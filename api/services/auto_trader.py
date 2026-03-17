# 5분 자동매매 루프 + 30분 레버리지 루프
import logging
from datetime import datetime, timezone
from typing import Optional

from api.core.database import execute, fetch_all, fetch_one
from api.services.alpaca_client import get_positions, submit_order, get_latest_price
from api.services.macro_engine import calculate_regime
from api.services.trading_engine import analyze_and_signal, check_exit

logger = logging.getLogger(__name__)

_trading_running = False
_leveraged_running = False


async def auto_trade_loop() -> dict:
    """5분 자동매매 루프: BUY/SELL 시그널 → 주문 실행."""
    global _trading_running
    if _trading_running:
        return {"status": "already_running"}
    _trading_running = True

    try:
        signals = await fetch_all(
            """
            SELECT id, stock_symbol, signal_type, final_score
            FROM signals
            WHERE executed = FALSE
              AND created_at > NOW() - INTERVAL '1 hour'
            ORDER BY final_score DESC
            """
        )

        executed = 0
        skipped = 0

        for sig in signals:
            symbol = sig["stock_symbol"]
            signal_type = sig["signal_type"]
            signal_id = sig["id"]

            if signal_type == "HOLD":
                skipped += 1
                continue

            max_amount_row = await fetch_one("SELECT value FROM settings WHERE key = 'max_order_amount'")
            max_amount = float(max_amount_row["value"]) if max_amount_row else 1000.0

            price = await get_latest_price(symbol)
            if not price or price <= 0:
                logger.warning("No price for %s, skip", symbol)
                skipped += 1
                continue

            if signal_type == "BUY":
                qty = max(1, int(max_amount / price))
                result = await submit_order(
                    symbol=symbol, qty=qty, side="buy", signal_id=signal_id,
                )
            elif signal_type == "SELL":
                position = await fetch_one(
                    "SELECT qty FROM portfolio WHERE stock_symbol = $1", symbol,
                )
                if not position:
                    skipped += 1
                    continue
                qty = float(position["qty"])
                result = await submit_order(
                    symbol=symbol, qty=qty, side="sell", signal_id=signal_id,
                )
            else:
                skipped += 1
                continue

            if result.get("status") == "ok":
                await execute(
                    "UPDATE signals SET executed = TRUE WHERE id = $1", signal_id,
                )
                executed += 1
            else:
                logger.warning("Order failed for %s: %s", symbol, result.get("error"))
                skipped += 1

        positions = await fetch_all("SELECT stock_symbol FROM portfolio")
        current_positions: Optional[list[dict]] = None
        try:
            current_positions = await get_positions()
        except Exception as e:
            logger.warning(
                "Failed to fetch Alpaca realtime positions, fallback to stale portfolio data: %s",
                e,
            )

        if current_positions == [] and positions:
            logger.warning(
                "Alpaca realtime positions unavailable/empty, fallback to stale portfolio data"
            )
            current_positions = None

        exits = 0
        for pos in positions:
            exit_signal = await check_exit(
                pos["stock_symbol"], current_positions=current_positions
            )
            if exit_signal:
                result = await submit_order(
                    symbol=exit_signal["symbol"],
                    qty=exit_signal["qty"],
                    side="sell",
                )
                if result.get("status") == "ok":
                    if exit_signal.get("trigger_reason") == "stop_loss":
                        logger.warning(
                            "Stop-loss sell executed for %s: %s",
                            exit_signal["symbol"], exit_signal["reason"],
                        )
                        try:
                            await execute(
                                "UPDATE trades SET trigger_reason = $1 WHERE order_id = $2",
                                exit_signal["trigger_reason"],
                                result.get("order_id"),
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to persist trigger_reason for order %s: %s",
                                result.get("order_id"),
                                e,
                            )
                    exits += 1

        logger.info("Auto-trade: executed=%d skipped=%d exits=%d", executed, skipped, exits)
        return {
            "status": "ok",
            "executed": executed,
            "skipped": skipped,
            "exits": exits,
        }

    except Exception as e:
        logger.error("Auto-trade loop failed: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        _trading_running = False


async def leveraged_loop() -> dict:
    """30분 레버리지 루프: TQQQ/SQQQ 전략 실행."""
    global _leveraged_running
    if _leveraged_running:
        return {"status": "already_running"}
    _leveraged_running = True

    try:
        enabled_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_enabled'")
        if not enabled_row or enabled_row["value"].lower() != "true":
            return {"status": "disabled"}

        regime_result = await calculate_regime()
        action = regime_result.get("leveraged_action", "hold")

        if action == "disabled":
            return {"status": "disabled"}

        if action.startswith("close_"):
            parts = action.split("_")
            symbol = parts[1] if len(parts) >= 2 else ""
            reason = parts[2] if len(parts) >= 3 else "unknown"

            position = await fetch_one(
                "SELECT * FROM leveraged_positions WHERE symbol = $1 AND status = 'open'", symbol,
            )
            if position:
                result = await submit_order(
                    symbol=symbol, qty=float(position["qty"]), side="sell",
                )
                if result.get("status") == "ok":
                    await execute(
                        """
                        UPDATE leveraged_positions
                        SET status = 'closed', closed_at = NOW(),
                            order_id = $1
                        WHERE id = $2
                        """,
                        result.get("order_id"), position["id"],
                    )
                    logger.info("Leveraged position closed: %s reason=%s", symbol, reason)
            return {"status": "closed", "symbol": symbol, "reason": reason}

        if action in ("buy_tqqq", "buy_sqqq"):
            symbol = "TQQQ" if action == "buy_tqqq" else "SQQQ"

            existing = await fetch_one(
                "SELECT id FROM leveraged_positions WHERE status = 'open'"
            )
            if existing:
                return {"status": "already_positioned"}

            max_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_max_pct'")
            max_pct = float(max_pct_row["value"]) if max_pct_row else 0.03

            total_cap_row = await fetch_one("SELECT value FROM settings WHERE key = 'total_capital'")
            total_capital = float(total_cap_row["value"]) if total_cap_row else 100000.0

            max_invest = total_capital * max_pct
            price = await get_latest_price(symbol)
            if not price or price <= 0:
                return {"status": "no_price"}

            qty = max(1, int(max_invest / price))

            sl_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_stop_loss'")
            tp_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_take_profit'")
            max_hold_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_max_hold_days'")

            sl_pct = float(sl_pct_row["value"]) if sl_pct_row else 0.08
            tp_pct = float(tp_pct_row["value"]) if tp_pct_row else 0.15
            max_hold = int(max_hold_row["value"]) if max_hold_row else 5

            stop_loss = round(price * (1 - sl_pct), 4)
            take_profit = round(price * (1 + tp_pct), 4)

            result = await submit_order(symbol=symbol, qty=qty, side="buy")
            if result.get("status") == "ok":
                from datetime import date
                await execute(
                    """
                    INSERT INTO leveraged_positions
                        (symbol, side, qty, entry_price, stop_loss, take_profit,
                         entry_date, max_hold_days, order_id)
                    VALUES ($1, 'buy', $2, $3, $4, $5, $6, $7, $8)
                    """,
                    symbol, qty, price, stop_loss, take_profit,
                    date.today(), max_hold, result.get("order_id"),
                )
                logger.info("Leveraged position opened: %s qty=%d price=%.2f", symbol, qty, price)
                return {"status": "opened", "symbol": symbol, "qty": qty, "price": price}

            return {"status": "order_failed", "error": result.get("error")}

        return {"status": "hold", "action": action}

    except Exception as e:
        logger.error("Leveraged loop failed: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        _leveraged_running = False
