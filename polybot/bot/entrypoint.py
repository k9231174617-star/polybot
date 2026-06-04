"""Runtime entrypoint that can launch the trading bot or the watchdog."""
from __future__ import annotations

import asyncio

from loguru import logger

from bot.config import settings
from bot.main import main as run_bot
from bot.watchdog import main as run_watchdog


async def main() -> None:
    mode = str(getattr(settings, "bot_mode", "bot")).strip().lower()
    logger.info("Bot entrypoint starting in mode={}", mode)

    if mode in {"watchdog", "deadman", "dead-man"}:
        await run_watchdog()
        return

    if mode not in {"bot", "trade", "trading"}:
        logger.warning("Unknown BOT_MODE={!r}; defaulting to bot", mode)

    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
