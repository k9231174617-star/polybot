"""Lightweight MSS2 notifications."""
from __future__ import annotations

from typing import Any

from loguru import logger

from bot.utils.db import log_entry


async def notify_mss2_event(level: str, message: str, details: dict[str, Any] | None = None) -> None:
    payload = details or {}
    await log_entry("mss2", level, message, payload)
    logger.log(level.upper() if level else "INFO", f"[MSS2] {message}")
