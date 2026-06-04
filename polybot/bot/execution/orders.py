"""Order Execution — places orders on Polymarket CLOB (or simulates in dry-run mode)."""
import random
from typing import Any, Optional
from loguru import logger

from bot.config import settings
from bot.execution.fees import estimate_taker_fee, resolve_market_fee_rate
from bot.notifications import send_telegram_alert
from bot.utils.db import insert_trade, insert_balance_reconciliation, get_pool, record_latency_event
from bot.data.polymarket import PolymarketClient
from bot.observability.latency import utcnow, duration_ms

try:
    from py_clob_client_v2 import ClobClient, ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions  # type: ignore
    from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType  # type: ignore
    from py_clob_client_v2.order_builder.constants import BUY  # type: ignore
except Exception:  # pragma: no cover - optional dependency on deploy image
    try:
        from py_clob_client.client import ClobClient  # type: ignore
        from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions  # type: ignore
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType  # type: ignore
        from py_clob_client.order_builder.constants import BUY  # type: ignore
    except Exception:  # pragma: no cover - optional dependency on deploy image
        ClobClient = None  # type: ignore
        ApiCreds = None  # type: ignore
        OrderArgs = None  # type: ignore
        OrderType = None  # type: ignore
        PartialCreateOrderOptions = None  # type: ignore
        BalanceAllowanceParams = None  # type: ignore
        AssetType = None  # type: ignore
        BUY = None  # type: ignore


def _token_price(side: str, yes_price: float) -> float:
    return yes_price if side == "YES" else 1 - yes_price


class OrderExecutor:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self._clob_client: Any | None = None
        self._api_creds: Any | None = None

    async def execute_signal(self, signal: dict, config: dict) -> Optional[dict]:
        """
        Execute a trade based on a detected signal.

        In dry_run mode: simulates execution with realistic slippage.
        In live mode: sends order to Polymarket CLOB.
        """
        market_id = signal["market_id"]
        direction = signal["direction"]  # YES or NO
        size_usd = signal["kelly_size_usd"]
        market_price = signal["market_price"]
        market_category = signal.get("market_category", "")

        order_type = signal.get("order_type") or ("limit" if config.get("use_limit_orders") else "market")
        slippage_pct = random.uniform(0.001, 0.005)
        exec_price = min(0.99, max(0.01, _token_price(direction, market_price) * (1 + slippage_pct)))

        if self.dry_run:
            filled_size = size_usd
            remaining_size = 0.0
            order_status = "simulated"
            order_id = f"sim-{''.join(random.choices('0123456789abcdef', k=16))}"
            tx_hash = None
            logger.info(f"[DRY RUN] Would execute: {direction} ${size_usd:.2f} on {market_id[:12]}... at {exec_price:.3f}")
        else:
            live_result = await self._send_clob_order(signal, config)
            if not live_result:
                logger.error(f"CLOB order failed for {market_id}")
                await send_telegram_alert(
                    "error",
                    "Trade execution failed",
                    f"Order rejected for {signal['market_id']} ({signal.get('signal_type')})",
                    {"market_id": market_id, "signal_type": signal.get("signal_type"), "direction": direction},
                )
                return None
            order_id = str(live_result.get("order_id") or "")
            order_status = str(live_result.get("order_status") or "submitted")
            filled_size = float(live_result.get("filled_size_usd") or 0.0)
            remaining_size = max(0.0, size_usd - filled_size)
            if filled_size <= 0.0 and order_status in {"matched", "filled"}:
                filled_size = size_usd
                remaining_size = 0.0
            if filled_size <= 0.0 and order_status in {"live", "delayed", "unmatched"}:
                remaining_size = size_usd
            tx_hash = live_result.get("tx_hash")
            exec_price = float(live_result.get("exec_price") or exec_price)
            market_category = str(live_result.get("market_category") or market_category or "")

        fee_usd = self._estimate_fee(filled_size, market_price, direction, market_category=market_category)
        trade = {
            "market_id": market_id,
            "market_question": signal["market_question"],
            "market_category": market_category,
            "signal_id": signal.get("signal_id"),
            "side": direction,
            "action": "buy",
            "size_usd": size_usd,
            "price": exec_price,
            "slippage": slippage_pct,
            "fee_usd": fee_usd,
            "realized_pnl": None,
            "tx_hash": tx_hash,
            "order_id": order_id,
            "order_status": order_status,
            "filled_size_usd": filled_size,
            "remaining_size_usd": remaining_size,
            "order_type": order_type,
        }

        trade_id = await insert_trade(trade)
        trade_recorded_at = utcnow()
        logger.info(
            f"Trade recorded: id={trade_id}, {direction} ${filled_size:.2f}, "
            f"status={order_status}, filled={filled_size:.2f}, remaining={remaining_size:.2f}"
        )

        detected_at = signal.get("detected_at")
        signal_id = signal.get("signal_id")
        if signal_id is not None and detected_at is not None:
            signal_to_trade_ms = duration_ms(detected_at, trade_recorded_at)
            if signal_to_trade_ms is not None:
                await record_latency_event({
                    "signal_id": signal_id,
                    "market_id": market_id,
                    "signal_type": signal.get("signal_type", "unknown"),
                    "stage": "signal_to_trade_recorded",
                    "duration_ms": signal_to_trade_ms,
                    "started_at": detected_at,
                    "finished_at": trade_recorded_at,
                    "details": {"trade_id": trade_id, "order_status": order_status, "paper_mode": False},
                })

        if filled_size > 0:
            await self._open_position(signal, exec_price, filled_size, trade_id, order_id=order_id, order_status=order_status, remaining_size_usd=remaining_size)
        if remaining_size > 0:
            await send_telegram_alert(
                "warning",
                "Partial fill detected",
                f"Order {order_id or '<unknown>'} on {market_id} has remainder {remaining_size:.2f} USD",
                {"market_id": market_id, "order_status": order_status, "filled_size_usd": filled_size, "remaining_size_usd": remaining_size},
            )

        return {**trade, "id": trade_id}

    async def _open_position(self, signal: dict, exec_price: float, size_usd: float, trade_id: int, *, order_id: str | None = None, order_status: str = "open", remaining_size_usd: float = 0.0):
        """Record an open position in the database."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO positions (market_id, market_question, side, size_usd, entry_price,
                    current_price, unrealized_pnl, unrealized_pnl_pct, entry_edge,
                    current_edge, order_id, order_status, filled_size_usd, remaining_size_usd, status, opened_at)
                VALUES ($1, $2, $3, $4, $5, $5, 0, 0, $6, $6, $7, $8, $9, $10, 'open', NOW())
            """,
                signal["market_id"], signal["market_question"], signal["direction"],
                size_usd, exec_price, signal["edge"], order_id, order_status, size_usd, remaining_size_usd
            )

    async def _send_clob_order(self, signal: dict, config: dict) -> dict | None:
        """
        Send actual order to Polymarket CLOB.
        Requires API keys to be configured.
        """
        if ClobClient is None or ApiCreds is None or OrderArgs is None or OrderType is None or PartialCreateOrderOptions is None or BUY is None:
            logger.error("Polymarket CLOB client is not installed — cannot place live orders")
            return None

        if not settings.polymarket_private_key:
            logger.error("POLYMARKET_PRIVATE_KEY not set — cannot place live orders")
            return None

        try:
            client = await self._get_clob_client()
            if client is None:
                return None

            market = await self._resolve_market(signal["market_id"])
            if not market:
                logger.error(f"Could not load market metadata for {signal['market_id']}")
                return None

            token_id = self._resolve_token_id(market, signal["direction"])
            if not token_id:
                logger.error(f"Could not resolve token id for {signal['market_id']} {signal['direction']}")
                return None

            token_price = _token_price(signal["direction"], signal["market_price"])
            if token_price <= 0:
                logger.error(f"Invalid token price for {signal['market_id']}: {token_price}")
                return None

            tick_size = self._resolve_tick_size(market)
            neg_risk = self._resolve_neg_risk(market)
            size_shares = float(signal["kelly_size_usd"]) / token_price
            order_args = OrderArgs(
                token_id=token_id,
                price=round(token_price, 4),
                size=round(size_shares, 6),
                side=BUY,
            )
            options = PartialCreateOrderOptions(tick_size=str(tick_size), neg_risk=bool(neg_risk))
            create_and_post = getattr(client, "create_and_post_order", None) or getattr(client, "createAndPostOrder", None)
            if create_and_post is None:
                logger.error("Polymarket client does not expose create_and_post_order/createAndPostOrder")
                return None

            response = await self._maybe_await(
                create_and_post(order_args, options=options, order_type=OrderType.GTC)
            )
            order_id = self._extract_order_id(response)
            order_status = self._extract_order_status(response)
            filled_size_usd = self._extract_filled_size_usd(response, float(signal["kelly_size_usd"]), token_price, signal["direction"])
            logger.info(
                f"[LIVE] Posted order {order_id or '<unknown>'} on {signal['market_id']} "
                f"token={token_id} size={size_shares:.6f} price={token_price:.4f}"
            )
            return {
                "order_id": order_id,
                "order_status": order_status,
                "filled_size_usd": filled_size_usd,
                "remaining_size_usd": max(0.0, float(signal["kelly_size_usd"]) - filled_size_usd),
                "exec_price": token_price,
                "tx_hash": self._extract_tx_hash(response),
                "market_category": market.get("category", ""),
            }
        except Exception as e:
            logger.error(f"CLOB order error: {e}")
            await send_telegram_alert(
                "error",
                "CLOB execution error",
                f"{signal['market_id']} failed with {e}",
                {"market_id": signal["market_id"], "signal_type": signal.get("signal_type"), "direction": signal.get("direction")},
            )
            return None

    async def _get_clob_client(self):
        if self._clob_client is not None:
            return self._clob_client

        if not settings.polymarket_private_key:
            return None

        funder = settings.polymarket_funder_address or None

        if settings.polymarket_api_key and settings.polymarket_api_secret and settings.polymarket_api_passphrase:
            creds = ApiCreds(
                api_key=settings.polymarket_api_key,
                api_secret=settings.polymarket_api_secret,
                api_passphrase=settings.polymarket_api_passphrase,
            )
        else:
            temp_client = ClobClient(settings.polymarket_clob_url, key=settings.polymarket_private_key, chain_id=137)
            derived = await self._maybe_await(temp_client.create_or_derive_api_key())
            creds = ApiCreds(
                api_key=derived["apiKey"] if isinstance(derived, dict) else derived.api_key,
                api_secret=derived["secret"] if isinstance(derived, dict) else derived.secret,
                api_passphrase=derived["passphrase"] if isinstance(derived, dict) else derived.passphrase,
            )

        if creds is None:
            logger.error("Could not initialize Polymarket API credentials")
            return None

        init_kwargs = {
            "host": settings.polymarket_clob_url,
            "chain_id": 137,
            "key": settings.polymarket_private_key,
            "creds": creds,
            "signature_type": int(settings.polymarket_signature_type),
        }
        if funder:
            init_kwargs["funder"] = funder

        client = None
        constructor_attempts = [
            lambda: ClobClient(
                settings.polymarket_clob_url,
                key=settings.polymarket_private_key,
                chain_id=137,
                creds=creds,
                signature_type=int(settings.polymarket_signature_type),
                funder=funder,
            ),
            lambda: ClobClient(
                settings.polymarket_clob_url,
                key=settings.polymarket_private_key,
                chain_id=137,
                creds=creds,
                signature_type=int(settings.polymarket_signature_type),
            ),
            lambda: ClobClient(
                settings.polymarket_clob_url,
                key=settings.polymarket_private_key,
                chain_id=137,
            ),
        ]
        for factory in constructor_attempts:
            try:
                client = factory()
                break
            except TypeError:
                continue
        if client is None:
            logger.error("Could not initialize Polymarket CLOB client with available constructor signatures")
            return None
        self._clob_client = client
        self._api_creds = creds
        return self._clob_client

    async def _resolve_market(self, market_id: str) -> Optional[dict]:
        async with PolymarketClient() as client:
            return await client.get_market(market_id)

    def _resolve_token_id(self, market: dict, direction: str) -> str:
        tokens = market.get("tokens") or []
        target = "YES" if direction == "YES" else "NO"
        for token in tokens:
            outcome = str(token.get("outcome") or token.get("side") or token.get("name") or "").upper()
            if outcome == target:
                return str(token.get("token_id") or token.get("id") or token.get("tokenId") or "")
        return ""

    def _resolve_tick_size(self, market: dict) -> str:
        tick = market.get("minimum_tick_size") or market.get("minimumTickSize") or market.get("tick_size") or "0.01"
        try:
            value = float(tick)
            if value <= 0:
                return "0.01"
            if value >= 0.1:
                return "0.1"
            if value >= 0.01:
                return "0.01"
            if value >= 0.001:
                return "0.001"
        except Exception:
            logger.debug(f"Could not normalize tick size {tick!r}; using raw value")
        return str(tick)

    def _resolve_neg_risk(self, market: dict) -> bool:
        value = market.get("neg_risk")
        if value is None:
            value = market.get("negRisk")
        return bool(value)

    def _extract_order_id(self, response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("orderID") or response.get("order_id") or response.get("id") or "")
        return str(getattr(response, "orderID", None) or getattr(response, "order_id", None) or getattr(response, "id", "") or "")

    def _extract_order_status(self, response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("status") or response.get("orderStatus") or response.get("order_status") or "submitted")
        return str(getattr(response, "status", None) or getattr(response, "order_status", None) or "submitted")

    def _extract_tx_hash(self, response: Any) -> str | None:
        if isinstance(response, dict):
            tx_hashes = response.get("transactionsHashes") or response.get("transactionHashes") or response.get("tx_hashes") or []
            if isinstance(tx_hashes, list) and tx_hashes:
                return str(tx_hashes[0])
            return str(response.get("tx_hash") or "") or None
        return str(getattr(response, "tx_hash", None) or "") or None

    def _extract_filled_size_usd(self, response: Any, fallback_size_usd: float, token_price: float, direction: str) -> float:
        if isinstance(response, dict):
            taking = response.get("takingAmount")
            making = response.get("makingAmount")
            for raw in (making, taking):
                try:
                    if raw is not None and str(raw) != "":
                        value = float(raw)
                        if value > 0:
                            return value if direction == "YES" else value * token_price
                except Exception:
                    continue
            trade_ids = response.get("tradeIDs") or response.get("tradeIds") or []
            if response.get("status") in {"matched", "filled"} and trade_ids:
                return fallback_size_usd
            if response.get("status") in {"matched", "filled"}:
                return fallback_size_usd
        return 0.0

    async def _maybe_await(self, value: Any) -> Any:
        if hasattr(value, "__await__"):
            return await value
        return value

    def _estimate_fee(self, size_usd: float, price: float, direction: str, *, market_category: str = "", market: dict | None = None) -> float:
        if size_usd <= 0 or price <= 0:
            return 0.0
        fee_rate = resolve_market_fee_rate(market=market, category=market_category)
        return estimate_taker_fee(size_usd, price, direction, category=market_category, fee_rate=fee_rate)

    async def reconcile_live_orders(self) -> int:
        """Refresh live order statuses and propagate fills into positions."""
        if self.dry_run:
            return 0
        client = await self._get_clob_client()
        if client is None:
            return 0

        getter = getattr(client, "get_order_status", None) or getattr(client, "getOrderStatus", None)
        if getter is None:
            logger.warning("Polymarket client does not expose get_order_status/getOrderStatus")
            return 0

        pool = await get_pool()
        updated = 0
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, market_id, market_question, signal_id, side, size_usd, price, order_id, order_status, filled_size_usd, remaining_size_usd
                FROM trades
                WHERE order_id IS NOT NULL
                  AND action = 'buy'
                  AND order_status IN ('submitted','live','delayed','unmatched')
                """
            )
            for row in rows:
                try:
                    status_resp = await self._maybe_await(getter(row["order_id"]))
                except Exception as exc:
                    logger.warning(f"Failed to fetch order status for {row['order_id']}: {exc}")
                    continue

                status = self._extract_order_status(status_resp)
                size_usd = float(row["size_usd"] or 0.0)
                token_price = float(row["price"] or 0.0)
                filled_size = self._extract_filled_size_usd(status_resp, size_usd, token_price, str(row["side"]))
                remaining_size = max(0.0, size_usd - filled_size)
                await conn.execute(
                    """
                    UPDATE trades
                    SET order_status = $1,
                        filled_size_usd = $2,
                        remaining_size_usd = $3
                    WHERE id = $4
                    """,
                    status,
                    filled_size,
                    remaining_size,
                    row["id"],
                )
                if filled_size > 0:
                    await conn.execute(
                        """
                        UPDATE positions
                        SET size_usd = $1,
                            filled_size_usd = $1,
                            remaining_size_usd = $2,
                            order_status = $3
                        WHERE order_id = $4 AND status = 'open'
                        """,
                        filled_size,
                        remaining_size,
                        status,
                        row["order_id"],
                    )
                    if row["signal_id"] is not None and status in {"filled", "matched"}:
                        signal_row = await conn.fetchrow("SELECT detected_at, signal_type FROM signals WHERE id = $1", row["signal_id"])
                        if signal_row is not None and signal_row["detected_at"] is not None:
                            confirmation_at = utcnow()
                            confirmation_ms = duration_ms(signal_row["detected_at"], confirmation_at)
                            if confirmation_ms is not None:
                                await record_latency_event({
                                    "signal_id": row["signal_id"],
                                    "market_id": row["market_id"],
                                    "signal_type": str(signal_row["signal_type"] or "unknown"),
                                    "stage": "signal_to_confirmation",
                                    "duration_ms": confirmation_ms,
                                    "started_at": signal_row["detected_at"],
                                    "finished_at": confirmation_at,
                                    "details": {"order_id": row["order_id"], "order_status": status},
                                })
                    exists = await conn.fetchval(
                        "SELECT id FROM positions WHERE order_id = $1 AND status = 'open'",
                        row["order_id"],
                    )
                    if not exists:
                        await conn.execute(
                            """
                            INSERT INTO positions (market_id, market_question, side, size_usd, entry_price,
                                current_price, unrealized_pnl, unrealized_pnl_pct, entry_edge,
                                current_edge, order_id, order_status, filled_size_usd, remaining_size_usd,
                                status, opened_at)
                            VALUES ($1, $2, $3, $4, $5, $5, 0, 0, 0, 0, $6, $7, $8, $9, 'open', NOW())
                            """,
                            row["market_id"],
                            row["market_question"],
                            row["side"],
                            filled_size,
                            token_price,
                            row["order_id"],
                            status,
                            filled_size,
                            remaining_size,
                        )
                updated += 1
        return updated

    def _extract_balance_value(self, response: Any) -> float:
        if response is None:
            return 0.0
        if isinstance(response, (int, float)):
            return float(response)
        if isinstance(response, str):
            try:
                return float(response)
            except ValueError:
                return 0.0
        if isinstance(response, dict):
            for key in ("balance", "available_balance", "available", "collateral_balance", "value"):
                value = response.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        continue
            for nested_key in ("data", "result"):
                nested = response.get(nested_key)
                if isinstance(nested, dict):
                    nested_value = self._extract_balance_value(nested)
                    if nested_value:
                        return nested_value
        return 0.0

    async def reconcile_live_balance(self, *, capital_usd: float, config: dict | None = None) -> dict | None:
        """Compare live collateral balance against internal estimates and persist a snapshot."""
        if self.dry_run:
            return None

        enabled = settings.reconciliation_enabled if config is None else bool(config.get("reconciliation_enabled", settings.reconciliation_enabled))
        if not enabled:
            return None

        client = await self._get_clob_client()
        if client is None or BalanceAllowanceParams is None or AssetType is None:
            return None

        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=int(settings.polymarket_signature_type),
        )
        try:
            response = await self._maybe_await(client.get_balance_allowance(params))
        except Exception as exc:
            logger.warning(f"Failed to fetch live balance allowance: {exc}")
            await send_telegram_alert(
                "warning",
                "Balance reconciliation failed",
                f"Could not fetch Polymarket collateral balance: {exc}",
                {"error": str(exc)},
            )
            return None

        live_balance = self._extract_balance_value(response)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'open' THEN size_usd ELSE 0 END), 0) AS open_size_usd,
                    COALESCE(SUM(CASE WHEN status = 'open' THEN unrealized_pnl ELSE 0 END), 0) AS unrealized_pnl_usd,
                    COALESCE(SUM(COALESCE(fee_usd, 0)), 0) AS fees_usd,
                    COALESCE(SUM(COALESCE(realized_pnl, 0)), 0) AS realized_pnl_usd,
                    COUNT(*)::int AS trade_count
                FROM trades
                """
            )
            open_size_usd = float(row["open_size_usd"] or 0.0)
            unrealized_pnl_usd = float(row["unrealized_pnl_usd"] or 0.0)
            fees_usd = float(row["fees_usd"] or 0.0)
            realized_pnl_usd = float(row["realized_pnl_usd"] or 0.0)
            trade_count = int(row["trade_count"] or 0)

        internal_cash_estimate = capital_usd + realized_pnl_usd - open_size_usd - fees_usd
        internal_equity_estimate = capital_usd + realized_pnl_usd + unrealized_pnl_usd - fees_usd
        discrepancy_usd = live_balance - internal_cash_estimate
        discrepancy_pct = abs(discrepancy_usd) / max(capital_usd, 1.0)

        warning_pct = float(settings.reconciliation_warning_pct if config is None else config.get("reconciliation_warning_pct", settings.reconciliation_warning_pct))
        critical_pct = float(settings.reconciliation_critical_pct if config is None else config.get("reconciliation_critical_pct", settings.reconciliation_critical_pct))
        warning_usd = float(settings.reconciliation_warning_usd if config is None else config.get("reconciliation_warning_usd", settings.reconciliation_warning_usd))
        critical_usd = float(settings.reconciliation_critical_usd if config is None else config.get("reconciliation_critical_usd", settings.reconciliation_critical_usd))

        status = "ok"
        if abs(discrepancy_usd) >= critical_usd or discrepancy_pct >= critical_pct:
            status = "critical"
        elif abs(discrepancy_usd) >= warning_usd or discrepancy_pct >= warning_pct:
            status = "warning"

        snapshot = {
            "source": "live",
            "live_collateral_balance": live_balance,
            "internal_cash_estimate": internal_cash_estimate,
            "internal_equity_estimate": internal_equity_estimate,
            "discrepancy_usd": discrepancy_usd,
            "discrepancy_pct": discrepancy_pct,
            "status": status,
            "details": {
                "capital_usd": capital_usd,
                "open_size_usd": open_size_usd,
                "unrealized_pnl_usd": unrealized_pnl_usd,
                "realized_pnl_usd": realized_pnl_usd,
                "fees_usd": fees_usd,
                "trade_count": trade_count,
                "warning_pct": warning_pct,
                "critical_pct": critical_pct,
                "warning_usd": warning_usd,
                "critical_usd": critical_usd,
            },
        }
        await insert_balance_reconciliation(snapshot)

        if status != "ok":
            level = "warning" if status == "warning" else "error"
            logger.warning(
                f"Live balance reconciliation {status}: "
                f"live={live_balance:.2f} internal={internal_cash_estimate:.2f} "
                f"discrepancy={discrepancy_usd:.2f} ({discrepancy_pct * 100.0:.2f}%)"
            )
            await send_telegram_alert(
                level,
                "Balance reconciliation alert",
                (
                    f"Status={status}; live=${live_balance:.2f}; internal=${internal_cash_estimate:.2f}; "
                    f"delta=${discrepancy_usd:.2f} ({discrepancy_pct * 100.0:.2f}%)"
                ),
                snapshot["details"],
            )
        else:
            logger.info(
                f"Live balance reconciliation ok: "
                f"live={live_balance:.2f} internal={internal_cash_estimate:.2f} "
                f"delta={discrepancy_usd:.2f}"
            )

        return snapshot

    async def update_positions(self, market_prices: dict):
        """Update unrealized P&L for all open positions."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, market_id, side, size_usd, entry_price FROM positions WHERE status = 'open'"
            )
            for row in rows:
                current_yes_price = market_prices.get(row["market_id"])
                if current_yes_price is None:
                    continue

                current_token_price = _token_price(row["side"], current_yes_price)
                pnl = (current_token_price - row["entry_price"]) * row["size_usd"] / row["entry_price"]
                pnl_pct = pnl / row["size_usd"] if row["size_usd"] > 0 else 0

                await conn.execute("""
                    UPDATE positions SET
                        current_price = $1,
                        unrealized_pnl = $2,
                        unrealized_pnl_pct = $3
                    WHERE id = $4
                """, current_token_price, pnl, pnl_pct * 100, row["id"])
