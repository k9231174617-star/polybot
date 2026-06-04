# Polymarket Trading Bot

Automated trading bot for Polymarket prediction markets. Scans markets, detects pricing inefficiencies, and executes trades with built-in risk management.

## Architecture

```
bot/
├── main.py               # Entry point
├── config.py             # Settings (env-driven)
├── core/
│   └── bot.py            # Main scan-analyze-act loop
├── data/
│   └── polymarket.py     # Polymarket API client (Gamma + CLOB)
├── analytics/
│   └── engine.py         # Fair probability model + edge calculation
├── execution/
│   └── orders.py         # Order placement (dry-run or live CLOB)
├── risk/
│   └── manager.py        # Position limits, daily loss limits, correlation
└── utils/
    └── db.py             # Async PostgreSQL utilities
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r bot/requirements.txt
```

### 2. Set environment variables

```bash
export DATABASE_URL="postgresql://..."  # Set automatically by Replit
export DRY_RUN=true                     # Start in simulation mode
export INITIAL_CAPITAL_USD=1000
```

### 3. Run in dry-run mode (paper trading)

```bash
python -m bot.main
```

### 4. Live trading (after testing)

```bash
export DRY_RUN=false
export POLYMARKET_PRIVATE_KEY="your_polygon_wallet_private_key"
export POLYMARKET_API_KEY="your_polymarket_api_key"
export POLYMARKET_API_SECRET="your_polymarket_api_secret"
export POLYMARKET_API_PASSPHRASE="your_passphrase"
python -m bot.main
```

## Decision Logic

```
For each market:
  1. Fetch price, orderbook, and volume from Polymarket API
  2. Calculate "fair probability" using the analytics engine
  3. edge = model_probability - market_price
  4. If |edge| > edge_threshold (default 5%) → signal detected
  5. Calculate Kelly Criterion position size (capped at max_position_pct)
  6. Run risk checks (daily loss limit, position cap, correlation)
  7. If all checks pass → execute order (market or limit)
  8. Record trade, open position, log event
```

## Risk Management

| Parameter | Default | Description |
|-----------|---------|-------------|
| `edge_threshold` | 5% | Minimum edge to enter |
| `kelly_fraction` | 25% | Fraction of full Kelly (quarter-Kelly) |
| `max_position_pct` | 5% | Max % of capital per market |
| `daily_loss_limit_pct` | 3% | Bot stops if daily P&L < -3% |
| `max_correlated_exposure_pct` | 15% | Max total deployed capital |
| `min_liquidity_usd` | $1,000 | Skip illiquid markets |

## Extending the Analytics Engine

The `AnalyticsEngine` in `analytics/engine.py` uses a simple baseline model.
To improve accuracy:

1. **ML model**: Train a classifier on historical resolution outcomes
2. **Sentiment analysis**: Integrate news/Twitter sentiment for event-driven markets
3. **Cross-market arbitrage**: Compare prices against Kalshi/PredictIt/Betfair
4. **On-chain signals**: Track whale wallet activity via Polygon blockchain

## Monitoring

The dashboard (at `/`) shows real-time state from the PostgreSQL database:
- Bot status and uptime
- Open positions with unrealized P&L
- Detected signals with edge %
- Trade history and realized P&L
- Risk metrics and daily limits
