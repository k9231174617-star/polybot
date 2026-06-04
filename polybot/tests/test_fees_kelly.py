from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/polybot_test")

from bot.analytics.engine import AnalyticsEngine
from bot.execution.fees import estimate_taker_fee, resolve_market_fee_rate
from bot.risk.dynamic_kelly import compute_adjusted_kelly


class FeesAndKellyTests(unittest.TestCase):
    def test_fee_formula_scales_with_price_distance(self) -> None:
        rate = resolve_market_fee_rate(category="politics")
        low_fee = estimate_taker_fee(100.0, 0.90, "YES", category="politics", fee_rate=rate)
        mid_fee = estimate_taker_fee(100.0, 0.50, "YES", category="politics", fee_rate=rate)
        self.assertGreater(mid_fee, low_fee)

    def test_kelly_size_respects_edge_direction(self) -> None:
        engine = AnalyticsEngine()
        size = engine.calculate_kelly_size(0.08, 0.58, 0.50, 1000.0, 0.25)
        self.assertGreater(size, 0.0)
        self.assertLessEqual(size, 1000.0)

    def test_dynamic_kelly_decreases_on_drawdown(self) -> None:
        base = 0.25
        reduced = compute_adjusted_kelly(base, current_pnl=80.0, peak_pnl=200.0, capital=1000.0, daily_pnl=-25.0, daily_limit_usd=30.0)
        self.assertLess(reduced, base)


if __name__ == "__main__":
    unittest.main()
