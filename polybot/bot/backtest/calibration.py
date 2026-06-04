"""Backtest-driven calibration helpers for strategy threshold tuning."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from bot.backtest.engine import BacktestConfig, BacktestEngine
from bot.backtest.loader import load_backtest_snapshots
from bot.backtest.models import BacktestReport, BacktestSnapshot


def _score_report(report: BacktestReport) -> float:
    return (
        float(report.total_return_pct)
        + float(report.sharpe_ratio) * 2.0
        + float(report.win_rate) * 10.0
        - float(report.max_drawdown_pct) * 0.75
        - float(report.total_fees_usd) * 0.01
    )


def _merge_config(base: BacktestConfig, patch: dict[str, Any]) -> BacktestConfig:
    values = asdict(base)
    values.update(patch)
    return BacktestConfig(**values)


def _strategy_grids(strategy: str) -> list[dict[str, Any]]:
    if strategy == "roda":
        return [
            {"allow_generic_strategy": False, "allow_roda": True, "allow_lch": False, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "roda_mode": "auto", "roda_min_confidence": 0.92, "roda_min_sources": 2, "roda_max_age_hours": 18.0},
            {"allow_generic_strategy": False, "allow_roda": True, "allow_lch": False, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "roda_mode": "news_lag", "roda_min_confidence": 0.95, "roda_min_sources": 3, "roda_max_age_hours": 24.0},
            {"allow_generic_strategy": False, "allow_roda": True, "allow_lch": False, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "roda_mode": "divergence", "roda_divergence_min_edge": 0.05, "roda_divergence_min_confidence": 0.55, "roda_divergence_min_sources": 2},
        ]
    if strategy == "lch":
        return [
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": True, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "lch_min_z_score": 2.25, "lch_min_recovery_probability": 0.68, "lch_max_wash_trading_score": 0.70},
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": True, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "lch_min_z_score": 2.50, "lch_min_recovery_probability": 0.70, "lch_max_wash_trading_score": 0.72},
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": True, "allow_hybrid": False, "allow_mss2": False, "allow_arb": False, "lch_min_z_score": 2.75, "lch_min_recovery_probability": 0.74, "lch_max_wash_trading_score": 0.76},
        ]
    if strategy == "mss2":
        return [
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": False, "allow_hybrid": False, "allow_mss2": True, "allow_arb": False, "mss2_min_spread_bps": 30.0, "mss2_min_expected_profit_bps": 30.0, "mss2_max_adverse_selection_score": 0.70, "mss2_min_fill_probability_proxy": 0.25, "mss2_max_queue_pressure": 0.80},
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": False, "allow_hybrid": False, "allow_mss2": True, "allow_arb": False, "mss2_min_spread_bps": 35.0, "mss2_min_expected_profit_bps": 35.0, "mss2_max_adverse_selection_score": 0.65, "mss2_min_fill_probability_proxy": 0.30, "mss2_max_queue_pressure": 0.75},
            {"allow_generic_strategy": False, "allow_roda": False, "allow_lch": False, "allow_hybrid": False, "allow_mss2": True, "allow_arb": False, "mss2_min_spread_bps": 45.0, "mss2_min_expected_profit_bps": 40.0, "mss2_max_adverse_selection_score": 0.60, "mss2_min_fill_probability_proxy": 0.35, "mss2_max_queue_pressure": 0.68},
        ]
    return [{}]


@dataclass(slots=True)
class CalibrationResult:
    strategy: str
    score: float
    config_patch: dict[str, Any]
    report: BacktestReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "score": self.score,
            "config_patch": self.config_patch,
            "report": self.report.to_dict(),
        }


async def calibrate_strategy(
    snapshots: Iterable[BacktestSnapshot],
    *,
    strategy: str,
    base_config: BacktestConfig | None = None,
) -> CalibrationResult:
    base = base_config or BacktestConfig()
    best: CalibrationResult | None = None
    snapshot_list = list(snapshots)

    for patch in _strategy_grids(strategy):
        config = _merge_config(base, patch)
        engine = BacktestEngine(config)
        report = await engine.run(snapshot_list)
        score = _score_report(report)
        candidate = CalibrationResult(strategy=strategy, score=score, config_patch=patch, report=report)
        if best is None or candidate.score > best.score:
            best = candidate

    if best is None:
        raise ValueError(f"No calibration candidates generated for strategy={strategy!r}")
    return best


async def calibrate_suite(
    snapshots: Iterable[BacktestSnapshot],
    *,
    strategies: Iterable[str] = ("roda", "lch", "mss2"),
    base_config: BacktestConfig | None = None,
) -> dict[str, CalibrationResult]:
    results: dict[str, CalibrationResult] = {}
    for strategy in strategies:
        results[strategy] = await calibrate_strategy(snapshots, strategy=strategy, base_config=base_config)
    return results


def export_calibration(results: dict[str, CalibrationResult], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({key: value.to_dict() for key, value in results.items()}, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info(f"Calibration exported to {destination}")
    return destination


async def calibrate_file(path: str | Path, *, strategies: Iterable[str] = ("roda", "lch", "mss2")) -> dict[str, CalibrationResult]:
    snapshots = load_backtest_snapshots(path)
    return await calibrate_suite(snapshots, strategies=strategies)
