"""
Dynamic Kelly Fraction adjuster.

Reduces Kelly during drawdowns, applies heat penalty near daily loss limit.
adjusted = base × drawdown_mult × heat_mult, clamped to [0.10, 1.00].
"""
from loguru import logger

_MIN = 0.10
_MAX = 1.00


def drawdown_mult(current_pnl: float, peak_pnl: float, capital: float) -> float:
    if capital <= 0:
        return 1.0
    dd = max(0.0, (peak_pnl - current_pnl) / capital)
    if dd < 0.01:
        return 1.0
    return max(0.33, 1.0 - dd / 0.30)


def heat_mult(daily_loss_used_pct: float) -> float:
    if daily_loss_used_pct <= 0:
        return 1.0
    return max(0.10, 1.0 - daily_loss_used_pct ** 2)


def compute_adjusted_kelly(
    base: float, current_pnl: float, peak_pnl: float, capital: float,
    daily_pnl: float = 0.0, daily_limit_usd: float = 30.0,
) -> float:
    dd = drawdown_mult(current_pnl, peak_pnl, capital)
    heat_pct = abs(daily_pnl) / daily_limit_usd if daily_limit_usd > 0 and daily_pnl < 0 else 0.0
    heat = heat_mult(heat_pct)
    result = max(_MIN, min(_MAX, base * dd * heat))
    if abs(result - base) > 0.02:
        logger.debug(f"Dynamic Kelly {base:.2f}→{result:.2f} (dd={dd:.2f} heat={heat:.2f})")
    return result


class KellyTracker:
    def __init__(self, base_fraction: float = 0.25, total_capital: float = 1000.0):
        self.base_fraction = base_fraction
        self.total_capital = total_capital
        self._peak: float = 0.0

    def update(self, current_pnl: float, daily_pnl: float = 0.0, daily_limit_usd: float = 30.0) -> float:
        if current_pnl > self._peak:
            self._peak = current_pnl
        return compute_adjusted_kelly(self.base_fraction, current_pnl, self._peak,
                                      self.total_capital, daily_pnl, daily_limit_usd)

    def reset(self):
        self._peak = 0.0
