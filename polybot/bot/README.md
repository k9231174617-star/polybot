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

## Paper Trading

Paper trading is controlled by `bot_config.paper_trading`.
When enabled, the bot uses real market data, writes into the `paper_*` tables, and does not send live CLOB orders.

`DRY_RUN` only affects the live executor path.
