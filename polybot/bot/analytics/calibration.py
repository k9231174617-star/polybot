"""
Historical calibration — adjusts model probabilities using resolved Polymarket data.

Bins resolved markets by price, computes empirical YES-resolution rates,
and blends raw probabilities toward those rates (max 40% weight).
Cold-start: no-op until enough data is loaded.
"""
from loguru import logger
import httpx

_N_BINS = 10
_MIN_SAMPLES = 20


def _bin(p: float) -> int:
    return min(int(p * _N_BINS), _N_BINS - 1)


class CalibrationModel:
    def __init__(self):
        self._counts = [0] * _N_BINS
        self._yes = [0] * _N_BINS
        self._fitted = False

    def fit(self, resolved: list[dict]):
        self._counts = [0] * _N_BINS
        self._yes = [0] * _N_BINS
        for m in resolved:
            idx = _bin(float(m.get("market_price", 0.5)))
            self._counts[idx] += 1
            if m.get("resolved_yes"):
                self._yes[idx] += 1
        total = sum(self._counts)
        if total >= _MIN_SAMPLES:
            self._fitted = True
            logger.info(f"Calibration fitted on {total} resolved markets")

    def adjust(self, raw: float) -> float:
        if not self._fitted:
            return raw
        idx = _bin(raw)
        n = self._counts[idx]
        if n == 0:
            return raw
        empirical = self._yes[idx] / n
        w = min(0.40, n / 200)
        return max(0.01, min(0.99, (1 - w) * raw + w * empirical))

    async def load_from_polymarket(self, base_url: str = "https://gamma-api.polymarket.com", limit: int = 500):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{base_url}/markets", params={"closed": "true", "limit": limit})
                if resp.status_code != 200:
                    return
                data = resp.json()
                markets = data if isinstance(data, list) else data.get("markets", [])
                resolved = []
                for m in markets:
                    raw_p = m.get("lastTradePrice") or (m.get("outcomePrices") or ["0.5"])[0]
                    try:
                        price = float(raw_p)
                    except (ValueError, TypeError):
                        continue
                    res = str(m.get("resolution") or m.get("resolvedBy", "")).lower()
                    resolved.append({"market_price": price, "resolved_yes": res in ("1","yes","true","1.0")})
                self.fit(resolved)
        except Exception as e:
            logger.debug(f"Calibration load error: {e}")


_calibration = CalibrationModel()


async def load_calibration(base_url: str = "https://gamma-api.polymarket.com"):
    await _calibration.load_from_polymarket(base_url=base_url)


def get_calibration() -> CalibrationModel:
    return _calibration
