# GET regime/history, leveraged status/config, settings CRUD 매크로 라우터
import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.core.database import execute, fetch_all, fetch_one
from api.services.macro_engine import calculate_regime, get_regime_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/macro", tags=["macro"])


class SettingUpdate(BaseModel):
    """설정 업데이트 요청 모델."""
    value: str


@router.get("/regime")
async def get_current_regime() -> dict:
    """현재 매크로 레짐을 반환한다."""
    row = await fetch_one(
        """
        SELECT regime, regime_score, sp500_trend, vix_level,
               yield_curve_spread, market_rsi, market_breadth,
               put_call_ratio, macro_news_sentiment,
               leveraged_action, created_at
        FROM macro_regime
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return {"regime": "UNKNOWN", "regime_score": 0.5, "message": "No regime data yet"}
    return row


@router.post("/regime/calculate")
async def trigger_regime_calculation() -> dict:
    """매크로 레짐 계산을 수동 트리거한다."""
    result = await calculate_regime()
    return result


@router.get("/regime/history")
async def get_history(
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict]:
    """매크로 레짐 이력을 반환한다."""
    return await get_regime_history(limit=limit)


@router.get("/leveraged/status")
async def get_leveraged_status() -> dict:
    """레버리지 포지션 상태를 반환한다."""
    enabled_row = await fetch_one("SELECT value FROM settings WHERE key = 'leveraged_enabled'")
    enabled = enabled_row["value"].lower() == "true" if enabled_row else False

    open_positions = await fetch_all(
        """
        SELECT id, symbol, side, qty, entry_price, current_price,
               stop_loss, take_profit, entry_date, max_hold_days,
               consecutive_extreme_days, status, order_id, created_at
        FROM leveraged_positions
        WHERE status = 'open'
        ORDER BY created_at DESC
        """
    )

    closed_positions = await fetch_all(
        """
        SELECT id, symbol, side, qty, entry_price, current_price,
               stop_loss, take_profit, entry_date, status, pnl,
               closed_at, created_at
        FROM leveraged_positions
        WHERE status != 'open'
        ORDER BY closed_at DESC
        LIMIT 20
        """
    )

    return {
        "enabled": enabled,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
    }


@router.get("/leveraged/config")
async def get_leveraged_config() -> dict:
    """레버리지 설정을 반환한다."""
    keys = [
        "leveraged_enabled", "leveraged_max_pct", "leveraged_stop_loss",
        "leveraged_take_profit", "leveraged_max_hold_days", "leveraged_min_extreme_days",
    ]
    config = {}
    for key in keys:
        row = await fetch_one("SELECT value FROM settings WHERE key = $1", key)
        config[key] = row["value"] if row else None
    return config


@router.get("/settings")
async def get_all_settings() -> list[dict]:
    """모든 설정을 반환한다."""
    rows = await fetch_all(
        "SELECT key, value, description, updated_at FROM settings ORDER BY key"
    )
    return rows


@router.get("/settings/{key}")
async def get_setting(key: str) -> dict:
    """특정 설정을 반환한다."""
    row = await fetch_one(
        "SELECT key, value, description, updated_at FROM settings WHERE key = $1", key,
    )
    if not row:
        return {"error": f"Setting '{key}' not found"}
    return row


@router.put("/settings/{key}")
async def update_setting(key: str, body: SettingUpdate) -> dict:
    """설정을 업데이트한다."""
    existing = await fetch_one("SELECT key FROM settings WHERE key = $1", key)
    if not existing:
        return {"error": f"Setting '{key}' not found"}

    await execute(
        "UPDATE settings SET value = $1, updated_at = NOW() WHERE key = $2",
        body.value, key,
    )
    logger.info("Setting updated: %s = %s", key, body.value)
    return {"status": "ok", "key": key, "value": body.value}
