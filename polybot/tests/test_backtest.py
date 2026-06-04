from __future__ import annotations

import os
import tempfile
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.analytics.roda import detect_roda_signals
from bot.backtest.engine import BacktestConfig, BacktestEngine
from bot.backtest.loader import load_backtest_snapshots
from bot.backtest.models import BacktestSnapshot


class BacktestLoaderTests(unittest.TestCase):
    def test_load_jsonl_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.jsonl"
            path.write_text(
                "\n".join([
                    '{"timestamp":"2026-06-04T12:00:00Z","markets":[{"id":"m1","question":"Will X happen?","market_price":0.5,"status":"active","end_date":"2026-06-05T00:00:00Z","tokens":[{"token_id":"y1","outcome":"YES"},{"token_id":"n1","outcome":"NO"}]}]}',
                    '{"timestamp":"2026-06-04T12:01:00Z","markets":[{"id":"m1","question":"Will X happen?","market_price":1.0,"status":"resolved","resolved_yes":true,"end_date":"2026-06-05T00:00:00Z","tokens":[{"token_id":"y1","outcome":"YES"},{"token_id":"n1","outcome":"NO"}]}]}',
                ]),
                encoding="utf-8",
            )
            snapshots = load_backtest_snapshots(path)
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(snapshots[0].markets[0]["id"], "m1")


class RodaBacktestTests(unittest.IsolatedAsyncioTestCase):
    async def test_roda_uses_embedded_news_articles(self) -> None:
        markets = [{
            "id": "m1",
            "question": "Will X happen?",
            "category": "politics",
            "market_price": 0.72,
            "status": "active",
            "end_date": datetime(2026, 6, 4, 11, tzinfo=timezone.utc),
        }]
        news = {
            "m1": [{
                "title": "X confirmed after vote",
                "description": "Officials confirmed the event.",
                "source": {"name": "AP"},
                "published_at": datetime(2026, 6, 4, 11, 30, tzinfo=timezone.utc),
            }]
        }
        signals = await detect_roda_signals(
            markets,
            news_articles_by_market=news,
            config={"roda_enabled": True, "roda_min_sources": 1, "roda_min_confidence": 0.1},
            kelly_fraction=0.25,
            total_capital=1000.0,
        )
        self.assertTrue(signals)


class BacktestEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_engine_runs_simple_backtest(self) -> None:
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
        engine = BacktestEngine(BacktestConfig(
            allow_lch=False,
            allow_hybrid=False,
            allow_mss2=False,
            allow_arb=False,
            roda_min_sources=1,
            roda_min_confidence=0.1,
        ))
        report = await engine.run(snapshots)
        self.assertGreaterEqual(report.total_signals, 1)
        self.assertGreaterEqual(report.executed_trades, 1)
        self.assertGreaterEqual(report.final_capital_usd, 0.0)
