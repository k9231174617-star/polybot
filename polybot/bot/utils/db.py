"""Database utilities for the bot — uses asyncpg for async access."""
from typing import Any, Optional

import asyncpg
from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from bot.config import settings

_pool: Optional[asyncpg.Pool] = None

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
        updated_at TIMESTAMP DEFAULT NOW()
    )
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
        acted_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id SERIAL PRIMARY KEY,
        market_id TEXT NOT NULL,
        market_question TEXT NOT NULL,
        side TEXT NOT NULL,
        action TEXT NOT NULL,
        size_usd REAL NOT NULL,
        price REAL NOT NULL,
        slippage REAL NOT NULL DEFAULT 0,
        fee_usd REAL NOT NULL DEFAULT 0,
        realized_pnl REAL,
        tx_hash TEXT,
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
        side TEXT NOT NULL,
        action TEXT NOT NULL,
        size_usd REAL NOT NULL,
        price REAL NOT NULL,
        slippage REAL NOT NULL DEFAULT 0,
        fee_usd REAL NOT NULL DEFAULT 0,
        realized_pnl REAL,
        signal_type TEXT NOT NULL DEFAULT 'price_discrepancy',
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
        paper_capital_usd
    )
    SELECT
        0.05, 0.05, 0.03, 0.25, 30, TRUE, 1000, 0.15, TRUE, 1000
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
        row = await conn.fetchrow("""
            INSERT INTO signals (market_id, market_question, signal_type, direction,
                                  market_price, model_probability, edge, kelly_size_usd,
                                  confidence, status, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', NOW())
            RETURNING id
        """,
            signal["market_id"], signal["market_question"], signal["signal_type"],
            signal["direction"], signal["market_price"], signal["model_probability"],
            signal["edge"], signal["kelly_size_usd"], signal.get("confidence", 0.5)
        )
        return row["id"]


async def insert_trade(trade: dict) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO trades (market_id, market_question, side, action, size_usd, price,
                                 slippage, fee_usd, realized_pnl, tx_hash, executed_at, order_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), $11)
            RETURNING id
        """,
            trade["market_id"], trade["market_question"], trade["side"], trade["action"],
            trade["size_usd"], trade["price"], trade.get("slippage", 0),
            trade.get("fee_usd", 0), trade.get("realized_pnl"),
            trade.get("tx_hash"), trade.get("order_type", "market")
        )
        return row["id"]


async def get_bot_config() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bot_config LIMIT 1")
        if not row:
            return {
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
            }
        return dict(row)


async def snapshot_pnl(cumulative_pnl: float, portfolio_value: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pnl_snapshots (cumulative_pnl, portfolio_value, created_at) VALUES ($1, $2, NOW())",
            cumulative_pnl, portfolio_value
        )
