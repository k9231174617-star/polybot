from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.backtest.calibration import calibrate_strategy
from bot.backtest.models import BacktestSnapshot


class BacktestCalibrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_calibration_returns_best_candidate(self) -> None:
        snapshots = [
            BacktestSnapshot(
                timestamp=datetime(2026, 6, 4, 12, tzinfo=timezone.utc),
                markets=[{
                    "id": "m1",
                    "question": "Will X happen?",
                    "category": "politics",
                    "market_price": 0.72,
                    "status": "active",
                    "end_date": datetime(2026, 6, 4, 11, tzinfo=timezone.utc),
                    "tokens": [{"token_id": "y1", "outcome": "YES"}, {"token_id": "n1", "outcome": "NO"}],
                }],
                news_by_market={
                    "m1": [{
                        "title": "X confirmed after vote",
                        "description": "Officials confirmed the event.",
                        "source": {"name": "AP"},
                        "published_at": datetime(2026, 6, 4, 11, 30, tzinfo=timezone.utc),
                    }]
                },
            ),
            BacktestSnapshot(
                timestamp=datetime(2026, 6, 4, 13, tzinfo=timezone.utc),
                markets=[{
                    "id": "m1",
                    "question": "Will X happen?",
                    "category": "politics",
                    "market_price": 1.0,
                    "resolved_yes": True,
                    "status": "resolved",
                    "end_date": datetime(2026, 6, 4, 11, tzinfo=timezone.utc),
                    "tokens": [{"token_id": "y1", "outcome": "YES"}, {"token_id": "n1", "outcome": "NO"}],
                }],
                news_by_market={
                    "m1": [{
                        "title": "X confirmed after vote",
                        "description": "Officials confirmed the event.",
                        "source": {"name": "AP"},
                        "published_at": datetime(2026, 6, 4, 11, 30, tzinfo=timezone.utc),
                    }]
                },
            ),
        ]
        result = await calibrate_strategy(snapshots, strategy="roda")
        self.assertEqual(result.strategy, "roda")
        self.assertIn("config_patch", result.to_dict())


if __name__ == "__main__":
    unittest.main()
