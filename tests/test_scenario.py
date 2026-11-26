"""Scenario keyboard behavior checks. Run with: python -m pytest tests/test_scenario.py"""
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from src.scenario import ScenarioRunner


class RecordingRouter:
    def __init__(self, nodes):
        self.models = dict.fromkeys(nodes)
        self.events = []

    def dispatch(self, event):
        self.events.append(event)


class ScenarioTests(unittest.TestCase):
    def test_rain_keys_use_per_node_peak_ntu(self):
        router = RecordingRouter(["node-01", "node-02", "node-03", "node-04"])
        runner = ScenarioRunner(router, {}, threading.Event())
        keys = iter(["e", "1", "2", "3", "4", "q"])

        with patch("src.scenario.read_key", side_effect=lambda: next(keys)):
            runner._keys()

        self.assertEqual(
            router.events,
            [
                {"type": "rain_event", "node": "node-01", "peak_ntu": 600},
                {"type": "rain_event", "node": "node-02", "peak_ntu": 150},
                {"type": "rain_event", "node": "node-03", "peak_ntu": 35},
                {"type": "rain_event", "node": "node-04", "peak_ntu": 600},
                {"type": "rain_event", "node": "node-01", "peak_ntu": 600},
                {"type": "rain_event", "node": "node-02", "peak_ntu": 150},
                {"type": "rain_event", "node": "node-03", "peak_ntu": 35},
            ],
        )


if __name__ == "__main__":
    unittest.main()
