from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/polybot_test")

from bot.risk.manager import RiskManager


class RiskManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_loss_limit_blocks_trade(self) -> None:
        mgr = RiskManager({"daily_loss_limit_pct": 0.03, "max_position_pct": 0.05, "max_correlated_exposure_pct": 0.15}, 1000.0, paper_mode=True)
        mgr.check_daily_loss_limit = AsyncMock(return_value=False)
        ok, reason = await mgr.can_trade({"kelly_size_usd": 50.0, "market_id": "m1"})
        self.assertFalse(ok)
        self.assertIn("Daily loss", reason)

    async def test_duplicate_market_blocks_trade(self) -> None:
        mgr = RiskManager({"daily_loss_limit_pct": 0.03, "max_position_pct": 0.05, "max_correlated_exposure_pct": 0.15}, 1000.0, paper_mode=True)
        mgr.check_daily_loss_limit = AsyncMock(return_value=True)
        mgr.check_position_limit = AsyncMock(return_value=True)
        mgr.check_total_exposure = AsyncMock(return_value=True)
        mgr.check_duplicate_market = AsyncMock(return_value=False)
        ok, reason = await mgr.can_trade({"kelly_size_usd": 50.0, "market_id": "m1"})
        self.assertFalse(ok)
        self.assertIn("Already have open position", reason)


if __name__ == "__main__":
    unittest.main()
