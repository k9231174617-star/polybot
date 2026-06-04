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
from bot.analytics.roda import detect_roda_signals
from bot.analytics.lch import LchDetector
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
        self.lch_detector = LchDetector()

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

    async def _attempt_signal(self, signal: dict, config: dict, risk_mgr: RiskManager, paper_on: bool, label: str = "") -> bool:
        try:
            can_trade, reason = await risk_mgr.can_trade(signal)
            if not can_trade:
                if label:
                    logger.info(f"{label} skipped {signal['market_id']}: {reason}")
                else:
                    logger.info(f"Signal skipped {signal['market_id']}: {reason}")
                return False

            sig_id = await insert_signal(signal)
            logger.info(
                f"{label or 'Signal'} #{sig_id} {signal['direction']} "
                f"edge={signal['edge']:.3f} kelly=${signal['kelly_size_usd']:.2f} "
                f"type={signal['signal_type']} conf={signal.get('confidence', 0.0):.2f}"
            )
            trade = None
            if paper_on and self._paper:
                trade = await self._paper.execute_signal(signal)
            else:
                trade = await self.executor.execute_signal(signal, config)
            if trade:
                await self._mark_acted(sig_id)
                return True
            return False
        except Exception as e:
            logger.warning(f"{label or 'Signal'} error: {e}")
            return False

    async def scan_cycle(self, config: dict):
        paper_on = config.get("paper_trading", True)
        capital = config.get("paper_capital_usd", 1000.0) if paper_on else settings.initial_capital_usd
        risk_mgr = RiskManager(config, capital, paper_mode=paper_on)

        if paper_on and self._paper is None:
            self._paper = PaperExecutor(capital)
            logger.info(f"Paper trading active: ${capital:.0f} virtual capital")

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
        strategic_market_ids: set[str] = set()

        roda_config = {
            **config,
            "roda_enabled": settings.roda_enabled,
            "roda_min_confidence": settings.roda_min_confidence,
            "roda_min_age_hours": settings.roda_min_age_hours,
            "roda_max_age_hours": settings.roda_max_age_hours,
            "roda_max_entry_price": settings.roda_max_entry_price,
            "roda_min_sources": settings.roda_min_sources,
            "roda_hold_window_hours": settings.roda_hold_window_hours,
            "roda_max_position_pct": settings.roda_max_position_pct,
        }
        lch_config = {
            **config,
            "lch_enabled": settings.lch_enabled,
            "lch_min_hours_to_resolve": settings.lch_min_hours_to_resolve,
            "lch_lookback_hours": settings.lch_lookback_hours,
            "lch_min_shock_magnitude": settings.lch_min_shock_magnitude,
            "lch_min_z_score": settings.lch_min_z_score,
            "lch_min_recovery_probability": settings.lch_min_recovery_probability,
            "lch_stop_loss_pct": settings.lch_stop_loss_pct,
            "lch_take_profit_pct_of_shock": settings.lch_take_profit_pct_of_shock,
            "lch_max_hold_minutes": settings.lch_max_hold_minutes,
            "lch_max_position_pct": settings.lch_max_position_pct,
            "lch_kelly_fraction": settings.lch_kelly_fraction,
            "lch_min_position_size_usd": settings.lch_min_position_size_usd,
            "lch_max_position_size_usd": settings.lch_max_position_size_usd,
            "lch_max_daily_trades": settings.lch_max_daily_trades,
        }

        async with PolymarketClient() as client:
            raw_list = await client.get_active_markets(limit=min(settings.max_markets_to_scan, 100))
            parsed = [client.parse_market(r) for r in raw_list]
            valid = [m for m in parsed if m.get("id")]

            sentiment_map = await batch_sentiment(valid, api_key=settings.news_api_key)

            market_prices: dict[str, float] = {}
            roda_signals = await detect_roda_signals(
                valid,
                news_api_key=settings.news_api_key,
                config=roda_config,
                kelly_fraction=dyn_kelly,
                total_capital=capital,
            )
            for signal in roda_signals:
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="RODA"):
                    signals_found += 1
                    strategic_market_ids.add(signal["market_id"])

            lch_signals = await self.lch_detector.detect_signals(
                valid,
                config=lch_config,
                kelly_fraction=settings.lch_kelly_fraction,
                total_capital=capital,
            )
            for signal in lch_signals:
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="LCH"):
                    signals_found += 1
                    strategic_market_ids.add(signal["market_id"])

            for market in valid:
                try:
                    market_prices[market["id"]] = market["market_price"]
                    markets_scanned += 1
                    all_markets.append(market)
                    await upsert_market(market)
                    if market["id"] in strategic_market_ids:
                        continue

                    sentiment = sentiment_map.get(market["id"], 0.0)
                    market["sentiment_score"] = sentiment

                    signal = self.analytics.analyze_market(
                        market,
                        config={**config, "total_capital": capital},
                        sentiment_score=sentiment,
                        kelly_fraction_override=dyn_kelly,
                    )

                    if signal and await self._attempt_signal(signal, config, risk_mgr, paper_on):
                        signals_found += 1
                except Exception as e:
                    logger.warning(f"Market processing error: {e}")

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
                    if arb_sig["kelly_size_usd"] >= 1.0 and await self._attempt_signal(arb_sig, config, risk_mgr, paper_on, label="ARB"):
                        signals_found += 1
                except Exception as e:
                    logger.debug(f"Arb signal error: {e}")

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
