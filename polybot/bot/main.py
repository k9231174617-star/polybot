#!/usr/bin/env python3
"""
Polymarket Trading Bot — Entry Point

Usage:
    python -m bot.main

Environment variables (see bot/config.py for full list):
    DATABASE_URL        — PostgreSQL connection string (required)
    DRY_RUN             — Set to "false" to enable live trading (default: true)
    INITIAL_CAPITAL_USD — Starting capital in USD (default: 1000)
    POLYMARKET_PRIVATE_KEY — Wallet private key (required for live trading)

The bot writes state, signals, trades, and logs to PostgreSQL.
The dashboard reads from the same database via the API server.
"""
import asyncio
import sys
import signal as signal_module
import os

from loguru import logger
from bot.core.bot import PolymarketBot
from bot.config import settings


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    logger.add(
        "bot/logs/bot.log",
        rotation="50 MB",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
    )


async def main():
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("  POLYMARKET TRADING BOT")
    logger.info(f"  Dry Run: {settings.dry_run}")
    logger.info(f"  Capital: ${settings.initial_capital_usd:,.2f}")
    logger.info(f"  Max Markets: {settings.max_markets_to_scan}")
    logger.info("=" * 60)

    bot = PolymarketBot()

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        bot.stop()

    signal_module.signal(signal_module.SIGINT, shutdown_handler)
    signal_module.signal(signal_module.SIGTERM, shutdown_handler)

    await bot.start()
    logger.info("Bot shut down cleanly.")


if __name__ == "__main__":
    # Create logs directory
    os.makedirs("bot/logs", exist_ok=True)
    asyncio.run(main())
