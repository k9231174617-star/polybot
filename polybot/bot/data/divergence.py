"""External probability aggregation for true divergence arbitrage."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx


_DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "kalshi": 0.34,
    "manifold": 0.24,
    "bookmaker": 0.18,
    "bookmakers": 0.18,
    "predictit": 0.14,
    "consensus": 0.12,
    "oracle": 0.25,
    "source": 0.10,
}

_DEFAULT_PROBABILITY_FIELDS: tuple[str, ...] = ("probability", "price", "yes_probability", "yesProb")
_DEFAULT_CONFIDENCE_FIELDS: tuple[str, ...] = ("confidence", "weight")
_DEFAULT_UPDATED_AT_FIELDS: tuple[str, ...] = ("updated_at", "updatedAt", "timestamp")
_DEFAULT_PROVIDER_MIN_SIMILARITY = 0.34
_DEFAULT_PROVIDER_LIMIT = 250
_KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
_MANIFOLD_BASE_URL = "https://api.manifold.markets"
_MATCH_STOPWORDS = {
    "will", "the", "a", "an", "be", "is", "in", "on", "at", "to", "by", "of", "for",
    "and", "or", "with", "has", "have", "do", "does", "before", "after", "end",
    "year", "market", "markets", "yes", "no", "happen", "happens", "occur", "occurs",
    "occurring", "happening", "event", "question", "title", "date",
}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\w+", (text or "").lower())
        if len(token) > 1 and token not in _MATCH_STOPWORDS
    }


def _text_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize(left)
    right_tokens = _tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    if overlap == 0:
        return 0.0
    union = len(left_tokens | right_tokens)
    return overlap / max(union, 1)


@dataclass(slots=True)
class DivergenceQuote:
    source: str
    probability: float
    confidence: float = 1.0
    updated_at: datetime | None = None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class DivergenceConsensus:
    probability: float
    confidence: float
    source_count: int
    spread: float
    sources: list[str]
    quotes: list[DivergenceQuote]


@dataclass(slots=True)
class DivergenceFeedSpec:
    source: str
    url: str
    provider: str = "url"
    query: str | None = None
    sort: str | None = None
    filter: str | None = None
    contract_type: str | None = None
    series_ticker: str | None = None
    status: str | None = None
    limit: int = _DEFAULT_PROVIDER_LIMIT
    min_similarity: float = _DEFAULT_PROVIDER_MIN_SIMILARITY
    headers: dict[str, str] | None = None
    timeout_seconds: float = 10.0
    market_id_field: str = "market_id"
    probability_fields: tuple[str, ...] = ("probability", "price", "yes_probability", "yesProb")
    confidence_fields: tuple[str, ...] = ("confidence", "weight")
    updated_at_fields: tuple[str, ...] = ("updated_at", "updatedAt", "timestamp")
    question_fields: tuple[str, ...] = ("question", "title", "name", "description", "slug", "event_ticker", "ticker")
    payload_path: str | None = None
    markets_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DivergenceFeedSpec | None":
        url = str(data.get("url") or "").strip()
        provider = str(data.get("provider") or ("url" if url else "")).strip().lower()
        if not url and provider not in {"manifold", "kalshi", "bookmaker", "generic"}:
            return None
        source = str(data.get("source") or data.get("name") or provider or url).strip() or "source"
        probability_fields = data.get("probability_fields")
        confidence_fields = data.get("confidence_fields")
        updated_at_fields = data.get("updated_at_fields")
        question_fields = data.get("question_fields")
        if isinstance(probability_fields, str):
            probability_fields = [probability_fields]
        if isinstance(confidence_fields, str):
            confidence_fields = [confidence_fields]
        if isinstance(updated_at_fields, str):
            updated_at_fields = [updated_at_fields]
        if isinstance(question_fields, str):
            question_fields = [question_fields]
        return cls(
            source=source,
            url=url,
            provider=provider or "url",
            query=str(data.get("query") or data.get("term") or "").strip() or None,
            sort=str(data.get("sort") or "").strip() or None,
            filter=str(data.get("filter") or "").strip() or None,
            contract_type=str(data.get("contract_type") or data.get("contractType") or "").strip() or None,
            series_ticker=str(data.get("series_ticker") or data.get("seriesTicker") or "").strip() or None,
            status=str(data.get("status") or "").strip() or None,
            limit=max(1, int(data.get("limit") or data.get("max_results") or _DEFAULT_PROVIDER_LIMIT)),
            min_similarity=_clamp(float(data.get("min_similarity") or data.get("match_threshold") or _DEFAULT_PROVIDER_MIN_SIMILARITY), 0.0, 1.0),
            headers=data.get("headers") if isinstance(data.get("headers"), dict) else None,
            timeout_seconds=float(data.get("timeout_seconds") or data.get("timeout") or 10.0),
            market_id_field=str(data.get("market_id_field") or "market_id"),
            probability_fields=tuple(str(item) for item in (probability_fields or _DEFAULT_PROBABILITY_FIELDS)),
            confidence_fields=tuple(str(item) for item in (confidence_fields or _DEFAULT_CONFIDENCE_FIELDS)),
            updated_at_fields=tuple(str(item) for item in (updated_at_fields or _DEFAULT_UPDATED_AT_FIELDS)),
            question_fields=tuple(str(item) for item in (question_fields or ("question", "title", "name", "description", "slug", "event_ticker", "ticker"))),
            payload_path=str(data.get("payload_path") or "").strip() or None,
            markets_path=str(data.get("markets_path") or "").strip() or None,
        )


def _parse_probability(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        prob = float(value)
        if 0.0 <= prob <= 1.0:
            return prob
    except Exception:
        return None
    return None


def _parse_confidence(value: Any) -> float:
    try:
        if value is None or value == "":
            return 1.0
        return _clamp(float(value), 0.0, 1.0)
    except Exception:
        return 1.0


def _parse_updated_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except Exception:
            return None
    return None


def _extract_probability_from_item(item: dict[str, Any], spec: DivergenceFeedSpec) -> float | None:
    for field in spec.probability_fields:
        probability = _parse_probability(item.get(field))
        if probability is not None:
            return probability
    for field in ("yes_bid_dollars", "yes_bid", "yesPrice", "yes_price", "prob", "p"):
        probability = _parse_probability(item.get(field))
        if probability is not None:
            return probability
    for field in ("decimal_odds", "odds_decimal"):
        value = item.get(field)
        try:
            odds = float(value)
            if odds > 0.0:
                return _clamp(1.0 / odds, 0.0, 1.0)
        except Exception:
            continue
    for field in ("american_odds", "odds_american"):
        value = item.get(field)
        try:
            odds = float(value)
            if odds == 0.0:
                continue
            if odds > 0.0:
                return _clamp(100.0 / (odds + 100.0), 0.0, 1.0)
            return _clamp(abs(odds) / (abs(odds) + 100.0), 0.0, 1.0)
        except Exception:
            continue
    return None


def _extract_item_text(item: dict[str, Any], spec: DivergenceFeedSpec) -> str:
    parts: list[str] = []
    for field in spec.question_fields:
        value = item.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts).strip()


def _extract_external_quote(item: dict[str, Any], spec: DivergenceFeedSpec, *, market_id: str | None = None) -> dict[str, Any] | None:
    probability = _extract_probability_from_item(item, spec)
    if probability is None:
        return None
    source = str(item.get("source") or item.get("platform") or item.get("provider") or spec.source).strip() or spec.source
    confidence = 1.0
    for field in spec.confidence_fields:
        if field in item:
            confidence = _parse_confidence(item.get(field))
            break
    updated_at = None
    for field in spec.updated_at_fields:
        if field in item:
            updated_at = _parse_updated_at(item.get(field))
            break
    return {
        "market_id": market_id or str(item.get(spec.market_id_field) or item.get("market_id") or item.get("id") or "").strip(),
        "source": source,
        "probability": probability,
        "confidence": confidence,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "raw": item,
    }


def normalize_divergence_quotes(raw_quotes: Any) -> list[DivergenceQuote]:
    quotes: list[DivergenceQuote] = []
    if raw_quotes is None:
        return quotes

    if isinstance(raw_quotes, dict):
        # Mapping of source -> probability or source -> quote payload.
        for source, payload in raw_quotes.items():
            if isinstance(payload, dict):
                prob = _parse_probability(
                    payload.get("probability")
                    or payload.get("price")
                    or payload.get("yes_probability")
                    or payload.get("yesProb")
                )
                if prob is None:
                    continue
                quotes.append(
                    DivergenceQuote(
                        source=str(source).strip() or "source",
                        probability=prob,
                        confidence=_parse_confidence(payload.get("confidence") or payload.get("weight")),
                        updated_at=_parse_updated_at(payload.get("updated_at") or payload.get("updatedAt")),
                        raw=payload,
                    )
                )
            else:
                prob = _parse_probability(payload)
                if prob is None:
                    continue
                quotes.append(
                    DivergenceQuote(
                        source=str(source).strip() or "source",
                        probability=prob,
                        confidence=1.0,
                        updated_at=None,
                        raw={"probability": prob},
                    )
                )
        return quotes

    if isinstance(raw_quotes, list):
        for item in raw_quotes:
            if not isinstance(item, dict):
                continue
            prob = _parse_probability(
                item.get("probability")
                or item.get("price")
                or item.get("yes_probability")
                or item.get("yesProb")
            )
            if prob is None:
                continue
            quotes.append(
                DivergenceQuote(
                    source=str(item.get("source") or item.get("name") or item.get("platform") or "source").strip() or "source",
                    probability=prob,
                    confidence=_parse_confidence(item.get("confidence") or item.get("weight")),
                    updated_at=_parse_updated_at(item.get("updated_at") or item.get("updatedAt") or item.get("timestamp")),
                    raw=item,
                )
            )
    return quotes


def collect_divergence_quotes(
    market: dict[str, Any],
    *,
    market_sources: dict[str, Any] | None = None,
) -> list[DivergenceQuote]:
    raw_candidates: list[Any] = []
    for key in ("divergence_sources", "external_probabilities", "divergence_quotes", "source_quotes"):
        value = market.get(key)
        if value:
            raw_candidates.append(value)
    market_id = str(market.get("id") or "")
    if market_sources and market_id and market_id in market_sources:
        raw_candidates.append(market_sources[market_id])

    quotes: list[DivergenceQuote] = []
    for candidate in raw_candidates:
        quotes.extend(normalize_divergence_quotes(candidate))
    return quotes


def _drilldown(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except Exception:
                return None
        else:
            return None
    return current


def _extract_quote_dict(item: dict[str, Any], spec: DivergenceFeedSpec) -> dict[str, Any] | None:
    market_id = str(item.get(spec.market_id_field) or item.get("market_id") or item.get("id") or "").strip()
    probability = _extract_probability_from_item(item, spec)
    if probability is None:
        return None
    confidence = 1.0
    for field in spec.confidence_fields:
        if field in item:
            confidence = _parse_confidence(item.get(field))
            break
    updated_at = None
    for field in spec.updated_at_fields:
        if field in item:
            updated_at = _parse_updated_at(item.get(field))
            break
    return {
        "market_id": market_id,
        "source": spec.source,
        "probability": probability,
        "confidence": confidence,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "raw": item,
    }


def _payload_to_quote_map(payload: Any, spec: DivergenceFeedSpec) -> dict[str, list[dict[str, Any]]]:
    data = _drilldown(payload, spec.payload_path)
    if isinstance(data, dict) and spec.markets_path:
        data = _drilldown(data, spec.markets_path)

    quote_map: dict[str, list[dict[str, Any]]] = {}

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            quote = _extract_quote_dict(item, spec)
            if not quote:
                continue
            market_id = quote.pop("market_id") or ""
            if not market_id:
                continue
            quote_map.setdefault(market_id, []).append(quote)
        return quote_map

    if isinstance(data, dict):
        if all(isinstance(value, (int, float, str, dict)) for value in data.values()):
            for market_id, value in data.items():
                if isinstance(value, dict):
                    nested = dict(value)
                    nested.setdefault(spec.market_id_field, market_id)
                    quote = _extract_quote_dict(nested, spec)
                    if quote:
                        quote_map.setdefault(str(market_id), []).append(quote)
                else:
                    prob = _parse_probability(value)
                    if prob is None:
                        continue
                    quote_map.setdefault(str(market_id), []).append({
                        "source": spec.source,
                        "probability": prob,
                        "confidence": 1.0,
                        "updated_at": None,
                        "raw": {"market_id": market_id, "probability": prob},
                    })
            return quote_map

        quote = _extract_quote_dict(data, spec)
        if quote:
            market_id = quote.pop("market_id") or ""
            if market_id:
                quote_map.setdefault(market_id, []).append(quote)
        return quote_map

    return quote_map


def _best_matching_item(question: str, items: list[dict[str, Any]], spec: DivergenceFeedSpec) -> dict[str, Any] | None:
    best_item: dict[str, Any] | None = None
    best_score = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate_text = _extract_item_text(item, spec)
        score = _text_similarity(question, candidate_text)
        if score > best_score:
            best_score = score
            best_item = item
    if best_item is None or best_score < spec.min_similarity:
        return None
    enriched = dict(best_item)
    enriched["_match_score"] = best_score
    return enriched


def _extract_item_list(payload: Any, spec: DivergenceFeedSpec) -> list[dict[str, Any]]:
    data = _drilldown(payload, spec.payload_path)
    if isinstance(data, dict) and spec.markets_path:
        data = _drilldown(data, spec.markets_path)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if "markets" in data and isinstance(data["markets"], list):
            return [item for item in data["markets"] if isinstance(item, dict)]
        if "contracts" in data and isinstance(data["contracts"], list):
            return [item for item in data["contracts"] if isinstance(item, dict)]
        return [data]
    return []


def _payload_to_market_match_map(
    payload: Any,
    spec: DivergenceFeedSpec,
    markets: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    items = _extract_item_list(payload, spec)
    if not items:
        return {}

    quote_map: dict[str, list[dict[str, Any]]] = {}
    market_list = [market for market in markets if isinstance(market, dict) and market.get("id") and market.get("question")]
    if not market_list:
        return quote_map

    # If the payload already looks like a keyed mapping, preserve the original path-based parser.
    if isinstance(payload, dict) and not any(field in payload for field in ("markets", "contracts")):
        keyed = _payload_to_quote_map(payload, spec)
        if keyed:
            return keyed

    for market in market_list:
        question = str(market.get("question") or "").strip()
        if not question:
            continue
        best_item = _best_matching_item(question, items, spec)
        if best_item is None:
            continue
        quote = _extract_external_quote(best_item, spec, market_id=str(market["id"]))
        if not quote:
            continue
        quote_map.setdefault(str(market["id"]), []).append(quote)
    return quote_map


async def fetch_divergence_feeds(
    feeds: Iterable[dict[str, Any]] | Iterable[DivergenceFeedSpec],
    *,
    markets: Iterable[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    specs: list[DivergenceFeedSpec] = []
    for feed in feeds:
        if isinstance(feed, DivergenceFeedSpec):
            specs.append(feed)
            continue
        if isinstance(feed, dict):
            spec = DivergenceFeedSpec.from_dict(feed)
            if spec is not None:
                specs.append(spec)

    if not specs:
        return {}

    market_list = [market for market in (markets or []) if isinstance(market, dict)]

    async def _fetch(spec: DivergenceFeedSpec) -> dict[str, list[dict[str, Any]]]:
        timeout = httpx.Timeout(spec.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = spec.headers or {}
            provider = spec.provider.lower()
            if provider in {"manifold", "manifold-markets"}:
                url = spec.url or f"{_MANIFOLD_BASE_URL}/v0/search-markets"
                params = {
                    "term": spec.query or "",
                    "sort": spec.sort or "most-popular",
                    "filter": spec.filter or "open",
                    "contractType": spec.contract_type or "BINARY",
                    "limit": max(1, min(int(spec.limit or _DEFAULT_PROVIDER_LIMIT), 1000)),
                }
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                return _payload_to_market_match_map(payload, spec, market_list)

            if provider in {"kalshi", "kalshi-trade"}:
                base_url = spec.url or _KALSHI_BASE_URL
                url = base_url.rstrip("/") + "/markets"
                params: dict[str, Any] = {}
                if spec.series_ticker:
                    params["series_ticker"] = spec.series_ticker
                if spec.status:
                    params["status"] = spec.status
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
                return _payload_to_market_match_map(payload, spec, market_list)

            if provider in {"bookmaker", "generic"} and spec.url:
                response = await client.get(spec.url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if market_list:
                    return _payload_to_market_match_map(payload, spec, market_list)
                return _payload_to_quote_map(payload, spec)

            if not spec.url:
                return {}

            response = await client.get(spec.url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if market_list:
                return _payload_to_market_match_map(payload, spec, market_list)
            return _payload_to_quote_map(payload, spec)

    results = await asyncio.gather(*[_fetch(spec) for spec in specs], return_exceptions=True)
    quote_map: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if isinstance(result, Exception):
            continue
        for market_id, quotes in result.items():
            quote_map.setdefault(market_id, []).extend(quotes)
    return quote_map


def aggregate_divergence_quotes(
    quotes: Iterable[DivergenceQuote],
    *,
    source_weights: dict[str, float] | None = None,
) -> DivergenceConsensus | None:
    quote_list = [quote for quote in quotes if 0.0 <= quote.probability <= 1.0]
    if len(quote_list) < 2:
        return None

    weights = {**_DEFAULT_SOURCE_WEIGHTS, **(source_weights or {})}
    weighted_sum = 0.0
    total_weight = 0.0
    sources: list[str] = []
    for quote in quote_list:
        weight = max(weights.get(quote.source.lower(), weights.get("source", 0.10)), 0.01) * max(quote.confidence, 0.05)
        weighted_sum += quote.probability * weight
        total_weight += weight
        sources.append(quote.source)

    if total_weight <= 0.0:
        return None

    consensus = weighted_sum / total_weight
    dispersion = sum(abs(quote.probability - consensus) * max(weights.get(quote.source.lower(), weights.get("source", 0.10)), 0.01) for quote in quote_list) / total_weight
    coverage = _clamp(len(quote_list) / 4.0, 0.0, 1.0)
    agreement = _clamp(1.0 - dispersion * 1.8, 0.0, 1.0)
    weight_depth = _clamp(total_weight / 1.5, 0.0, 1.0)
    confidence = _clamp(0.34 * coverage + 0.36 * agreement + 0.30 * weight_depth, 0.0, 0.99)

    return DivergenceConsensus(
        probability=_clamp(consensus, 0.01, 0.99),
        confidence=confidence,
        source_count=len(quote_list),
        spread=_clamp(dispersion, 0.0, 1.0),
        sources=sorted({source for source in sources if source}),
        quotes=quote_list,
    )
