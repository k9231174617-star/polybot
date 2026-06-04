# Operational Readiness

## Environments

- `production` is the live Railway environment.
- `staging` is a separate Railway environment with its own Postgres volume and its own variables.
- Default rule: deploy to `staging` first, validate there, then promote the same commit to `production`.

### Staging defaults

- `DRY_RUN=true`
- `BOT_MODE=bot`
- `AUTO_RECALIBRATION_ENABLED=false`
- `AUTO_RECALIBRATION_APPLY_CHANGES=false`
- `ALERTS_ENABLED=true`

## Alerting

- Primary channel: Telegram chat for operational alerts.
- Critical channel: a separate Telegram chat ID is supported via `TELEGRAM_CRITICAL_CHAT_ID`.
- Critical alerts are duplicated to the critical channel when configured.
- Do not rely on DB logs as the only alert sink.

## SLO / Observability

Track these operational metrics in the dashboard:

- latency p50 / p95 / p99 for signal -> decision, decision -> execution, signal -> trade recorded, signal -> confirmation
- error rate over the last 24h
- heartbeat age and stale heartbeat flag
- dropped / stale pending signals
- fill success rate
- reconciliation drift in USD and percent

## Secrets

- Keep production and staging variables separate.
- Rotate `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, `POLYMARKET_API_PASSPHRASE`, and Telegram credentials on a fixed cadence.
- Rotation rule: update staging first, verify, then roll production.

## Backup / Restore

- Backup the PostgreSQL database before any schema change or deploy that touches persistence.
- Verify restore by loading a backup into a scratch environment and checking:
  - `bot_config`
  - `signals`
  - `trades`
  - `positions`
  - `balance_reconciliation_snapshots`
  - `latency_events`
- Do not assume Railway backups are sufficient without a restore test.

## Divergence Feeds

- RODA divergence mode should be fed from live external sources.
- Supported provider families:
  - Kalshi
  - Manifold
  - custom bookmaker / URL feeds
- Rule: do not enable `roda_mode=divergence` unless at least one real live feed is configured for the market class.

## Recalibration

- `AUTO_RECALIBRATION_APPLY_CHANGES` must stay `false` by default.
- Recalibration recommendations should be reviewed manually until the signal quality is stable.
- Review cadence: weekly at minimum, or after a noticeable regime shift.

## Access Control

- Only a small number of operators should be allowed to:
  - push to `main`
  - change Railway variables
  - redeploy `production`
  - enable live mode
- Use separate credentials for staging and production.
- Never share production Railway or GitHub tokens in runbooks or logs.
