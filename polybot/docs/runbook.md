# Incident Runbook

## 1. Stale heartbeat

Symptoms:
- dashboard heartbeat age grows
- bot status becomes unhealthy
- watchdog alerts fire

Action:
1. Check latest `bot_state.updated_at`.
2. Confirm the bot process is alive in Railway.
3. If the process is stuck, restart the service.
4. If the heartbeat is stale after restart, keep `DRY_RUN=true` and inspect logs before re-enabling live mode.

## 2. Reconciliation drift

Symptoms:
- balance reconciliation status becomes `warning` or `critical`
- discrepancy grows above the configured threshold

Action:
1. Stop live trading.
2. Check open orders and recent fills.
3. Compare internal balance estimates with the live collateral balance.
4. Resolve the mismatch before resuming live mode.

## 3. Telegram alert outage

Symptoms:
- logs show alert send failures
- no critical messages arrive

Action:
1. Confirm `TELEGRAM_BOT_TOKEN`.
2. Confirm primary and critical chat IDs.
3. Send a manual test alert from staging.
4. If Telegram is down, treat the dashboard as the backup channel and keep live mode conservative.

## 4. Failed deploy

Symptoms:
- Railway deployment stays in `BUILDING`, `DEPLOYING`, or `FAILED`

Action:
1. Check the deploy logs.
2. Verify the current commit still passes local tests.
3. Redeploy from the last known-good commit.
4. Do not push a second change before the first failure is understood.

## 5. Manual kill switch

Use when:
- drift is unresolved
- a key dependency is down
- the bot behaves unexpectedly

Action:
1. Set `paper_trading=true` or stop the bot through the dashboard.
2. Kill or restart the Railway service if the bot does not stop cleanly.
3. Confirm no open live orders remain.
4. Only restore live mode after a clean health check.
