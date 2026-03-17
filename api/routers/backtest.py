from fastapi import APIRouter, Query

from api.services.historical_loader import get_history_status, load_history

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("/load-history")
async def trigger_load_history(
    incremental: bool = Query(default=True),
) -> dict:
    """히스토리컬 OHLCV + 기술지표 적재를 트리거한다."""
    return await load_history(incremental=incremental)


@router.get("/history-status")
async def history_status() -> dict:
    """히스토리컬 데이터 적재 상태를 반환한다."""
    return await get_history_status()
