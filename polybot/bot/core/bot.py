"""Main bot loop — orchestrates data, analysis, risk checks, execution."""
import asyncio
import os
from loguru import logger

from bot.config import settings
from bot.data.polymarket import PolymarketClient
from bot.data.news import batch_sentiment
from bot.analytics.engine import AnalyticsEngine
from bot.analytics.calibration import load_calibration
from bot.analytics.arbitrage import find_all_arb_signals
from bot.execution.orders import OrderExecutor
from bot.execution.paper import PaperExecutor
from bot.risk.manager import RiskManager
from bot.risk.dynamic_kelly import KellyTracker
from bot.utils.db import (
    ensure_schema, update_bot_state, upsert_market, insert_signal, log_entry,
    snapshot_pnl, get_bot_config, get_pool, close_pool,
)


class PolymarketBot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.analytics = AnalyticsEngine()
        self.executor = OrderExecutor(dry_run=settings.dry_run)
        self.kelly_tracker = KellyTracker(0.25, settings.initial_capital_usd)
        self.scan_count = 0
        self._shutdown_event = asyncio.Event()
        self._paper: PaperExecutor | None = None

    async def start(self):
        logger.info("Starting Polymarket bot...")
        await ensure_schema()
        self.running = True
        await update_bot_state("running", markets_scanned=0, pid=os.getpid())
        await log_entry("bot", "info", "Bot started", {
            "dry_run": settings.dry_run, "pid": os.getpid(),
            "news_api": bool(settings.news_api_key),
        })
        asyncio.create_task(self._load_calibration())
        try:
            await self.run_loop()
        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            await update_bot_state("error", error_message=str(e))
            await log_entry("bot", "error", f"Bot crashed: {e}")
        finally:
            await update_bot_state("stopped")
            await log_entry("bot", "info", "Bot stopped")
            await close_pool()

    async def _load_calibration(self):
        try:
            await load_calibration(settings.polymarket_api_url)
            await log_entry("bot", "info", "Historical calibration loaded")
        except Exception as e:
            logger.debug(f"Calibration load: {e}")

    async def run_loop(self):
        while self.running and not self._shutdown_event.is_set():
            config = await get_bot_config()
            if not self.paused:
                try:
                    await self.scan_cycle(config)
                except Exception as e:
                    logger.error(f"Scan cycle error: {e}")
                    await log_entry("bot", "error", f"Scan cycle failed: {e}")
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=config.get("scan_interval_seconds", 30)
                )
                break
            except asyncio.TimeoutError:
                pass

    async def scan_cycle(self, config: dict):
        paper_on = config.get("paper_trading", True)
        capital = config.get("paper_capital_usd", 1000.0) if paper_on else settings.initial_capital_usd
        risk_mgr = RiskManager(config, capital, paper_mode=paper_on)

        if paper_on and self._paper is None:
            self._paper = PaperExecutor(capital)
            logger.info(f"Paper trading active: ${capital:.0f} virtual capital")

        # Dynamic Kelly
        if paper_on and self._paper:
            paper_stats = await self._paper.get_stats()
            cur_pnl = paper_stats["cumulative_pnl"]
            daily_pnl = paper_stats.get("today_realized_pnl", 0.0)
        else:
            cur_pnl = await self._total_pnl()
            daily_pnl = await self._daily_pnl()

        daily_limit = capital * config.get("daily_loss_limit_pct", 0.03)
        self.kelly_tracker.base_fraction = config.get("kelly_fraction", 0.25)
        self.kelly_tracker.total_capital = capital
        dyn_kelly = self.kelly_tracker.update(cur_pnl, daily_pnl, daily_limit)

        signals_found = 0
        markets_scanned = 0
        all_markets: list[dict] = []

        async with PolymarketClient() as client:
            raw_list = await client.get_active_markets(limit=min(settings.max_markets_to_scan, 100))
            parsed = [client.parse_market(r) for r in raw_list]
            valid = [m for m in parsed if m.get("id")]

            # Batch sentiment (concurrent)
            sentiment_map = await batch_sentiment(valid, api_key=settings.news_api_key)

            market_prices: dict[str, float] = {}

            for market in valid:
                try:
                    market_prices[market["id"]] = market["market_price"]
                    markets_scanned += 1
                    all_markets.append(market)
                    sentiment = sentiment_map.get(market["id"], 0.0)
                    market["sentiment_score"] = sentiment

                    signal = self.analytics.analyze_market(
                        market,
                        config={**config, "total_capital": capital},
                        sentiment_score=sentiment,
                        kelly_fraction_override=dyn_kelly,
                    )
                    await upsert_market(market)

                    if signal:
                        can_trade, reason = await risk_mgr.can_trade(signal)
                        if can_trade:
                            sig_id = await insert_signal(signal)
                            logger.info(
                                f"Signal #{sig_id} {signal['direction']} "
                                f"edge={signal['edge']:.3f} kelly=${signal['kelly_size_usd']:.2f} "
                                f"type={signal['signal_type']} kelly_frac={dyn_kelly:.2f}"
                            )
                            trade = None
                            if paper_on and self._paper:
                                trade = await self._paper.execute_signal(signal)
                            else:
                                trade = await self.executor.execute_signal(signal, config)
                            if trade:
                                signals_found += 1
                                await self._mark_acted(sig_id)
                except Exception as e:
                    logger.warning(f"Market processing error: {e}")

            # Arb detection
            for arb_sig in find_all_arb_signals(all_markets, capital):
                try:
                    arb_sig["kelly_size_usd"] = min(
                        self.analytics.calculate_kelly_size(
                            arb_sig["edge"], arb_sig.get("model_probability", 0.5),
                            arb_sig["market_price"], capital, dyn_kelly,
                        ),
                        capital * config.get("max_position_pct", 0.05),
                    )
                    arb_sig["confidence"] = min(0.85, abs(arb_sig["edge"]) * 3)
                    if arb_sig["kelly_size_usd"] >= 1.0:
                        can_trade, _ = await risk_mgr.can_trade(arb_sig)
                        if can_trade:
                            await insert_signal(arb_sig)
                            if paper_on and self._paper:
                                await self._paper.execute_signal(arb_sig)
                except Exception as e:
                    logger.debug(f"Arb signal error: {e}")

            # Update positions
            if paper_on and self._paper:
                await self._paper.update_positions(market_prices)
                await self._paper.snapshot_pnl()
            else:
                await self.executor.update_positions(market_prices)

        self.scan_count += 1
        await update_bot_state("running", markets_scanned=markets_scanned)
        pnl = cur_pnl if paper_on and self._paper else await self._total_pnl()
        await snapshot_pnl(pnl, capital + pnl)
        await log_entry("scanner", "info",
            f"Scan #{self.scan_count}: {markets_scanned} markets, {signals_found} signals, kelly={dyn_kelly:.2f}",
            {"scan": self.scan_count, "markets": markets_scanned, "kelly": dyn_kelly})

    async def _mark_acted(self, sig_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE signals SET status='acted',acted_at=NOW() WHERE id=$1", sig_id)

    async def _total_pnl(self) -> float:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COALESCE(SUM(realized_pnl),0) AS r,
                  (SELECT COALESCE(SUM(unrealized_pnl),0) FROM positions WHERE status='open') AS u
                FROM trades
            """)
            return float(row["r"] or 0) + float(row["u"] or 0)

    async def _daily_pnl(self) -> float:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(SUM(realized_pnl),0) AS r FROM trades WHERE executed_at>=CURRENT_DATE")
            return float(row["r"] or 0)

    def stop(self):
        self.running = False
        self._shutdown_event.set()
