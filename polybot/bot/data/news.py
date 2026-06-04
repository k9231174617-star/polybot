"""News & Sentiment fetcher — headlines → sentiment score for each market question."""
import asyncio
import re
from datetime import datetime, timedelta, timezone
from loguru import logger
import httpx

_BULLISH = {
    "confirmed","approved","passed","wins","won","elected","launched","signed",
    "announced","succeeds","achieved","reached","deal","agreement","record",
    "breakthrough","positive","rally","rises","growth","victory","gain","higher",
    "increase","boost","support","advance",
}
_BEARISH = {
    "denied","rejected","fails","failed","lost","loses","cancelled","postponed",
    "delayed","declined","drops","crash","crisis","negative","worse","investigation",
    "scandal","collapse","ban","blocked","defeat","lower","decrease","fall","retreat",
}


def keyword_sentiment(text: str) -> float:
    """Keyword-based score in [-1, +1]. Works without any API key."""
    words = set(re.findall(r"\w+", text.lower()))
    bull = len(words & _BULLISH)
    bear = len(words & _BEARISH)
    total = bull + bear
    return 0.0 if total == 0 else (bull - bear) / total


async def fetch_news_sentiment(question: str, api_key: str = "", category: str = "") -> float:
    """
    Returns sentiment [-1, +1].
    Without NEWS_API_KEY: instant keyword match on the question text.
    With NEWS_API_KEY: fetches real headlines from NewsAPI for better signal.
    """
    if not api_key:
        return keyword_sentiment(question)

    stop = {"will","the","a","an","be","is","in","on","at","to","by","of","for",
            "and","or","with","has","have","do","does","before","after","end",
            "year","2024","2025","2026"}
    words = [w for w in re.findall(r"\w+", question.lower()) if w not in stop]
    query = " ".join(words[:6])

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://newsapi.org/v2/everything", params={
                "q": query, "language": "en", "sortBy": "publishedAt", "pageSize": 10,
                "from": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d"),
                "apiKey": api_key,
            })
            if resp.status_code != 200:
                return keyword_sentiment(question)
            articles = resp.json().get("articles", [])
            if not articles:
                return keyword_sentiment(question)
            scores = [keyword_sentiment(" ".join(filter(None, [a.get("title",""), a.get("description","")])))
                      for a in articles]
            return sum(scores) / len(scores)
    except Exception as e:
        logger.debug(f"NewsAPI error: {e}")
        return keyword_sentiment(question)


async def batch_sentiment(markets: list[dict], api_key: str = "", max_concurrent: int = 5) -> dict[str, float]:
    """Concurrent sentiment fetch for all markets. Returns {market_id: score}."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _one(m: dict) -> tuple[str, float]:
        async with sem:
            s = await fetch_news_sentiment(m.get("question",""), api_key=api_key, category=m.get("category",""))
            return m["id"], s

    results = await asyncio.gather(*[_one(m) for m in markets if m.get("id")], return_exceptions=True)
    return {r[0]: r[1] for r in results if isinstance(r, tuple)}
