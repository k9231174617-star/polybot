from __future__ import annotations

import argparse
import asyncio
import json

from .calibration import calibrate_file, export_calibration


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polybot backtest calibration suite")
    parser.add_argument("--input", required=True, help="Path to JSON or JSONL replay file")
    parser.add_argument("--output", help="Optional path to write calibration JSON")
    parser.add_argument(
        "--strategies",
        default="roda,lch,mss2",
        help="Comma-separated strategies to calibrate",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    strategies = [item.strip().lower() for item in str(args.strategies or "").split(",") if item.strip()]
    results = asyncio.run(calibrate_file(args.input, strategies=strategies))
    if args.output:
        export_calibration(results, args.output)
    if args.json or not args.output:
        print(json.dumps({key: value.to_dict() for key, value in results.items()}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
