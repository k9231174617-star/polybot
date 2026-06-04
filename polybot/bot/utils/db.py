"""Database utilities for the bot — uses asyncpg for async access."""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from bot.config import settings

_pool: Optional[asyncpg.Pool] = None

BOT_CONFIG_DEFAULTS: dict[str, Any] = {
    "edge_threshold": 0.05,
    "max_position_pct": 0.05,
    "daily_loss_limit_pct": 0.03,
    "kelly_fraction": 0.25,
    "scan_interval_seconds": 30,
    "use_limit_orders": True,
    "min_liquidity_usd": 1000,
    "max_correlated_exposure_pct": 0.15,
    "paper_trading": True,
    "paper_capital_usd": 1000,
    "retention_scan_interval": 48,
    "reconciliation_enabled": True,
    "reconciliation_warning_pct": 0.01,
    "reconciliation_critical_pct": 0.03,
    "reconciliation_warning_usd": 5.0,
    "reconciliation_critical_usd": 25.0,
    "auto_recalibration_enabled": False,
    "auto_recalibration_interval_seconds": 3600,
    "auto_recalibration_window_days": 14,
    "auto_recalibration_min_trades": 20,
    "auto_recalibration_apply_changes": False,
    "auto_recalibration_max_adjustment_pct": 0.15,
    "roda_enabled": True,
    "roda_mode": "auto",
    "lch_enabled": True,
    "hybrid_enabled": True,
    "mss2_enabled": True,
    "roda_min_confidence": 0.95,
    "roda_min_sources": 3,
    "roda_divergence_min_edge": 0.06,
    "roda_divergence_min_confidence": 0.60,
    "roda_divergence_min_sources": 2,
    "lch_min_z_score": 2.5,
    "lch_min_recovery_probability": 0.70,
    "lch_max_wash_trading_score": 0.72,
    "mss2_min_spread_bps": 35.0,
    "mss2_min_expected_profit_bps": 35.0,
    "mss2_max_adverse_selection_score": 0.65,
    "mss2_min_fill_probability_proxy": 0.30,
    "mss2_max_queue_pressure": 0.75,
}

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS bot_state (
        id SERIAL PRIMARY KEY,
        state TEXT NOT NULL DEFAULT 'stopped',
        started_at TIMESTAMP,
        markets_scanned INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        pid INTEGER,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bot_config (
        id SERIAL PRIMARY KEY,
        edge_threshold REAL NOT NULL DEFAULT 0.05,
        max_position_pct REAL NOT NULL DEFAULT 0.05,
        daily_loss_limit_pct REAL NOT NULL DEFAULT 0.03,
        kelly_fraction REAL NOT NULL DEFAULT 0.25,
        scan_interval_seconds INTEGER NOT NULL DEFAULT 30,
        use_limit_orders BOOLEAN NOT NULL DEFAULT TRUE,
        min_liquidity_usd REAL NOT NULL DEFAULT 1000,
        max_correlated_exposure_pct REAL NOT NULL DEFAULT 0.15,
        paper_trading BOOLEAN NOT NULL DEFAULT TRUE,
        paper_capital_usd REAL NOT NULL DEFAULT 1000,
        retention_scan_interval INTEGER NOT NULL DEFAULT 48,
        reconciliation_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        reconciliation_warning_pct REAL NOT NULL DEFAULT 0.01,
        reconciliation_critical_pct REAL NOT NULL DEFAULT 0.03,
        reconciliation_warning_usd REAL NOT NULL DEFAULT 5.0,
        reconciliation_critical_usd REAL NOT NULL DEFAULT 25.0,
        auto_recalibration_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        auto_recalibration_interval_seconds INTEGER NOT NULL DEFAULT 3600,
        auto_recalibration_window_days INTEGER NOT NULL DEFAULT 14,
        auto_recalibration_min_trades INTEGER NOT NULL DEFAULT 20,
        auto_recalibration_apply_changes BOOLEAN NOT NULL DEFAULT FALSE,
        auto_recalibration_max_adjustment_pct REAL NOT NULL DEFAULT 0.15,
        roda_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        roda_mode TEXT NOT NULL DEFAULT 'auto',
        lch_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        mss2_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        roda_min_confidence REAL NOT NULL DEFAULT 0.95,
        roda_min_sources INTEGER NOT NULL DEFAULT 3,
        roda_divergence_min_edge REAL NOT NULL DEFAULT 0.06,
        roda_divergence_min_confidence REAL NOT NULL DEFAULT 0.60,
        roda_divergence_min_sources INTEGER NOT NULL DEFAULT 2,
        lch_min_z_score REAL NOT NULL DEFAULT 2.5,
        lch_min_recovery_probability REAL NOT NULL DEFAULT 0.70,
        lch_max_wash_trading_score REAL NOT NULL DEFAULT 0.72,
        mss2_min_spread_bps REAL NOT NULL DEFAULT 35.0,
        mss2_min_expected_profit_bps REAL NOT NULL DEFAULT 35.0,
        mss2_max_adverse_selection_score REAL NOT NULL DEFAULT 0.65,
        mss2_min_fill_probability_proxy REAL NOT NULL DEFAULT 0.30,
        mss2_max_queue_pressure REAL NOT NULL DEFAULT 0.75,
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_mode TEXT NOT NULL DEFAULT 'auto'
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_min_confidence REAL NOT NULL DEFAULT 0.95
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_min_sources INTEGER NOT NULL DEFAULT 3
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_edge REAL NOT NULL DEFAULT 0.06
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_confidence REAL NOT NULL DEFAULT 0.60
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_sources INTEGER NOT NULL DEFAULT 2
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_min_z_score REAL NOT NULL DEFAULT 2.5
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_min_recovery_probability REAL NOT NULL DEFAULT 0.70
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_max_wash_trading_score REAL NOT NULL DEFAULT 0.72
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_spread_bps REAL NOT NULL DEFAULT 35.0
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_expected_profit_bps REAL NOT NULL DEFAULT 35.0
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_max_adverse_selection_score REAL NOT NULL DEFAULT 0.65
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_fill_probability_proxy REAL NOT NULL DEFAULT 0.30
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_max_queue_pressure REAL NOT NULL DEFAULT 0.75
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS retention_scan_interval INTEGER NOT NULL DEFAULT 48
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS reconciliation_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS reconciliation_warning_pct REAL NOT NULL DEFAULT 0.01
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS reconciliation_critical_pct REAL NOT NULL DEFAULT 0.03
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS reconciliation_warning_usd REAL NOT NULL DEFAULT 5.0
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS reconciliation_critical_usd REAL NOT NULL DEFAULT 25.0
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_enabled BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_interval_seconds INTEGER NOT NULL DEFAULT 3600
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_window_days INTEGER NOT NULL DEFAULT 14
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_min_trades INTEGER NOT NULL DEFAULT 20
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_apply_changes BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS auto_recalibration_max_adjustment_pct REAL NOT NULL DEFAULT 0.15
    """,
    """
    CREATE TABLE IF NOT EXISTS markets (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        category TEXT DEFAULT '',
        market_price REAL NOT NULL,
        model_probability REAL,
        edge REAL,
        volume_24h REAL NOT NULL DEFAULT 0,
        liquidity_usd REAL NOT NULL DEFAULT 0,
        sentiment_score REAL,
        end_date TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'active',
        last_updated TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        side TEXT NOT NULL,
        size_usd REAL NOT NULL,
        entry_price REAL NOT NULL,
        current_price REAL NOT NULL,
        unrealized_pnl REAL NOT NULL DEFAULT 0,
        unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
        entry_edge REAL NOT NULL DEFAULT 0,
        current_edge REAL,
        order_id TEXT,
        order_status TEXT NOT NULL DEFAULT 'open',
        filled_size_usd REAL NOT NULL DEFAULT 0,
        remaining_size_usd REAL NOT NULL DEFAULT 0,
        opened_at TIMESTAMP DEFAULT NOW(),
        closed_at TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'open'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        direction TEXT NOT NULL,
        market_price REAL NOT NULL,
        model_probability REAL NOT NULL,
        edge REAL NOT NULL,
        kelly_size_usd REAL NOT NULL,
        confidence REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        detected_at TIMESTAMP DEFAULT NOW(),
        acted_at TIMESTAMP,
        details JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        signal_id INTEGER,
        side TEXT NOT NULL,
        action TEXT NOT NULL,
        size_usd REAL NOT NULL,
        price REAL NOT NULL,
        slippage REAL NOT NULL DEFAULT 0,
        fee_usd REAL NOT NULL DEFAULT 0,
        realized_pnl REAL,
        tx_hash TEXT,
        order_id TEXT,
        order_status TEXT NOT NULL DEFAULT 'filled',
        filled_size_usd REAL NOT NULL DEFAULT 0,
        remaining_size_usd REAL NOT NULL DEFAULT 0,
        executed_at TIMESTAMP DEFAULT NOW(),
        order_type TEXT NOT NULL DEFAULT 'market'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pnl_snapshots (
        id SERIAL PRIMARY KEY,
        cumulative_pnl REAL NOT NULL,
        portfolio_value REAL NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS log_entries (
        id SERIAL PRIMARY KEY,
        level TEXT NOT NULL,
        module TEXT NOT NULL,
        message TEXT NOT NULL,
        details JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS latency_events (
        id SERIAL PRIMARY KEY,
        signal_id INTEGER,
        market_id TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        duration_ms REAL NOT NULL,
        started_at TIMESTAMP NOT NULL,
        finished_at TIMESTAMP NOT NULL,
        details JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_positions (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        side TEXT NOT NULL,
        size_usd REAL NOT NULL,
        entry_price REAL NOT NULL,
        current_price REAL NOT NULL,
        unrealized_pnl REAL NOT NULL DEFAULT 0,
        unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
        entry_edge REAL NOT NULL DEFAULT 0,
        signal_type TEXT NOT NULL DEFAULT 'price_discrepancy',
        confidence REAL NOT NULL DEFAULT 0,
        opened_at TIMESTAMP DEFAULT NOW(),
        closed_at TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'open'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_trades (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        signal_id INTEGER,
        side TEXT NOT NULL,
        action TEXT NOT NULL,
        size_usd REAL NOT NULL,
        price REAL NOT NULL,
        slippage REAL NOT NULL DEFAULT 0,
        fee_usd REAL NOT NULL DEFAULT 0,
        realized_pnl REAL,
        signal_type TEXT NOT NULL DEFAULT 'price_discrepancy',
        order_id TEXT,
        order_status TEXT NOT NULL DEFAULT 'filled',
        filled_size_usd REAL NOT NULL DEFAULT 0,
        remaining_size_usd REAL NOT NULL DEFAULT 0,
        executed_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_pnl_snapshots (
        id SERIAL PRIMARY KEY,
        cumulative_pnl REAL NOT NULL,
        portfolio_value REAL NOT NULL,
        win_rate REAL NOT NULL DEFAULT 0,
        total_trades INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS balance_reconciliation_snapshots (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL DEFAULT 'live',
        live_collateral_balance REAL NOT NULL DEFAULT 0,
        internal_cash_estimate REAL NOT NULL DEFAULT 0,
        internal_equity_estimate REAL NOT NULL DEFAULT 0,
        discrepancy_usd REAL NOT NULL DEFAULT 0,
        discrepancy_pct REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ok',
        details JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    ALTER TABLE trades ADD COLUMN IF NOT EXISTS signal_id INTEGER
    """,
    """
    ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_id TEXT
    """,
    """
    ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_status TEXT NOT NULL DEFAULT 'filled'
    """,
    """
    ALTER TABLE trades ADD COLUMN IF NOT EXISTS filled_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE trades ADD COLUMN IF NOT EXISTS remaining_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS signal_id INTEGER
    """,
    """
    ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS order_id TEXT
    """,
    """
    ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS order_status TEXT NOT NULL DEFAULT 'filled'
    """,
    """
    ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS filled_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS remaining_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE signals ADD COLUMN IF NOT EXISTS details JSONB
    """,
    """
    ALTER TABLE positions ADD COLUMN IF NOT EXISTS order_id TEXT
    """,
    """
    ALTER TABLE positions ADD COLUMN IF NOT EXISTS order_status TEXT NOT NULL DEFAULT 'open'
    """,
    """
    ALTER TABLE positions ADD COLUMN IF NOT EXISTS filled_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE positions ADD COLUMN IF NOT EXISTS remaining_size_usd REAL NOT NULL DEFAULT 0
    """,
    """
    CREATE INDEX IF NOT EXISTS balance_reconciliation_created_at_idx ON balance_reconciliation_snapshots (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS bot_state_state_updated_at_idx ON bot_state (state, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS bot_config_updated_at_idx ON bot_config (updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS markets_status_end_date_idx ON markets (status, end_date DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS markets_category_last_updated_idx ON markets (category, last_updated DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS positions_status_market_id_idx ON positions (status, market_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS positions_order_id_idx ON positions (order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS signals_status_detected_at_idx ON signals (status, detected_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS signals_market_id_idx ON signals (market_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS trades_order_id_idx ON trades (order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS trades_status_executed_at_idx ON trades (order_status, executed_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS trades_market_id_idx ON trades (market_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS trades_signal_id_idx ON trades (signal_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS latency_events_created_at_idx ON latency_events (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS latency_events_stage_created_at_idx ON latency_events (stage, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS latency_events_signal_type_created_at_idx ON latency_events (signal_type, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_positions_status_opened_at_idx ON paper_positions (status, opened_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_positions_market_id_idx ON paper_positions (market_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_trades_order_id_idx ON paper_trades (order_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_trades_signal_type_executed_at_idx ON paper_trades (signal_type, executed_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_trades_signal_id_idx ON paper_trades (signal_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS log_entries_created_at_idx ON log_entries (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS pnl_snapshots_created_at_idx ON pnl_snapshots (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS paper_pnl_snapshots_created_at_idx ON paper_pnl_snapshots (created_at DESC)
    """,
)

DEFAULT_BOT_CONFIG_SQL = """
    INSERT INTO bot_config (
        edge_threshold,
        max_position_pct,
        daily_loss_limit_pct,
        kelly_fraction,
        scan_interval_seconds,
        use_limit_orders,
        min_liquidity_usd,
        max_correlated_exposure_pct,
        paper_trading,
        paper_capital_usd,
        retention_scan_interval,
        reconciliation_enabled,
        reconciliation_warning_pct,
        reconciliation_critical_pct,
        reconciliation_warning_usd,
        reconciliation_critical_usd,
        auto_recalibration_enabled,
        auto_recalibration_interval_seconds,
        auto_recalibration_window_days,
        auto_recalibration_min_trades,
        auto_recalibration_apply_changes,
        auto_recalibration_max_adjustment_pct,
        roda_enabled,
        roda_mode,
        lch_enabled,
        hybrid_enabled,
        mss2_enabled,
        roda_min_confidence,
        roda_min_sources,
        roda_divergence_min_edge,
        roda_divergence_min_confidence,
        roda_divergence_min_sources,
        lch_min_z_score,
        lch_min_recovery_probability,
        lch_max_wash_trading_score,
        mss2_min_spread_bps,
        mss2_min_expected_profit_bps,
        mss2_max_adverse_selection_score,
        mss2_min_fill_probability_proxy,
        mss2_max_queue_pressure
    )
    SELECT
        0.05, 0.05, 0.03, 0.25, 30, TRUE, 1000, 0.15, TRUE, 1000, 48, TRUE, 0.01, 0.03, 5.0, 25.0, FALSE, 3600, 14, 20, FALSE, 0.15, TRUE, 'auto', TRUE, TRUE, TRUE,
        0.95, 3, 0.06, 0.60, 2, 2.5, 0.70, 0.72, 35.0, 35.0, 0.65, 0.30, 0.75
    WHERE NOT EXISTS (SELECT 1 FROM bot_config)
"""


async def _create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=5,
        command_timeout=5,
        timeout=10,
        server_settings={
            "application_name": "polybot",
            "statement_timeout": "5000",
            "idle_in_transaction_session_timeout": "10000",
        },
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(value: Any) -> Any:
    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.replace(tzinfo=None)
    return value


async def apply_retention_policy() -> dict[str, int]:
    """Delete old rows according to configured retention windows."""
    pool = await get_pool()
    stats = {
        "log_entries": 0,
        "pnl_snapshots": 0,
        "paper_pnl_snapshots": 0,
        "signals": 0,
        "latency_events": 0,
        "trades": 0,
        "paper_trades": 0,
        "positions": 0,
        "paper_positions": 0,
        "markets": 0,
    }
    now = _utc_now()
    log_cutoff = now - timedelta(days=max(1, int(getattr(settings, "log_retention_days", 30))))
    snapshot_cutoff = now - timedelta(days=max(30, int(getattr(settings, "snapshot_retention_days", 365))))
    trade_cutoff = now - timedelta(days=max(30, int(getattr(settings, "trade_retention_days", 730))))
    signal_cutoff = now - timedelta(days=max(30, int(getattr(settings, "signal_retention_days", 365))))
    market_cutoff = now - timedelta(days=max(30, int(getattr(settings, "market_retention_days", 180))))
    latency_cutoff = now - timedelta(days=max(7, int(getattr(settings, "latency_retention_days", 30))))

    async with pool.acquire() as conn:
        stats["log_entries"] = _rows_affected(await conn.execute(
            "DELETE FROM log_entries WHERE created_at < $1",
            log_cutoff.replace(tzinfo=None),
        ))
        stats["pnl_snapshots"] = _rows_affected(await conn.execute(
            "DELETE FROM pnl_snapshots WHERE created_at < $1",
            snapshot_cutoff.replace(tzinfo=None),
        ))
        stats["paper_pnl_snapshots"] = _rows_affected(await conn.execute(
            "DELETE FROM paper_pnl_snapshots WHERE created_at < $1",
            snapshot_cutoff.replace(tzinfo=None),
        ))
        stats["signals"] = _rows_affected(await conn.execute(
            "DELETE FROM signals WHERE detected_at < $1 AND status IN ('pending','acted')",
            signal_cutoff.replace(tzinfo=None),
        ))
        stats["latency_events"] = _rows_affected(await conn.execute(
            "DELETE FROM latency_events WHERE created_at < $1",
            latency_cutoff.replace(tzinfo=None),
        ))
        stats["trades"] = _rows_affected(await conn.execute(
            "DELETE FROM trades WHERE executed_at < $1",
            trade_cutoff.replace(tzinfo=None),
        ))
        stats["paper_trades"] = _rows_affected(await conn.execute(
            "DELETE FROM paper_trades WHERE executed_at < $1",
            trade_cutoff.replace(tzinfo=None),
        ))
        stats["positions"] = _rows_affected(await conn.execute(
            "DELETE FROM positions WHERE status = 'closed' AND closed_at IS NOT NULL AND closed_at < $1",
            trade_cutoff.replace(tzinfo=None),
        ))
        stats["paper_positions"] = _rows_affected(await conn.execute(
            "DELETE FROM paper_positions WHERE status = 'closed' AND closed_at IS NOT NULL AND closed_at < $1",
            trade_cutoff.replace(tzinfo=None),
        ))
        stats["markets"] = _rows_affected(await conn.execute(
            "DELETE FROM markets WHERE status IN ('resolved','blocked') AND last_updated < $1",
            market_cutoff.replace(tzinfo=None),
        ))
    return stats


def _rows_affected(status: str) -> int:
    try:
        return int(status.split()[-1])
    except Exception:
        return 0


async def insert_balance_reconciliation(snapshot: dict[str, Any]) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        import json
        row = await conn.fetchrow(
            """
            INSERT INTO balance_reconciliation_snapshots
              (source, live_collateral_balance, internal_cash_estimate, internal_equity_estimate,
               discrepancy_usd, discrepancy_pct, status, details, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            RETURNING id
            """,
            snapshot.get("source", "live"),
            snapshot.get("live_collateral_balance", 0.0),
            snapshot.get("internal_cash_estimate", 0.0),
            snapshot.get("internal_equity_estimate", 0.0),
            snapshot.get("discrepancy_usd", 0.0),
            snapshot.get("discrepancy_pct", 0.0),
            snapshot.get("status", "ok"),
            json.dumps(snapshot.get("details")) if snapshot.get("details") is not None else None,
        )
        return int(row["id"])


async def record_latency_event(event: dict[str, Any]) -> int:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            import json
            row = await conn.fetchrow(
                """
                INSERT INTO latency_events
                  (signal_id, market_id, signal_type, stage, duration_ms, started_at, finished_at, details, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                RETURNING id
                """,
                event.get("signal_id"),
                event["market_id"],
                event["signal_type"],
                event["stage"],
                event["duration_ms"],
                _naive_utc(event["started_at"]),
                _naive_utc(event["finished_at"]),
                json.dumps(event.get("details")) if event.get("details") is not None else None,
            )
            return int(row["id"])
    except Exception as exc:
        logger.debug(f"Latency event write skipped: {exc}")
        return 0


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        retryable = (
            OSError,
            TimeoutError,
            ConnectionError,
            asyncpg.PostgresError,
        )
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential_jitter(initial=1, max=10),
            retry=retry_if_exception_type(retryable),
            reraise=True,
        ):
            with attempt:
                _pool = await _create_pool()
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def ensure_schema():
    """Create the minimal bot schema on first boot."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(statement)
        await conn.execute(DEFAULT_BOT_CONFIG_SQL)


async def log_entry(module: str, level: str, message: str, details: Optional[dict] = None):
    """Write a log entry to the database."""
    try:
        pool = await get_pool()
        import json
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO log_entries (level, module, message, details, created_at)
                   VALUES ($1, $2, $3, $4, NOW())""",
                level, module, message,
                json.dumps(details) if details else None
            )
    except Exception as e:
        logger.error(f"Failed to write log to DB: {e}")


async def update_bot_state(state: str, markets_scanned: Optional[int] = None,
                            error_message: Optional[str] = None, pid: Optional[int] = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM bot_state LIMIT 1")
        if existing:
            sets = ["state = $1", "updated_at = NOW()"]
            vals: list[Any] = [state]
            idx = 2
            if markets_scanned is not None:
                sets.append(f"markets_scanned = ${idx}")
                vals.append(markets_scanned)
                idx += 1
            if error_message is not None:
                sets.append(f"error_message = ${idx}")
                vals.append(error_message)
                idx += 1
            if pid is not None:
                sets.append(f"pid = ${idx}")
                vals.append(pid)
                idx += 1
            if state == "running":
                sets.append("started_at = NOW()")
            await conn.execute(
                f"UPDATE bot_state SET {', '.join(sets)} WHERE id = ${ idx }",
                *vals, existing["id"]
            )
        else:
            await conn.execute(
                """INSERT INTO bot_state (state, started_at, markets_scanned, error_message, pid, updated_at)
                   VALUES ($1, CASE WHEN $1='running' THEN NOW() ELSE NULL END, $2, $3, $4, NOW())""",
                state, markets_scanned or 0, error_message, pid
            )


async def upsert_market(market: dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO markets (id, question, category, market_price, model_probability, edge,
                                 volume_24h, liquidity_usd, end_date, status, last_updated)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (id) DO UPDATE SET
                market_price = EXCLUDED.market_price,
                model_probability = EXCLUDED.model_probability,
                edge = EXCLUDED.edge,
                volume_24h = EXCLUDED.volume_24h,
                liquidity_usd = EXCLUDED.liquidity_usd,
                status = EXCLUDED.status,
                last_updated = NOW()
        """,
            market["id"], market["question"], market.get("category", ""),
            market["market_price"], market.get("model_probability"),
            market.get("edge"), market.get("volume_24h", 0),
            market.get("liquidity_usd", 0), market.get("end_date"),
            market.get("status", "active")
        )


async def insert_signal(signal: dict) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        core_fields = {
            "market_id",
            "market_question",
            "signal_type",
            "direction",
            "market_price",
            "model_probability",
            "edge",
            "kelly_size_usd",
            "confidence",
            "status",
            "detected_at",
            "acted_at",
            "signal_id",
            "details",
        }
        details = signal.get("details")
        if details is None:
            details = {key: value for key, value in signal.items() if key not in core_fields and value is not None}
        row = await conn.fetchrow("""
            INSERT INTO signals (market_id, market_question, signal_type, direction,
                                  market_price, model_probability, edge, kelly_size_usd,
                                  confidence, status, detected_at, details)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', COALESCE($10, NOW()), $11)
            RETURNING id
        """,
            signal["market_id"], signal["market_question"], signal["signal_type"],
            signal["direction"], signal["market_price"], signal["model_probability"],
            signal["edge"], signal["kelly_size_usd"], signal.get("confidence", 0.5),
            _naive_utc(signal.get("detected_at")),
            json.dumps(details, default=str) if details else None,
        )
        return row["id"]


async def insert_trade(trade: dict) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO trades (market_id, market_question, signal_id, side, action, size_usd, price,
                                 slippage, fee_usd, realized_pnl, tx_hash, order_id, order_status,
                                 filled_size_usd, remaining_size_usd, executed_at, order_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW(), $16)
            RETURNING id
        """,
            trade["market_id"], trade["market_question"], trade.get("signal_id"),
            trade["side"], trade["action"], trade["size_usd"], trade["price"], trade.get("slippage", 0),
            trade.get("fee_usd", 0), trade.get("realized_pnl"),
            trade.get("tx_hash"), trade.get("order_id"), trade.get("order_status", "filled"),
            trade.get("filled_size_usd", trade["size_usd"]), trade.get("remaining_size_usd", 0),
            trade.get("order_type", "market")
        )
        return row["id"]


async def get_bot_config() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bot_config LIMIT 1")
        if not row:
            return dict(BOT_CONFIG_DEFAULTS)
        config = dict(BOT_CONFIG_DEFAULTS)
        config.update({key: value for key, value in dict(row).items() if value is not None})
        return config


async def update_bot_config(patch: dict[str, Any]) -> dict:
    if not patch:
        return await get_bot_config()
    pool = await get_pool()
    allowed = {
        "edge_threshold",
        "max_position_pct",
        "daily_loss_limit_pct",
        "kelly_fraction",
        "scan_interval_seconds",
        "use_limit_orders",
        "min_liquidity_usd",
        "max_correlated_exposure_pct",
        "paper_trading",
        "paper_capital_usd",
        "retention_scan_interval",
        "reconciliation_enabled",
        "reconciliation_warning_pct",
        "reconciliation_critical_pct",
        "reconciliation_warning_usd",
        "reconciliation_critical_usd",
        "auto_recalibration_enabled",
        "auto_recalibration_interval_seconds",
        "auto_recalibration_window_days",
        "auto_recalibration_min_trades",
        "auto_recalibration_apply_changes",
        "auto_recalibration_max_adjustment_pct",
        "roda_enabled",
        "lch_enabled",
        "hybrid_enabled",
        "mss2_enabled",
        "roda_min_confidence",
        "roda_min_sources",
        "roda_divergence_min_edge",
        "roda_divergence_min_confidence",
        "roda_divergence_min_sources",
        "lch_min_z_score",
        "lch_min_recovery_probability",
        "lch_max_wash_trading_score",
        "mss2_min_spread_bps",
        "mss2_min_expected_profit_bps",
        "mss2_max_adverse_selection_score",
        "mss2_min_fill_probability_proxy",
        "mss2_max_queue_pressure",
        "roda_mode",
    }
    patch = {key: value for key, value in patch.items() if key in allowed}
    if not patch:
        return await get_bot_config()

    assignments = []
    values: list[Any] = []
    idx = 1
    for key, value in patch.items():
        assignments.append(f"{key} = ${idx}")
        values.append(value)
        idx += 1
    assignments.append(f"updated_at = ${idx}")
    values.append(_utc_now())

    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM bot_config ORDER BY id LIMIT 1")
        if existing:
            await conn.execute(
                f"UPDATE bot_config SET {', '.join(assignments)} WHERE id = ${idx + 1}",
                *values,
                existing["id"],
            )
        else:
            columns = ", ".join(list(patch.keys()) + ["updated_at"])
            placeholders = ", ".join(f"${i}" for i in range(1, len(patch) + 2))
            await conn.execute(
                f"INSERT INTO bot_config ({columns}) VALUES ({placeholders})",
                *values,
            )
    return await get_bot_config()


async def snapshot_pnl(cumulative_pnl: float, portfolio_value: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pnl_snapshots (cumulative_pnl, portfolio_value, created_at) VALUES ($1, $2, NOW())",
            cumulative_pnl, portfolio_value
        )
