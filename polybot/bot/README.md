# Polymarket Trading Bot

Automated trading bot for Polymarket prediction markets. Scans markets, detects pricing inefficiencies, and executes trades with built-in risk management.

## Quick Start

```bash
cd polybot
pip install -r bot/requirements.txt
export DATABASE_URL="postgresql://..."
export DRY_RUN=true
python -m bot.main
```

## Historical Backtest

Replay historical market snapshots from a JSON or JSONL file:

```bash
python -m bot.backtest --input ./replays/sample.jsonl --json
```

Each snapshot should include a timestamp and a full market universe for that time step. Optional fields allow you to embed per-market news, trades, and orderbooks so the same strategy code can be replayed offline without live APIs.

## Paper Trading

Paper trading is controlled by `bot_config.paper_trading`.
When enabled, the bot uses real market data, writes into the `paper_*` tables, and does not send live CLOB orders.

`DRY_RUN` only affects the live executor path.

## Runtime modes

Set `BOT_MODE=watchdog` to run the dead-man watchdog instead of the trading loop.
The default mode is `BOT_MODE=bot`.
