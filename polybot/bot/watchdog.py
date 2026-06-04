#!/usr/bin/env python3
"""External watchdog for bot liveness and dead-man alerts."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from bot.config import settings
from bot.notifications import send_telegram_alert
from bot.utils.db import ensure_schema, get_pool, log_entry, update_bot_state


async def check_once(timeout_seconds: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT state, updated_at, pid, markets_scanned FROM bot_state ORDER BY id LIMIT 1")
    if not row:
        await send_telegram_alert("warning", "Watchdog", "No bot_state row found", {})
        return False

    updated_at = row["updated_at"]
    if updated_at is None:
        stale = True
    else:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        stale = (datetime.now(timezone.utc) - updated_at).total_seconds() > timeout_seconds

    if stale:
        await send_telegram_alert(
            "error",
            "Dead man's switch triggered",
            f"Bot heartbeat is stale for more than {timeout_seconds}s",
            {"state": row["state"], "pid": row["pid"], "markets_scanned": row["markets_scanned"], "updated_at": str(row["updated_at"])},
        )
        await log_entry("watchdog", "error", "Bot heartbeat stale", {"timeout_seconds": timeout_seconds})
        await update_bot_state("error", error_message="Watchdog heartbeat stale")
        return False

    logger.info("Watchdog OK: bot heartbeat fresh")
    return True


async def main() -> None:
    await ensure_schema()
    timeout_seconds = int(settings.watchdog_timeout_seconds)
    logger.info("Starting watchdog with timeout={}s", timeout_seconds)
    while True:
        await check_once(timeout_seconds)
        await asyncio.sleep(max(5, timeout_seconds // 3))


if __name__ == "__main__":
    asyncio.run(main())
