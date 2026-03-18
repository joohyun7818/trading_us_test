import logging
from typing import Any

from api.core.database import fetch_one

logger = logging.getLogger(__name__)


async def _get_setting_float(key: str, default: float) -> float:
    """settings 테이블에서 float 설정값을 조회한다."""
    row = await fetch_one("SELECT value FROM settings WHERE key = $1", key)
    if not row:
        return default
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        logger.warning("Invalid float setting for %s=%s, fallback=%s", key, row.get("value"), default)
        return default


async def _get_setting_int(key: str, default: int) -> int:
    """settings 테이블에서 int 설정값을 조회한다."""
    row = await fetch_one("SELECT value FROM settings WHERE key = $1", key)
    if not row:
        return default
    try:
        return int(float(row["value"]))
    except (TypeError, ValueError):
        logger.warning("Invalid int setting for %s=%s, fallback=%s", key, row.get("value"), default)
        return default


async def evaluate_exit(position: dict[str, Any]) -> dict[str, Any]:
    """동적 청산 규칙을 평가해 청산 여부와 수량을 반환한다."""
    symbol = str(position.get("symbol", "UNKNOWN"))
    entry_price = float(position.get("entry_price") or 0.0)
    current_price = float(position.get("current_price") or 0.0)
    highest_price = float(position.get("highest_price_since_entry") or current_price or 0.0)
    days_held = int(position.get("days_held") or 0)
    raw_entry_atr = float(position.get("entry_atr") or 0.0)
    quantity = float(position.get("quantity") or 0.0)

    if quantity <= 0 or entry_price <= 0 or current_price <= 0:
        return {
            "should_exit": False,
            "exit_reason": "hold",
            "exit_quantity": 0,
            "details": f"{symbol}: invalid position values",
        }

    hard_stop_mult = await _get_setting_float("hard_stop_atr_mult", 2.5)
    trail_mult = await _get_setting_float("trailing_stop_atr_mult", 2.0)
    max_holding_days = await _get_setting_int("max_holding_days", 20)
    partial_mult = await _get_setting_float("partial_exit_atr_mult", 3.0)

    entry_atr = raw_entry_atr if raw_entry_atr > 0 else entry_price * 0.02
    full_exit_qty = max(1, int(quantity))
    partial_exit_qty = max(1, int(quantity * 0.5))

    hard_stop_price = entry_price - (entry_atr * hard_stop_mult)
    if current_price <= hard_stop_price:
        return {
            "should_exit": True,
            "exit_reason": "atr_hard_stop",
            "exit_quantity": full_exit_qty,
            "details": f"{symbol}: current={current_price:.4f} <= hard_stop={hard_stop_price:.4f}",
        }

    trail_active = highest_price > (entry_price * 1.01)
    if trail_active:
        trail_stop_price = highest_price - (entry_atr * trail_mult)
        if current_price <= trail_stop_price:
            return {
                "should_exit": True,
                "exit_reason": "trailing_stop",
                "exit_quantity": full_exit_qty,
                "details": f"{symbol}: current={current_price:.4f} <= trail_stop={trail_stop_price:.4f}",
            }

    if days_held >= max_holding_days:
        return {
            "should_exit": True,
            "exit_reason": "time_limit",
            "exit_quantity": full_exit_qty,
            "details": f"{symbol}: days_held={days_held} >= {max_holding_days}",
        }

    pnl_atr_multiple = (current_price - entry_price) / entry_atr if entry_atr > 0 else 0.0
    if pnl_atr_multiple >= partial_mult and quantity > 1:
        return {
            "should_exit": True,
            "exit_reason": "partial_take_profit",
            "exit_quantity": partial_exit_qty,
            "details": f"{symbol}: atr_multiple={pnl_atr_multiple:.4f} >= {partial_mult}",
        }

    return {
        "should_exit": False,
        "exit_reason": "hold",
        "exit_quantity": 0,
        "details": f"{symbol}: no exit condition met",
    }
