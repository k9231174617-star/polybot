from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.analytics.recalibration import StrategyPerformance, _build_recommendation
from bot.config import settings


class RecalibrationTests(unittest.TestCase):
    def test_auto_recalibration_apply_changes_defaults_to_suggest_only(self) -> None:
        self.assertFalse(settings.auto_recalibration_apply_changes)

    def test_mss2_recalibration_tightens_queue_gate(self) -> None:
        performance = StrategyPerformance(
            strategy="mss2",
            sample_size=40,
            wins=10,
            losses=30,
            win_rate=0.25,
            gross_profit=25.0,
            gross_loss=55.0,
            net_pnl=-30.0,
            avg_pnl=-0.75,
            profit_factor=0.45,
            avg_queue_pressure=0.82,
            avg_expected_fill_delay_seconds=95.0,
            avg_latency_signal_to_confirmation_ms=1800.0,
            avg_wash_score=0.0,
            p95_latency_signal_to_confirmation_ms=2600.0,
            p95_latency_signal_to_trade_recorded_ms=2000.0,
        )
        recommendation = _build_recommendation(
            strategy="mss2",
            performance=performance,
            current_config={
                "mss2_min_spread_bps": 35.0,
                "mss2_min_expected_profit_bps": 35.0,
                "mss2_max_adverse_selection_score": 0.65,
                "mss2_max_queue_pressure": 0.75,
            },
            max_adjustment_pct=0.15,
        )
        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertLess(recommendation.proposed_patch["mss2_max_queue_pressure"], 0.75)
        self.assertGreater(recommendation.proposed_patch["mss2_min_expected_profit_bps"], 35.0)

    def test_roda_divergence_recalibration_tightens_confidence(self) -> None:
        performance = StrategyPerformance(
            strategy="roda",
            sample_size=30,
            wins=8,
            losses=22,
            win_rate=0.2666666667,
            gross_profit=12.0,
            gross_loss=28.0,
            net_pnl=-16.0,
            avg_pnl=-0.5333333333,
            profit_factor=0.4285714285,
            avg_queue_pressure=0.0,
            avg_expected_fill_delay_seconds=0.0,
            avg_latency_signal_to_confirmation_ms=0.0,
            avg_wash_score=0.0,
            p95_latency_signal_to_confirmation_ms=0.0,
            p95_latency_signal_to_trade_recorded_ms=0.0,
        )
        recommendation = _build_recommendation(
            strategy="roda",
            performance=performance,
            current_config={
                "roda_mode": "divergence",
                "roda_divergence_min_confidence": 0.60,
                "roda_divergence_min_edge": 0.06,
                "roda_divergence_min_sources": 2,
            },
            max_adjustment_pct=0.15,
        )
        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertGreater(recommendation.proposed_patch["roda_divergence_min_confidence"], 0.60)
        self.assertGreater(recommendation.proposed_patch["roda_divergence_min_edge"], 0.06)


if __name__ == "__main__":
    unittest.main()
