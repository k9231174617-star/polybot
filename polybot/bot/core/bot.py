"""Main bot loop — orchestrates data, analysis, risk checks, execution."""
import asyncio
import json
import os
from loguru import logger

from bot.config import settings
from bot.data.polymarket import PolymarketClient
from bot.data.polymarket_ws import PolymarketMarketStream
from bot.data.divergence import fetch_divergence_feeds
from bot.data.news import batch_sentiment
from bot.analytics.engine import AnalyticsEngine
from bot.analytics.calibration import load_calibration
from bot.analytics.arbitrage import find_all_arb_signals
from bot.analytics.mss2 import Mss2Scanner
from bot.analytics.hybrid import detect_hybrid_signals
from bot.analytics.roda import detect_roda_signals
from bot.analytics.lch import LchDetector
from bot.analytics.recalibration import run_auto_recalibration
from bot.execution.orders import OrderExecutor
from bot.execution.paper import PaperExecutor
from bot.notifications.mss2 import notify_mss2_event
from bot.notifications import send_telegram_alert
from bot.risk.manager import RiskManager
from bot.risk.mss2 import Mss2RiskManager
from bot.risk.dynamic_kelly import KellyTracker
from bot.utils.db import (
    ensure_schema, apply_retention_policy, update_bot_state, upsert_market, insert_signal, log_entry,
    snapshot_pnl, get_bot_config, get_pool, close_pool, record_latency_event,
)
from bot.observability.latency import utcnow, duration_ms


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
        self.mss2_detector = Mss2Scanner()
        self.mss2_risk = Mss2RiskManager()
        self.market_stream = PolymarketMarketStream()
        self._market_stream_task: asyncio.Task | None = None
        self._divergence_refresh_task: asyncio.Task | None = None
        self._recalibration_task: asyncio.Task | None = None
        self._roda_latest_markets: list[dict] = []
        self._roda_divergence_sources: dict[str, list[dict]] = {}

    async def start(self):
        logger.info("Starting Polymarket bot...")
        await ensure_schema()
        self.running = True
        await update_bot_state("running", markets_scanned=0, pid=os.getpid())
        try:
            await apply_retention_policy()
        except Exception as exc:
            logger.debug(f"Initial retention skipped: {exc}")
        await log_entry("bot", "info", "Bot started", {
            "dry_run": settings.dry_run, "pid": os.getpid(),
            "news_api": bool(settings.news_api_key),
        })
        await send_telegram_alert(
            "info",
            "Bot started",
            f"Polymarket bot started in {'paper' if settings.dry_run else 'live'} mode",
            {"pid": os.getpid(), "paper_mode": settings.dry_run},
        )
        asyncio.create_task(self._load_calibration())
        self._market_stream_task = asyncio.create_task(self.market_stream.run())
        self._divergence_refresh_task = asyncio.create_task(self._refresh_roda_divergence_sources())
        self._recalibration_task = asyncio.create_task(self._auto_recalibration_loop())
        try:
            await self.run_loop()
        except asyncio.CancelledError:
            logger.info("Bot cancelled")
        except Exception as e:
            logger.error(f"Bot crashed: {e}")
            await update_bot_state("error", error_message=str(e))
            await log_entry("bot", "error", f"Bot crashed: {e}")
        finally:
            await self.market_stream.stop()
            if self._market_stream_task:
                self._market_stream_task.cancel()
                try:
                    await self._market_stream_task
                except BaseException as exc:
                    logger.debug(f"Market stream task stopped with: {exc}")
            if self._divergence_refresh_task:
                self._divergence_refresh_task.cancel()
                try:
                    await self._divergence_refresh_task
                except BaseException as exc:
                    logger.debug(f"Divergence refresh task stopped with: {exc}")
            if self._recalibration_task:
                self._recalibration_task.cancel()
                try:
                    await self._recalibration_task
                except BaseException as exc:
                    logger.debug(f"Recalibration task stopped with: {exc}")
            await update_bot_state("stopped")
            await log_entry("bot", "info", "Bot stopped")
            await close_pool()

    async def _load_calibration(self):
        try:
            await load_calibration(settings.polymarket_api_url)
            await log_entry("bot", "info", "Historical calibration loaded")
        except Exception as e:
            logger.debug(f"Calibration load: {e}")

    def _parse_divergence_feeds(self) -> list[dict]:
        raw = settings.roda_divergence_feeds_json.strip()
        if not raw:
            return [
                {
                    "source": "manifold",
                    "provider": "manifold",
                    "sort": "most-popular",
                    "filter": "open",
                    "contract_type": "BINARY",
                    "limit": 250,
                    "min_similarity": 0.34,
                },
                {
                    "source": "kalshi",
                    "provider": "kalshi",
                    "status": "open",
                    "limit": 250,
                    "min_similarity": 0.34,
                },
            ]
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            logger.debug(f"Divergence feed config parse failed: {exc}")
            return []
        if isinstance(parsed, dict):
            parsed = parsed.get("feeds") or parsed.get("sources") or parsed.get("providers") or []
        if not isinstance(parsed, list):
            return []
        feeds: list[dict] = []
        for item in parsed:
            if isinstance(item, dict) and item.get("url"):
                feeds.append(item)
        return feeds

    async def _refresh_roda_divergence_sources(self):
        feeds = self._parse_divergence_feeds()
        if not feeds:
            return
        refresh_seconds = max(15, int(settings.roda_divergence_refresh_seconds))
        while not self._shutdown_event.is_set():
            try:
                self._roda_divergence_sources = await fetch_divergence_feeds(feeds, markets=self._roda_latest_markets)
                await log_entry(
                    "roda",
                    "info",
                    "Divergence feeds refreshed",
                    {"markets": len(self._roda_divergence_sources), "feeds": len(feeds)},
                )
            except Exception as exc:
                logger.debug(f"Divergence feed refresh failed: {exc}")
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=refresh_seconds)
                break
            except asyncio.TimeoutError:
                continue

    async def _auto_recalibration_loop(self):
        interval = max(300, int(settings.auto_recalibration_interval_seconds))
        if not settings.auto_recalibration_enabled:
            return
        while not self._shutdown_event.is_set():
            try:
                await run_auto_recalibration(
                    window_days=settings.auto_recalibration_window_days,
                    min_trades=settings.auto_recalibration_min_trades,
                    apply_changes=settings.auto_recalibration_apply_changes,
                    max_adjustment_pct=settings.auto_recalibration_max_adjustment_pct,
                )
            except Exception as exc:
                logger.debug(f"Auto recalibration skipped: {exc}")
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                continue

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
                continue

    async def _attempt_signal(self, signal: dict, config: dict, risk_mgr: RiskManager, paper_on: bool, label: str = "") -> bool:
        try:
            detected_at = signal.get("detected_at") or utcnow()
            signal["detected_at"] = detected_at
            decision_started = utcnow()
            can_trade, reason = await risk_mgr.can_trade(signal)
            if not can_trade:
                if label:
                    logger.info(f"{label} skipped {signal['market_id']}: {reason}")
                else:
                    logger.info(f"Signal skipped {signal['market_id']}: {reason}")
                return False

            sig_id = await insert_signal(signal)
            decision_finished = utcnow()
            signal["signal_id"] = sig_id
            signal["signal_recorded_at"] = decision_finished
            decision_latency = duration_ms(detected_at, decision_finished)
            if decision_latency is not None:
                await record_latency_event({
                    "signal_id": sig_id,
                    "market_id": signal["market_id"],
                    "signal_type": signal["signal_type"],
                    "stage": "signal_to_decision",
                    "duration_ms": decision_latency,
                    "started_at": detected_at,
                    "finished_at": decision_finished,
                    "details": {"label": label or "signal", "paper_mode": paper_on},
                })
            logger.info(
                f"{label or 'Signal'} #{sig_id} {signal['direction']} "
                f"edge={signal['edge']:.3f} kelly=${signal['kelly_size_usd']:.2f} "
                f"type={signal['signal_type']} conf={signal.get('confidence', 0.0):.2f}"
            )
            trade = None
            execution_started = utcnow()
            if paper_on and self._paper:
                trade = await self._paper.execute_signal(signal)
            else:
                trade = await self.executor.execute_signal(signal, config)
            execution_finished = utcnow()
            if trade:
                trade["signal_id"] = sig_id
                execution_latency = duration_ms(execution_started, execution_finished)
                if execution_latency is not None:
                    await record_latency_event({
                        "signal_id": sig_id,
                        "market_id": signal["market_id"],
                        "signal_type": signal["signal_type"],
                        "stage": "decision_to_execution",
                        "duration_ms": execution_latency,
                        "started_at": execution_started,
                        "finished_at": execution_finished,
                        "details": {"label": label or "signal", "paper_mode": paper_on, "order_status": trade.get("order_status")},
                    })
                signal_to_trade_latency = duration_ms(detected_at, execution_finished)
                if signal_to_trade_latency is not None:
                    await record_latency_event({
                        "signal_id": sig_id,
                        "market_id": signal["market_id"],
                        "signal_type": signal["signal_type"],
                        "stage": "signal_to_trade_recorded",
                        "duration_ms": signal_to_trade_latency,
                        "started_at": detected_at,
                        "finished_at": execution_finished,
                        "details": {"trade_id": trade.get("id"), "paper_mode": paper_on},
                    })
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
            "roda_enabled": config.get("roda_enabled", settings.roda_enabled),
            "roda_mode": config.get("roda_mode", settings.roda_mode),
            "roda_min_confidence": config.get("roda_min_confidence", settings.roda_min_confidence),
            "roda_min_age_hours": config.get("roda_min_age_hours", settings.roda_min_age_hours),
            "roda_max_age_hours": config.get("roda_max_age_hours", settings.roda_max_age_hours),
            "roda_max_entry_price": config.get("roda_max_entry_price", settings.roda_max_entry_price),
            "roda_min_sources": config.get("roda_min_sources", settings.roda_min_sources),
            "roda_hold_window_hours": config.get("roda_hold_window_hours", settings.roda_hold_window_hours),
            "roda_max_position_pct": config.get("roda_max_position_pct", settings.roda_max_position_pct),
            "roda_divergence_min_edge": config.get("roda_divergence_min_edge", settings.roda_divergence_min_edge),
            "roda_divergence_min_confidence": config.get("roda_divergence_min_confidence", settings.roda_divergence_min_confidence),
            "roda_divergence_min_sources": config.get("roda_divergence_min_sources", settings.roda_divergence_min_sources),
        }
        lch_config = {
            **config,
            "lch_enabled": config.get("lch_enabled", settings.lch_enabled),
            "lch_min_hours_to_resolve": config.get("lch_min_hours_to_resolve", settings.lch_min_hours_to_resolve),
            "lch_lookback_hours": config.get("lch_lookback_hours", settings.lch_lookback_hours),
            "lch_min_shock_magnitude": config.get("lch_min_shock_magnitude", settings.lch_min_shock_magnitude),
            "lch_min_z_score": config.get("lch_min_z_score", settings.lch_min_z_score),
            "lch_min_recovery_probability": config.get("lch_min_recovery_probability", settings.lch_min_recovery_probability),
            "lch_stop_loss_pct": config.get("lch_stop_loss_pct", settings.lch_stop_loss_pct),
            "lch_take_profit_pct_of_shock": config.get("lch_take_profit_pct_of_shock", settings.lch_take_profit_pct_of_shock),
            "lch_max_hold_minutes": config.get("lch_max_hold_minutes", settings.lch_max_hold_minutes),
            "lch_max_position_pct": config.get("lch_max_position_pct", settings.lch_max_position_pct),
            "lch_kelly_fraction": config.get("lch_kelly_fraction", settings.lch_kelly_fraction),
            "lch_min_position_size_usd": config.get("lch_min_position_size_usd", settings.lch_min_position_size_usd),
            "lch_max_position_size_usd": config.get("lch_max_position_size_usd", settings.lch_max_position_size_usd),
            "lch_max_daily_trades": config.get("lch_max_daily_trades", settings.lch_max_daily_trades),
            "lch_max_wash_trading_score": config.get("lch_max_wash_trading_score", settings.lch_max_wash_trading_score),
        }
        hybrid_config = {
            **config,
            "hybrid_enabled": config.get("hybrid_enabled", settings.hybrid_enabled),
        }
        mss2_config = {
            **config,
            "mss2_enabled": config.get("mss2_enabled", settings.mss2_enabled),
            "mss2_min_spread_bps": config.get("mss2_min_spread_bps", settings.mss2_min_spread_bps),
            "mss2_min_expected_profit_bps": config.get("mss2_min_expected_profit_bps", settings.mss2_min_expected_profit_bps),
            "mss2_max_adverse_selection_score": config.get("mss2_max_adverse_selection_score", settings.mss2_max_adverse_selection_score),
            "mss2_min_fill_probability_proxy": config.get("mss2_min_fill_probability_proxy", settings.mss2_min_fill_probability_proxy),
            "mss2_max_queue_pressure": config.get("mss2_max_queue_pressure", settings.mss2_max_queue_pressure),
        }

        async with PolymarketClient() as client:
            raw_list = await client.get_active_markets(limit=min(settings.max_markets_to_scan, 100))
            parsed = [client.parse_market(r) for r in raw_list]
            valid = [m for m in parsed if m.get("id")]
            try:
                await self.market_stream.update_watchlist(valid)
            except Exception as exc:
                logger.debug(f"Market stream watchlist update failed: {exc}")

            sentiment_map = await batch_sentiment(valid, api_key=settings.news_api_key)

            market_prices: dict[str, float] = {}
            roda_signals = await detect_roda_signals(
                valid,
                news_api_key=settings.news_api_key,
                divergence_sources_by_market={
                    **self._roda_divergence_sources,
                    **(config.get("roda_divergence_sources_by_market") if isinstance(config.get("roda_divergence_sources_by_market"), dict) else {}),
                } or None,
                config=roda_config,
                kelly_fraction=dyn_kelly,
                total_capital=capital,
            )
            arb_signals_preview = find_all_arb_signals(valid, capital)
            hybrid_signals = await detect_hybrid_signals(
                valid,
                roda_signals=roda_signals,
                arb_signals=arb_signals_preview,
                config=hybrid_config,
                kelly_fraction=dyn_kelly,
                total_capital=capital,
            )
            mss2_signals = await self.mss2_detector.detect_signals(
                valid,
                client=self.market_stream,
                config=mss2_config,
                kelly_fraction=dyn_kelly,
                total_capital=capital,
            )
            self._roda_latest_markets = list(valid)
            for signal in roda_signals:
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="RODA"):
                    signals_found += 1
                    strategic_market_ids.add(signal["market_id"])

            lch_signals = await self.lch_detector.detect_signals(
                valid,
                client=self.market_stream,
                config=lch_config,
                kelly_fraction=settings.lch_kelly_fraction,
                total_capital=capital,
            )
            for signal in lch_signals:
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="LCH"):
                    signals_found += 1
                    strategic_market_ids.add(signal["market_id"])

            for signal in hybrid_signals:
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="HYBRID"):
                    signals_found += 1
                    strategic_market_ids.add(signal["market_id"])

            for signal in mss2_signals:
                mss2_risk = await self.mss2_risk.assess_trade(signal, paper_mode=paper_on)
                if not mss2_risk.can_trade:
                    await notify_mss2_event(
                        "warning",
                        f"Blocked: {mss2_risk.reason}",
                        {"market_id": signal.get("market_id"), "signal_type": signal.get("signal_type")},
                    )
                    continue
                if mss2_risk.size_multiplier != 1.0:
                    signal = {
                        **signal,
                        "kelly_size_usd": signal["kelly_size_usd"] * mss2_risk.size_multiplier,
                        "mss2_size_multiplier": mss2_risk.size_multiplier,
                        "risk_level": mss2_risk.risk_level,
                    }
                if await self._attempt_signal(signal, config, risk_mgr, paper_on, label="MSS2"):
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

            for arb_sig in arb_signals_preview:
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
                await self.executor.reconcile_live_orders()
                if config.get("reconciliation_enabled", settings.reconciliation_enabled):
                    await self.executor.reconcile_live_balance(capital_usd=capital, config=config)

        self.scan_count += 1
        if self.scan_count % max(1, int(config.get("retention_scan_interval", 48))) == 0:
            try:
                await apply_retention_policy()
            except Exception as exc:
                logger.debug(f"Retention policy run skipped: {exc}")
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
