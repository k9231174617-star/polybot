"""Telegram alerts for critical bot events."""
from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from bot.config import settings
from bot.utils.db import log_entry


async def send_telegram_alert(level: str, title: str, message: str, details: dict[str, Any] | None = None) -> None:
    payload = details or {}
    await log_entry("alerts", level, title, {"message": message, **payload})

    if not settings.alerts_enabled:
        return
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("Telegram alerts are not configured")
        return

    text = f"*{title}*\n{message}"
    if payload:
        text += "\n\n" + "\n".join(f"`{k}`: `{v}`" for k, v in payload.items())

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    recipients = [settings.telegram_chat_id]
    if level.lower() in {"error", "critical"} and settings.telegram_critical_chat_id:
        if settings.telegram_critical_chat_id not in recipients:
            recipients.append(settings.telegram_critical_chat_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in recipients:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
            if response.status_code >= 400:
                logger.error("Failed to send Telegram alert: {}", response.text)
