from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class BacktestSnapshot:
    timestamp: datetime
    markets: list[dict[str, Any]]
    news_by_market: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    trades_by_market: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    orderbooks_by_token: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestPosition:
    id: int
    market_id: str
    market_question: str
    side: str
    signal_type: str
    opened_at: datetime
    entry_yes_price: float
    entry_token_price: float
    size_usd: float
    confidence: float
    entry_fee_usd: float
    entry_slippage: float
    status: str = "open"
    closed_at: datetime | None = None
    exit_yes_price: float | None = None
    exit_token_price: float | None = None
    exit_fee_usd: float = 0.0
    realized_pnl: float = 0.0


@dataclass(slots=True)
class BacktestTrade:
    position_id: int
    market_id: str
    market_question: str
    side: str
    action: str
    signal_type: str
    executed_at: datetime
    size_usd: float
    yes_price: float
    token_price: float
    fee_usd: float
    slippage: float
    realized_pnl: float | None = None


@dataclass(slots=True)
class BacktestReport:
    initial_capital_usd: float
    final_capital_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    total_fees_usd: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    profit_factor: float
    total_signals: int
    executed_trades: int
    open_positions: int
    closed_positions: int
    by_signal_type: dict[str, dict[str, Any]]
    equity_curve: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital_usd": self.initial_capital_usd,
            "final_capital_usd": self.final_capital_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "unrealized_pnl_usd": self.unrealized_pnl_usd,
            "total_fees_usd": self.total_fees_usd,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_signals": self.total_signals,
            "executed_trades": self.executed_trades,
            "open_positions": self.open_positions,
            "closed_positions": self.closed_positions,
            "by_signal_type": self.by_signal_type,
            "equity_curve": self.equity_curve,
        }
