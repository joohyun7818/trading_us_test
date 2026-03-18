# 5분 자동매매 루프 + 30분 레버리지 루프
import logging
from datetime import datetime, timezone
from typing import Optional

from api.core.database import execute, fetch_all, fetch_one
from api.services.alpaca_client import get_positions, submit_order, get_latest_price
from api.services.exit_manager import evaluate_exit
from api.services.macro_engine import calculate_regime
from api.services.position_sizer import calculate_position_size
from api.services.trading_engine import analyze_and_signal

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

            if signal_type == "BUY":
                # ATR 기반 포지션 사이징 사용 여부 확인
                use_atr_sizing_row = await fetch_one(
                    "SELECT value FROM settings WHERE key = 'use_atr_sizing'"
                )
                use_atr_sizing = (
                    use_atr_sizing_row and use_atr_sizing_row["value"].lower() == "true"
                ) if use_atr_sizing_row else False

                if use_atr_sizing:
                    # 계좌 자산 조회
                    total_capital_row = await fetch_one(
                        "SELECT value FROM settings WHERE key = 'total_capital'"
                    )
                    account_equity = (
                        float(total_capital_row["value"]) if total_capital_row else 100000.0
                    )

                    # 최대 포지션 수 조회
                    max_pos_row = await fetch_one(
                        "SELECT value FROM settings WHERE key = 'max_positions'"
                    )
                    max_positions = int(max_pos_row["value"]) if max_pos_row else 20

                    # 현재 포지션 조회
                    current_positions = await fetch_all(
                        """
                        SELECT stock_symbol, qty, avg_price
                        FROM portfolio
                        """
                    )

                    # 포지션 사이징 계산
                    final_score = sig.get("final_score", 50.0)
                    sizing_result = await calculate_position_size(
                        symbol=symbol,
                        signal_score=final_score,
                        account_equity=account_equity,
                        current_positions=current_positions,
                        max_positions=max_positions,
                    )

                    order_amount = sizing_result.get("order_amount", 0.0)
                    qty = sizing_result.get("quantity", 0)
                    sizing_reason = sizing_result.get("sizing_reason", "unknown")

                    if order_amount <= 0 or qty <= 0:
                        logger.info(
                            "Skip BUY %s: order_amount=%.2f qty=%d reason=%s",
                            symbol,
                            order_amount,
                            qty,
                            sizing_reason,
                        )
                        skipped += 1
                        continue

                    logger.info(
                        "ATR-based sizing for %s: amount=%.2f qty=%d atr=%.4f reason=%s",
                        symbol,
                        order_amount,
                        qty,
                        sizing_result.get("atr_14", 0.0),
                        sizing_reason,
                    )
                else:
                    # 기존 고정 금액 방식
                    max_amount_row = await fetch_one(
                        "SELECT value FROM settings WHERE key = 'max_order_amount'"
                    )
                    max_amount = float(max_amount_row["value"]) if max_amount_row else 1000.0

                    price = await get_latest_price(symbol)
                    if not price or price <= 0:
                        logger.warning("No price for %s, skip", symbol)
                        skipped += 1
                        continue

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

        try:
            positions = await fetch_all(
                """
                SELECT stock_symbol, qty, avg_price, highest_price, entry_atr
                FROM portfolio
                """
            )
        except Exception:
            logger.warning("portfolio.highest_price/entry_atr column missing, using fallback query")
            positions = await fetch_all("SELECT stock_symbol, qty, avg_price FROM portfolio")
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
            symbol = pos["stock_symbol"]
            realtime_position = None
            for rt_pos in (current_positions or []):
                if str(rt_pos.get("symbol", "")).upper() == str(symbol).upper():
                    realtime_position = rt_pos
                    break

            qty = float(realtime_position.get("qty", 0) or 0) if realtime_position else float(pos.get("qty", 0) or 0)
            if qty <= 0:
                continue

            current_price = (
                float(realtime_position.get("current_price", 0) or 0) if realtime_position else 0.0
            )
            if current_price <= 0:
                current_price = await get_latest_price(symbol)
            if not current_price or current_price <= 0:
                continue

            entry_price = (
                float(realtime_position.get("avg_entry_price", 0) or 0)
                if realtime_position
                else float(pos.get("avg_price", 0) or 0)
            )
            if entry_price <= 0:
                entry_price = current_price

            highest_price = float(pos.get("highest_price", 0) or 0)
            if highest_price <= 0:
                highest_price = current_price
            else:
                highest_price = max(highest_price, current_price)

            entry_atr = float(pos.get("entry_atr", 0) or 0)
            if entry_atr <= 0:
                trade_entry = await fetch_one(
                    """
                    SELECT entry_atr, created_at
                    FROM trades
                    WHERE stock_symbol = $1
                      AND LOWER(side) = 'buy'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    symbol,
                )
                if trade_entry:
                    entry_atr = float(trade_entry.get("entry_atr", 0) or 0)
                    entry_dt = trade_entry.get("created_at")
                else:
                    entry_dt = None
            else:
                trade_entry = await fetch_one(
                    """
                    SELECT created_at
                    FROM trades
                    WHERE stock_symbol = $1
                      AND LOWER(side) = 'buy'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    symbol,
                )
                entry_dt = trade_entry.get("created_at") if trade_entry else None

            if entry_atr <= 0:
                entry_atr = entry_price * 0.02

            days_held = 0
            if entry_dt:
                if isinstance(entry_dt, datetime):
                    entry_date = entry_dt.date()
                else:
                    entry_date = entry_dt
                days_held = max(0, (datetime.now(timezone.utc).date() - entry_date).days)

            try:
                await execute(
                    """
                    UPDATE portfolio
                    SET highest_price = $1,
                        entry_atr = COALESCE(entry_atr, $2)
                    WHERE stock_symbol = $3
                    """,
                    highest_price,
                    entry_atr,
                    symbol,
                )
            except Exception:
                logger.debug("Skip portfolio highest_price/entry_atr update for %s", symbol)

            exit_signal = await evaluate_exit(
                {
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "highest_price_since_entry": highest_price,
                    "days_held": days_held,
                    "entry_atr": entry_atr,
                    "quantity": qty,
                }
            )
            if exit_signal.get("should_exit"):
                sell_qty = min(qty, float(exit_signal.get("exit_quantity", 0) or 0))
                if sell_qty <= 0:
                    continue
                result = await submit_order(
                    symbol=symbol,
                    qty=sell_qty,
                    side="sell",
                )
                if result.get("status") == "ok":
                    try:
                        await execute(
                            "UPDATE trades SET exit_reason = $1 WHERE order_id = $2",
                            exit_signal.get("exit_reason"),
                            result.get("order_id"),
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to persist exit_reason for order %s: %s",
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
