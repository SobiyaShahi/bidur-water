"""Scenario control: scripted events from a JSON file plus keyboard keys.

Both push the same kind of event dictionary through EventRouter.dispatch(),
so nothing is hard-coded. Model events go to model.post_event(); network events
call link.block()/unblock() (Ritik's link object).
"""
import json
import threading
import time

from src.logutil import log

EVENT_TYPES = {"rain_event", "supply_interruption", "network_outage", "network_restore"}
DEFAULT_PEAK_NTU = 600
HELP = ("keys: e=rain event (all nodes)  1/2/3=rain on that node  i=supply interruption  "
        "o=toggle network outage  s=status  h=help  q=quit")


def load_scenario(path):
    """Read and validate the scenario file; return it with defaults filled in."""
    with open(path, encoding="utf-8") as f:
        sc = json.load(f)
    sc.setdefault("time_scale", 30)
    sc.setdefault("sample_interval_s", 2)
    sc.setdefault("start_hour", 8)
    sc.setdefault("events", [])
    for i, ev in enumerate(sc["events"]):
        if ev.get("type") not in EVENT_TYPES:
            raise ValueError(f"event {i}: unknown type {ev.get('type')!r}")
        if "at_s" not in ev:
            raise ValueError(f"event {i}: missing at_s")
        ev.setdefault("node", "all")
    sc["events"].sort(key=lambda e: e["at_s"])
    return sc


class EventRouter:
    """Sends an event to the right model(s) and link(s)."""

    def __init__(self, models, links=None):
        """models/links: dicts node_id -> object (links may be empty in dry-run)."""
        self.models, self.links = models, links or {}
        self.outage = False

    def dispatch(self, event):
        """Apply one event to its target node(s) and log it."""
        typ = event["type"]
        targets = list(self.models) if event.get("node", "all") == "all" else [event["node"]]
        for n in targets:
            if n not in self.models:
                log("scenario", "WARN", f"unknown node {n!r} in event {typ}")
                continue
            ev = dict(event, node=n)
            extra = {k: v for k, v in ev.items() if k not in ("type", "node", "at_s")}
            log(n, "EVENT", f"{typ} {extra}")
            if typ in ("rain_event", "supply_interruption"):
                self.models[n].post_event(ev)
            elif typ == "network_outage":
                self._link(n, True)
                if "duration_s" in ev:   # auto-restore after the duration
                    t = threading.Timer(float(ev["duration_s"]), self.dispatch,
                                        [{"type": "network_restore", "node": n}])
                    t.daemon = True
                    t.start()
            elif typ == "network_restore":
                self._link(n, False)

    def _link(self, node, blocked):
        """Block or unblock a node's link, if it has one."""
        link = self.links.get(node)
        if link is not None:
            (link.block if blocked else link.unblock)()

    def toggle_outage(self):
        """Keyboard outage toggle for all nodes."""
        self.outage = not self.outage
        self.dispatch({"type": "network_outage" if self.outage else "network_restore", "node": "all"})


def read_key():
    """Block until one key is pressed (Windows/macOS/Linux); falls back to Enter-terminated input."""
    try:
        import msvcrt
        return msvcrt.getwch()
    except ImportError:
        pass
    try:
        import sys
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        line = input()
        return line[:1]


class ScenarioRunner:
    """Runs the timed script and the keyboard listener until stop is set."""

    def __init__(self, router, scenario, stop, status_fn=None, keyboard=True):
        self.router, self.sc, self.stop = router, scenario, stop
        self.status_fn, self.keyboard = status_fn, keyboard

    def start(self):
        """Start background threads."""
        threading.Thread(target=self._script, daemon=True).start()
        if self.keyboard:
            threading.Thread(target=self._keys, daemon=True).start()
            log("scenario", "INFO", HELP)

    def _script(self):
        """Fire each scripted event at its at_s (real seconds since start)."""
        t0 = time.monotonic()
        for ev in self.sc["events"]:
            while not self.stop.is_set() and time.monotonic() - t0 < ev["at_s"]:
                self.stop.wait(0.05)
            if self.stop.is_set():
                return
            self.router.dispatch(ev)

    def _keys(self):
        """Turn key presses into the same events."""
        nodes = list(self.router.models)
        while not self.stop.is_set():
            try:
                k = read_key().lower()
            except EOFError:
                return
            if k == "e":
                self.router.dispatch({"type": "rain_event", "node": "all", "peak_ntu": DEFAULT_PEAK_NTU})
            elif k in "123" and k and int(k) <= len(nodes):
                self.router.dispatch({"type": "rain_event", "node": nodes[int(k) - 1],
                                      "peak_ntu": DEFAULT_PEAK_NTU})
            elif k == "i":
                self.router.dispatch({"type": "supply_interruption",
                                      "node": nodes[1] if len(nodes) > 1 else nodes[0],
                                      "duration_s": 60})
            elif k == "o":
                self.router.toggle_outage()
            elif k == "s" and self.status_fn:
                self.status_fn()
            elif k == "h":
                log("scenario", "INFO", HELP)
            elif k == "q":
                log("scenario", "INFO", "quit requested")
                self.stop.set()