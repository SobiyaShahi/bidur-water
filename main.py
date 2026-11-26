#!/usr/bin/env python3
"""Entry point: Bidur post-flood water-quality edge simulator (ITS67404 Task 3).

Usage:  python main.py --help
        python main.py --dry-run            (models + scenario only, no SQLite/MQTT)
"""
import argparse
import json
import os
import sys
import threading
import time

from dotenv import load_dotenv

from src.logutil import log, setup_file_log
from src.models import WaterModel
from src.scenario import EventRouter, ScenarioRunner, load_scenario


def parse_args():
    """Command-line options (Ritik adds --batch-size, --fresh-db, ... as needed)."""
    ap = argparse.ArgumentParser(description="Water-quality edge simulator with store-and-forward")
    ap.add_argument("--config", default="config/nodes.json", help="node config (copy nodes.example.json)")
    ap.add_argument("--scenario", default="scenarios/demo_scenario.json")
    ap.add_argument("--dry-run", action="store_true", help="models + scenario only")
    ap.add_argument("--no-keyboard", action="store_true", help="disable keyboard keys")
    ap.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = until q)")
    ap.add_argument("--log-file", default=None, help="also write the console log to this file")
    return ap.parse_args()


def dry_run(models, interval, stop):
    """Print model readings only (no buffer, no network)."""
    seq = {n: 0 for n in models}
    while not stop.is_set():
        now = int(time.time() * 1000)
        for n, m in models.items():
            r = m.step(now)
            v = r["values"]
            seq[n] += 1
            log(n, "ONLINE", f"seq={seq[n]} ntu={v['turbidity_ntu']} ph={v['ph']} "
                             f"tds={v['tds_ppm']:.0f} flow={v['flow_lpm']} temp={v['water_temp_c']} "
                             f"sev={r['severity']}")
        stop.wait(interval)


def load_node_tokens(nodes):
    """Load each node token from its configured environment variable."""
    load_dotenv(dotenv_path=".env")
    for node in nodes:
        if "token" in node:
            raise ValueError(
                f"Node {node['id']} contains a static token; replace it with a token_env setting."
            )
        env_name = node.get("token_env")
        if not env_name:
            raise ValueError(f"Node {node['id']} must define token_env in the node config.")
        token = os.getenv(env_name)
        if not token:
            raise ValueError(f"Missing {env_name}; set it in .env or the process environment.")
        node["token"] = token


def main():
    """Load config and scenario, build models, start scenario control and the nodes."""
    a = parse_args()
    if a.log_file:
        setup_file_log(a.log_file)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    sc = load_scenario(a.scenario)
    models = {n["id"]: WaterModel(n, sc["time_scale"], sc["start_hour"]) for n in cfg["nodes"]}
    stop = threading.Event()

    if a.dry_run:
        links = {}
        threading.Thread(target=dry_run, args=(models, sc["sample_interval_s"], stop), daemon=True).start()
        status = lambda: [log(n, "STATUS", f"severity={m.severity:.2f}") for n, m in models.items()]
    else:
        load_node_tokens(cfg["nodes"])
        try:
            from src.node import Node   # Ritik's module, see docs/INTERFACES.md
        except ImportError:
            print("src/node.py not ready yet. Use --dry-run for now.")
            sys.exit(2)
        nodes = {n["id"]: Node(n, models[n["id"]], cfg, sc["sample_interval_s"]) for n in cfg["nodes"]}
        links = {i: nd.link for i, nd in nodes.items()}
        for nd in nodes.values():
            nd.start()
        status = lambda: [log(i, "STATUS", nd.status()) for i, nd in nodes.items()]

    router = EventRouter(models, links)
    ScenarioRunner(router, sc, stop, status, keyboard=not a.no_keyboard).start()
    t0 = time.monotonic()
    try:
        while not stop.wait(0.2):
            if a.duration and time.monotonic() - t0 > a.duration:
                stop.set()
    except KeyboardInterrupt:
        stop.set()
    if not a.dry_run:
        for nd in nodes.values():
            nd.stop()
    log("main", "INFO", "stopped")


if __name__ == "__main__":
    main()