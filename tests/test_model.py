"""Model checks. Run: python tests/test_model.py   (or: python -m pytest tests)"""
import pathlib
import statistics
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from src.models import WaterModel

BASE_MS = 1_795_046_400_000
CFG = {"id": "t-01", "latitude": 27.9, "longitude": 85.1,
       "baseline": dict(base_ph=7.2, base_ntu=4.0, base_tds=180.0, base_flow=12.0, temp_offset=0.0)}


def run(model, seconds, events=(), dt=2):
    """Step the model on a synthetic clock; events = [(at_s, event_dict)]."""
    out = []
    for t in range(0, seconds + 1, dt):
        for at, ev in events:
            if at == t:
                model.post_event(ev, BASE_MS + t * 1000)
        out.append((t, model.step(BASE_MS + t * 1000)))
    return out


def col(rows, key, upto=None):
    return [r["values"][key] for t, r in rows if upto is None or t <= upto]


class ModelTests(unittest.TestCase):
    def test_timestamp_is_13_digit_epoch_ms(self):
        r = WaterModel(CFG).step(BASE_MS)
        self.assertIsInstance(r["ts"], int)
        self.assertEqual(len(str(r["ts"])), 13)

    def test_baseline_is_plausible_and_not_flat(self):
        m = WaterModel({"id": "node-01", "latitude": 1, "longitude": 1})
        rows = run(m, 600)
        self.assertTrue(all(6.6 < v < 7.9 for v in col(rows, "ph")))
        self.assertTrue(all(0.1 <= v < 15 for v in col(rows, "turbidity_ntu")))
        self.assertTrue(all(100 < v < 300 for v in col(rows, "tds_ppm")))
        self.assertTrue(all(14 < v < 26 for v in col(rows, "water_temp_c")))
        self.assertTrue(all(3 < v < 20 for v in col(rows, "flow_lpm")))
        self.assertGreater(statistics.pstdev(col(rows, "tds_ppm")), 0.5)
        self.assertEqual(rows[-1][1]["severity"], 0.0)

    def test_same_seed_same_data(self):
        a = run(WaterModel(CFG, seed=5), 60)
        b = run(WaterModel(CFG, seed=5), 60)
        self.assertEqual(col(a, "tds_ppm"), col(b, "tds_ppm"))

    def test_severe_event_is_coupled(self):
        m = WaterModel(CFG, noise_scale=0)
        rows = run(m, 300, [(0, {"type": "rain_event", "peak_ntu": 600})])
        ntu, tds, ph = col(rows, "turbidity_ntu"), col(rows, "tds_ppm"), col(rows, "ph")
        self.assertGreater(max(ntu), 590)                       # turbidity hits peak
        self.assertGreater(max(tds) - 180, 220)                 # TDS rises with it
        self.assertLess(min(ph), 6.5)                           # pH crosses the alarm line
        self.assertGreater(tds.index(max(tds)), ntu.index(max(ntu)))   # TDS lags turbidity
        w = 75                                                  # samples up to t=150 s
        self.assertLess(statistics.correlation(ntu[:w], ph[:w]), -0.85)
        self.assertGreater(statistics.correlation(ntu[:w], tds[:w]), 0.5)

    def test_mild_event_does_not_trigger_tds_alarm(self):
        m = WaterModel(CFG, noise_scale=0)
        rows = run(m, 300, [(0, {"type": "rain_event", "peak_ntu": 180})])
        self.assertTrue(170 < max(col(rows, "turbidity_ntu")) < 190)
        self.assertLess(max(col(rows, "tds_ppm")), 400)
        drop = 7.2 - min(col(rows, "ph"))
        self.assertTrue(0.3 < drop < 0.7)

    def test_supply_interruption_is_exactly_zero_then_recovers(self):
        m = WaterModel(CFG, noise_scale=0)
        rows = run(m, 140, [(10, {"type": "supply_interruption", "duration_s": 60})])
        flow = {t: r["values"]["flow_lpm"] for t, r in rows}
        self.assertTrue(all(flow[t] == 0.0 for t in range(22, 79, 2)))
        self.assertGreater(flow[4], 5)
        self.assertGreater(flow[120], 5)

    def test_network_events_are_not_model_events(self):
        self.assertFalse(WaterModel(CFG).post_event({"type": "network_outage"}))


if __name__ == "__main__":
    unittest.main()