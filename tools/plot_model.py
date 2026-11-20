"""Plot the event curves that prove physical coupling.
Usage: python tools/plot_model.py [--node node-01] [--peak 600] [--seconds 600] [--save curves.png]"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import matplotlib.pyplot as plt
from src.models import WaterModel

BASE_MS = 1_795_046_400_000


def simulate(node, peak, seconds, rain_at=60, supply_at=360, dt=2):
    """Run one model on a synthetic clock; return list of (t_real_s, reading)."""
    m = WaterModel({"id": node, "latitude": 27.9, "longitude": 85.1}, time_scale=30, start_hour=8)
    rows = []
    for t in range(0, seconds + 1, dt):
        now = BASE_MS + t * 1000
        if t == rain_at:
            m.post_event({"type": "rain_event", "peak_ntu": peak}, now)
        if t == supply_at:
            m.post_event({"type": "supply_interruption", "duration_s": 60}, now)
        rows.append((t, m.step(now)))
    return rows


def main():
    """Draw turbidity, TDS, pH, flow and temperature on a shared time axis."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default="node-01")
    ap.add_argument("--peak", type=float, default=600)
    ap.add_argument("--seconds", type=int, default=600)
    ap.add_argument("--save", default=None)
    a = ap.parse_args()
    rows = simulate(a.node, a.peak, a.seconds)
    t = [r[0] for r in rows]
    series = [("turbidity_ntu", "Turbidity (NTU)", [50, 200]),
              ("tds_ppm", "TDS (ppm)", [500]),
              ("ph", "pH", [6.5]),
              ("flow_lpm", "Flow (L/min)", []),
              ("water_temp_c", "Temp (°C)", [])]
    fig, axes = plt.subplots(len(series), 1, sharex=True, figsize=(9, 10))
    for ax, (key, label, lines) in zip(axes, series):
        ax.plot(t, [r[1]["values"][key] for r in rows])
        for y in lines:
            ax.axhline(y, ls="--", lw=0.8, color="red")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Real time since start (s); model clock is 30x faster")
    axes[0].set_title(f"{a.node}: rain event at 60 s (peak {a.peak:.0f} NTU), supply interruption at 360 s")
    fig.tight_layout()
    if a.save:
        fig.savefig(a.save, dpi=200)
    plt.show()


if __name__ == "__main__":
    main()