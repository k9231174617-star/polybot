from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/polybot_test")

from bot.analytics.lch import LchDetector


class LchWashTests(unittest.TestCase):
    def test_wash_score_is_high_for_repetitive_bursty_trades(self) -> None:
        detector = LchDetector()
        now = datetime.now(timezone.utc)
        trades = [
            {"timestamp": now - timedelta(seconds=i * 2), "price": 0.52, "size": 100.0, "wallet": "0xabc", "side": "BUY"}
            for i in range(10)
        ]
        score = detector._wash_trading_score(trades, now)
        self.assertGreaterEqual(score, 0.7)

    def test_wash_score_is_low_for_diverse_trades(self) -> None:
        detector = LchDetector()
        now = datetime.now(timezone.utc)
        trades = [
            {"timestamp": now - timedelta(minutes=i * 10), "price": 0.40 + i * 0.01, "size": 10.0 + i, "wallet": f"0x{i:02x}", "side": "BUY" if i % 2 == 0 else "SELL"}
            for i in range(10)
        ]
        score = detector._wash_trading_score(trades, now)
        self.assertLess(score, 0.5)


if __name__ == "__main__":
    unittest.main()
