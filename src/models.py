"""Physics-based water-quality model for one sensor node.

One event strength drives everything, so parameters move together:
  turbidity rises fast, TDS rises lagged, pH falls with diminishing returns,
  flow gets a short surge then settles lower. Temperature is independent
  (daily cycle). The model clock runs `time_scale` times faster than real time,
  but the 'ts' returned is always real wall-clock epoch milliseconds.
"""
import math
import random
import threading
import time
import zlib

# --- physical constants (justify these in the paper) ---
PEAK_REF_NTU = 600.0        # peak that counts as strength 1.0
K_TDS = 350.0               # ppm added at full strength (cite sewage TDS source!)
DPH_MAX = 1.0               # max pH drop below baseline
B_PH = 2.5                  # pH saturation rate: drop = DPH_MAX*(1-exp(-B*I))
RISE_MODEL_S = 12 * 60      # turbidity rise time (model seconds)
TAU_TDS_LAG_S = 10 * 60     # TDS smoothing time constant (model seconds)
DEFAULT_TAU_MIN = 60.0      # washout time constant, model minutes (45-90 allowed)
FLOW_DROP = 0.15            # steady flow loss at full strength (leak at breach)
FLOW_SURGE_AMP = 0.25       # pressure-transient amplitude
FLOW_SURGE_DECAY_S = 120.0  # transient decay (REAL seconds, so 2 s sampling sees it)
FLOW_SURGE_PERIOD_S = 90.0  # transient period (REAL seconds)
SUPPLY_RAMP_S = 10.0        # real seconds to ramp flow to/from zero

# Per-node baselines (slightly different on purpose, not a fixed band).
DEFAULT_PROFILES = {
    "node-01": dict(base_ph=7.30, base_ntu=4.5, base_tds=200.0, base_flow=12.0, temp_offset=0.0),
    "node-02": dict(base_ph=7.10, base_ntu=3.0, base_tds=160.0, base_flow=14.0, temp_offset=-0.4),
    "node-03": dict(base_ph=7.20, base_ntu=3.8, base_tds=180.0, base_flow=9.0, temp_offset=0.3),
}
FALLBACK_PROFILE = dict(base_ph=7.2, base_ntu=4.0, base_tds=180.0, base_flow=12.0, temp_offset=0.0)


class AR1:
    """Correlated noise: each sample is partly the previous one (stationary sd = sigma)."""

    def __init__(self, rng, phi, sigma):
        self.rng, self.phi, self.sigma, self.x = rng, phi, sigma, 0.0

    def step(self):
        """Advance one sample and return the new noise value."""
        self.x = self.phi * self.x + self.sigma * math.sqrt(1 - self.phi ** 2) * self.rng.gauss(0, 1)
        return self.x


def rain_envelope(t_s, tau_s):
    """Event shape 0..1: smooth S-curve rise (3x^2-2x^3), then exponential washout."""
    if t_s <= 0:
        return 0.0
    if t_s < RISE_MODEL_S:
        x = t_s / RISE_MODEL_S
        return 3 * x * x - 2 * x ** 3
    return math.exp(-(t_s - RISE_MODEL_S) / tau_s)


def supply_factor(el_s, dur_s):
    """Flow multiplier for a supply interruption: ramp down, hold at exactly 0, ramp up."""
    if el_s < 0:
        return 1.0
    if el_s < SUPPLY_RAMP_S:
        return 1.0 - el_s / SUPPLY_RAMP_S
    if el_s < SUPPLY_RAMP_S + dur_s:
        return 0.0
    if el_s < 2 * SUPPLY_RAMP_S + dur_s:
        return (el_s - SUPPLY_RAMP_S - dur_s) / SUPPLY_RAMP_S
    return 1.0


def _bump(h, centre, width):
    """Smooth hump used for the daily water-demand pattern."""
    return math.exp(-(((h - centre) / width) ** 2))


def demand_factor(hour):
    """Household demand: morning and evening peaks, low at night (0.85 .. ~1.25)."""
    return 1 + 0.25 * _bump(hour, 7, 1.5) + 0.20 * _bump(hour, 18, 2.0) - 0.15 * _bump(hour, 3, 2.0)


class WaterModel:
    """Model for one node. Call step(now_ms) once per sample; post_event(event) any time."""

    def __init__(self, node_cfg, time_scale=30.0, start_hour=8.0, seed=None, noise_scale=1.0):
        """node_cfg needs id, latitude, longitude; optional 'baseline' overrides.
        noise_scale=0 gives a noise-free model (used by tests and plots)."""
        self.node_id = node_cfg["id"]
        self.lat = node_cfg.get("latitude")
        self.lon = node_cfg.get("longitude")
        self.p = dict(DEFAULT_PROFILES.get(self.node_id, FALLBACK_PROFILE))
        self.p.update(node_cfg.get("baseline", {}))
        self.time_scale = float(time_scale)
        self.start_hour = float(start_hour)
        self.noise_scale = float(noise_scale)
        # reproducible per node (crc32, not hash(), which changes every run)
        self.rng = random.Random(zlib.crc32(self.node_id.encode()) if seed is None else seed)
        r = self.rng
        self._n_ntu_slow, self._n_ntu_fast = AR1(r, 0.98, 0.12), AR1(r, 0.5, 0.03)
        self._n_tds_slow, self._n_tds_fast = AR1(r, 0.995, 4.0), AR1(r, 0.6, 1.5)
        self._n_ph_slow, self._n_ph_fast = AR1(r, 0.99, 0.04), AR1(r, 0.5, 0.01)
        self._n_temp, self._n_flow = AR1(r, 0.9, 0.15), AR1(r, 0.7, 0.03)
        self._rain, self._supply = [], []
        self._start_ms = self._last_ms = None
        self._i_lag = 0.0       # lagged severity driving TDS
        self._blip = 0.0        # tiny natural turbidity bumps
        self.severity = 0.0     # severity scalar 0..1 (read by node/log)
        self._lock = threading.RLock()

    def _n(self, ar):
        """Noise sample scaled by noise_scale."""
        return ar.step() * self.noise_scale

    def post_event(self, event, now_ms=None):
        """Start a scenario event. Returns True if the model handled it.
        rain_event: peak_ntu, optional tau_min. supply_interruption: duration_s."""
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        typ = event.get("type")
        with self._lock:
            if typ == "rain_event":
                peak = max(float(event.get("peak_ntu", 600)), self.p["base_ntu"])
                tau = float(event.get("tau_min", DEFAULT_TAU_MIN)) * 60.0
                self._rain.append({"t0": now_ms, "peak": peak, "tau_s": tau})
                return True
            if typ == "supply_interruption":
                self._supply.append({"t0": now_ms, "dur": float(event.get("duration_s", 60))})
                return True
        return False  # network events are handled by the link, not the model

    def step(self, now_ms):
        """Return {"ts", "severity", "values": {ph, turbidity_ntu, tds_ppm,
        water_temp_c, flow_lpm, latitude, longitude}} for time now_ms (epoch ms).
        The node adds rssi_dbm, buffer_depth and seq."""
        with self._lock:
            now_ms = int(now_ms)
            if self._start_ms is None:
                self._start_ms = self._last_ms = now_ms
            dt = max(0.0, (now_ms - self._last_ms) / 1000.0 * self.time_scale)  # model seconds
            self._last_ms = now_ms
            t_model = (now_ms - self._start_ms) / 1000.0 * self.time_scale
            hour = (self.start_hour + t_model / 3600.0) % 24.0
            p = self.p

            # --- event strength I (severity) and turbidity excess ---
            sev, extra, alive = 0.0, 0.0, []
            for ev in self._rain:
                el = (now_ms - ev["t0"]) / 1000.0 * self.time_scale
                env = rain_envelope(el, ev["tau_s"])
                sev = max(sev, env * min(1.0, ev["peak"] / PEAK_REF_NTU))
                extra = max(extra, (ev["peak"] - p["base_ntu"]) * env)
                if el < RISE_MODEL_S or env > 1e-3:
                    alive.append(ev)
            self._rain = alive
            self.severity = sev

            # --- turbidity: drifting baseline + rare blips + event, multiplicative noise ---
            self._blip *= math.exp(-dt / 300.0)
            if self.noise_scale > 0 and self.rng.random() < 0.004:
                self._blip += self.rng.uniform(1.0, 4.0)
            base_ntu = p["base_ntu"] * math.exp(self._n(self._n_ntu_slow)) + self._blip
            ntu = (base_ntu + extra) * (1 + self._n(self._n_ntu_fast))

            # --- TDS: follows a LAGGED severity (dissolved load mixes slowly) ---
            self._i_lag += (1 - math.exp(-dt / TAU_TDS_LAG_S)) * (sev - self._i_lag)
            tds = p["base_tds"] + self._n(self._n_tds_slow) + self._n(self._n_tds_fast) + K_TDS * self._i_lag

            # --- pH: falls with diminishing returns, floor about 1 unit below baseline ---
            ph = (p["base_ph"] + self._n(self._n_ph_slow) + self._n(self._n_ph_fast)
                  - DPH_MAX * (1 - math.exp(-B_PH * sev)))

            # --- temperature: independent daily cycle, peak mid-afternoon ---
            temp = 20 + 4 * math.sin(2 * math.pi * (hour - 9) / 24) + p["temp_offset"] + self._n(self._n_temp)

            # --- flow: demand pattern x (leak loss + surge/wobble) x supply interruption ---
            surge = 0.0
            for ev in self._rain:
                el = (now_ms - ev["t0"]) / 1000.0   # REAL seconds
                if el >= 0:
                    surge += (min(1.0, ev["peak"] / PEAK_REF_NTU) * FLOW_SURGE_AMP
                              * math.exp(-el / FLOW_SURGE_DECAY_S)
                              * math.cos(2 * math.pi * el / FLOW_SURGE_PERIOD_S))
            sup = 1.0
            for ev in self._supply:
                sup = min(sup, supply_factor((now_ms - ev["t0"]) / 1000.0, ev["dur"]))
            self._supply = [e for e in self._supply
                            if (now_ms - e["t0"]) / 1000.0 < 2 * SUPPLY_RAMP_S + e["dur"] + 5]
            flow = (p["base_flow"] * demand_factor(hour) * (1 - FLOW_DROP * sev + surge)
                    * sup * (1 + self._n(self._n_flow)))

            return {
                "ts": now_ms,
                "severity": round(sev, 3),
                "values": {
                    "ph": round(min(14.0, max(0.0, ph)), 2),
                    "turbidity_ntu": round(max(0.1, ntu), 1),
                    "tds_ppm": round(max(0.0, tds), 0),
                    "water_temp_c": round(temp, 1),
                    "flow_lpm": round(max(0.0, flow), 1),
                    "latitude": self.lat,
                    "longitude": self.lon,
                },
            }