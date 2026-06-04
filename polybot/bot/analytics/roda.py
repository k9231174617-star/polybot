"""Resolution Lag Arb detector — confirmation on unresolved markets."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from bot.analytics.engine import AnalyticsEngine
from bot.data.news import fetch_news_articles

_STOPWORDS = {
    "will", "the", "a", "an", "be", "is", "in", "on", "at", "to", "by", "of", "for",
    "and", "or", "with", "has", "have", "do", "does", "before", "after", "end",
    "year", "2024", "2025", "2026", "2027", "2028", "market", "polymarket", "yes", "no",
}

_CONFIRM_POS = {
    "won", "wins", "win", "elected", "election", "approved", "passes", "passed", "pass",
    "launched", "launches", "signed", "signs", "confirmed", "confirm", "reached",
    "achieved", "record", "victory", "victorious", "called", "declared", "accepted",
    "adopted", "finalized", "settled", "resolved", "convicted", "charged",
}

_CONFIRM_NEG = {
    "lost", "loses", "lose", "rejected", "rejects", "failed", "fails", "cancelled", "canceled",
    "delayed", "postponed", "blocked", "denied", "denies", "defeated", "defeat", "lower",
    "drop", "drops", "fell", "fall", "retreat", "retreated", "crash", "crashed", "investigation",
    "disputed", "challenge", "challenged", "reversal", "overturned",
}

_NEGATED_QUESTION_HINTS = {
    "not", "never", "fail", "failed", "loss", "lose", "loses", "denied", "deny", "reject", "rejected", "blocked"
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if t not in _STOPWORDS}


def _question_polarity(question: str) -> int:
    tokens = _tokens(question)
    return -1 if tokens & _NEGATED_QUESTION_HINTS else 1


def _time_decay(hours_since_event: float, hold_window_hours: float) -> float:
    if hours_since_event < 1.0:
        return 0.0
    if hours_since_event <= 2.0:
        return 0.5
    if hours_since_event <= 6.0:
        return 0.5 + (hours_since_event - 2.0) * 0.125
    if hours_since_event <= hold_window_hours:
        # After the main window, decay gradually so stale opportunities shrink quickly.
        span = max(hold_window_hours - 6.0, 1.0)
        return max(0.25, 1.0 - (hours_since_event - 6.0) * (0.35 / span))
    return max(0.10, 0.25 - (hours_since_event - hold_window_hours) * 0.02)


def _market_age_hours(end_date: datetime, now: datetime) -> float:
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    return max(0.0, (now - end_date.astimezone(timezone.utc)).total_seconds() / 3600.0)


def _article_support(question_tokens: set[str], article: dict, question_sign: int, end_date: datetime) -> float:
    title = article.get("title", "") or ""
    description = article.get("description", "") or ""
    text = f"{title} {description}".strip()
    text_tokens = _tokens(text)
    overlap = len(question_tokens & text_tokens)
    if overlap == 0:
        return 0.0

    article_time = article.get("published_at")
    if article_time is not None:
        if article_time.tzinfo is None:
            article_time = article_time.replace(tzinfo=timezone.utc)
        if article_time.astimezone(timezone.utc) < end_date.astimezone(timezone.utc):
            return 0.0

    pos = len(text_tokens & _CONFIRM_POS)
    neg = len(text_tokens & _CONFIRM_NEG)
    raw = pos - neg
    if raw == 0:
        return 0.0

    recency_boost = 1.0
    if article_time is not None:
        hours_old = max(0.0, (datetime.now(timezone.utc) - article_time.astimezone(timezone.utc)).total_seconds() / 3600.0)
        recency_boost = max(0.35, 1.0 - hours_old / 72.0)

    return float(question_sign * raw) * (overlap / max(len(question_tokens), 1)) * recency_boost


async def detect_roda_signals(
    markets: list[dict],
    *,
    news_api_key: str = "",
    news_articles_by_market: Optional[dict[str, list[dict]]] = None,
    config: Optional[dict] = None,
    now: Optional[datetime] = None,
    kelly_fraction: float = 0.25,
    total_capital: float = 1000.0,
) -> list[dict]:
    cfg = config or {}
    enabled = cfg.get("roda_enabled", True)
    if not enabled:
        return []

    min_confidence = cfg.get("roda_min_confidence", 0.95)
    min_age_hours = cfg.get("roda_min_age_hours", 1.0)
    max_age_hours = cfg.get("roda_max_age_hours", 24.0)
    max_entry_price = cfg.get("roda_max_entry_price", 0.90)
    min_sources = int(cfg.get("roda_min_sources", 3))
    max_position_pct = cfg.get("roda_max_position_pct", 0.10)
    hold_window_hours = float(cfg.get("roda_hold_window_hours", 12.0))
    engine = AnalyticsEngine()
    now = now or datetime.now(timezone.utc)

    candidates: list[dict] = []
    for market in markets:
        end_date = market.get("end_date")
        if not end_date or not market.get("id"):
            continue
        if market.get("status") not in {"active", "open"}:
            continue

        age_hours = _market_age_hours(end_date, now)
        if age_hours < min_age_hours or age_hours > max_age_hours:
            continue

        candidates.append({**market, "_age_hours": age_hours})

    if not candidates:
        return []

    signals: list[dict] = []
    for market in candidates:
        question = market.get("question", "")
        question_tokens = _tokens(question)
        if not question_tokens:
            continue

        end_date = market.get("end_date")
        override_articles = (news_articles_by_market or {}).get(str(market["id"])) or market.get("news_articles")
        if override_articles is not None:
            articles = list(override_articles)
        elif news_api_key:
            articles = await fetch_news_articles(
                question,
                api_key=news_api_key,
                category=market.get("category", ""),
                page_size=12,
                since=end_date,
            )
        else:
            continue
        if not articles:
            continue

        question_sign = _question_polarity(question)
        scored_articles: list[tuple[float, dict]] = []
        for article in articles:
            score = _article_support(question_tokens, article, question_sign, end_date)
            if score != 0.0:
                scored_articles.append((score, article))

        if not scored_articles:
            continue

        strong_articles = [item for item in scored_articles if abs(item[0]) >= 0.35]
        source_names = {
            str((item[1].get("source") or {}).get("name", "")).strip()
            for item in strong_articles
            if (item[1].get("source") or {}).get("name")
        }
        total_support = sum(score for score, _ in scored_articles)
        confidence = min(
            0.99,
            0.55
            + 0.08 * len(strong_articles)
            + 0.05 * len(source_names)
            + 0.10 * min(abs(total_support), 2.0)
            + 0.07 * min(1.0, market["_age_hours"] / max(hold_window_hours, 1.0)),
        )

        if len(source_names) < min_sources or confidence < min_confidence:
            continue

        direction = "YES" if total_support > 0 else "NO"
        yes_price = float(market.get("market_price", 0.5))
        model_prob = confidence if direction == "YES" else 1.0 - confidence
        edge = engine.calculate_edge(yes_price, model_prob)
        token_price = yes_price if direction == "YES" else 1.0 - yes_price
        if token_price <= 0.0 or token_price > max_entry_price:
            continue

        time_factor = _time_decay(market["_age_hours"], hold_window_hours)
        if time_factor <= 0.0:
            continue

        size = engine.calculate_kelly_size(edge, model_prob, yes_price, total_capital, kelly_fraction)
        size = min(size * time_factor, total_capital * max_position_pct)
        if size < 1.0:
            continue

        event_key = " ".join(sorted(question_tokens))[:96]
        signal = {
            "market_id": market["id"],
            "market_question": question,
            "market_category": market.get("category", ""),
            "signal_type": "roda_oracle_lag",
            "direction": direction,
            "market_price": yes_price,
            "model_probability": model_prob,
            "edge": edge,
            "kelly_size_usd": size,
            "confidence": confidence,
            "roda_event_key": event_key,
            "roda_age_hours": market["_age_hours"],
            "roda_source_count": len(source_names),
            "roda_time_factor": time_factor,
            "roda_hold_window_hours": hold_window_hours,
        }
        signals.append(signal)

    signals.sort(key=lambda s: (s["confidence"], abs(s["edge"])), reverse=True)
    logger.info(f"Resolution Lag Arb detected {len(signals)} opportunities")
    return signals
