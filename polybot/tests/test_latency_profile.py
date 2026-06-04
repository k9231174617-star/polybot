from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.observability.latency import LatencyEvent, summarize_by_stage, summarize_by_signal_type


class LatencyProfileTests(unittest.TestCase):
    def test_stage_summary_computes_percentiles(self) -> None:
        now = datetime.now(timezone.utc)
        events = [
            LatencyEvent(1, "m1", "roda_oracle_lag", "signal_to_decision", 50.0, now, now + timedelta(milliseconds=50)),
            LatencyEvent(2, "m2", "roda_oracle_lag", "signal_to_decision", 100.0, now, now + timedelta(milliseconds=100)),
            LatencyEvent(3, "m3", "mss2_spread_capture", "signal_to_confirmation", 200.0, now, now + timedelta(milliseconds=200)),
        ]
        stage_summary = summarize_by_stage(events)
        self.assertEqual(stage_summary["signal_to_decision"]["count"], 2)
        self.assertGreater(stage_summary["signal_to_decision"]["p95_ms"], 50.0)
        type_summary = summarize_by_signal_type(events)
        self.assertEqual(type_summary["roda_oracle_lag"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
