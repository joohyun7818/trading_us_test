# 성과 추적 API 라우터
import logging

from fastapi import APIRouter, Query

from api.services.performance_tracker import (
    create_daily_snapshot,
    generate_weekly_report,
    get_daily_snapshots,
    get_score_vs_return,
    get_signal_performance_summary,
    get_weekly_reports,
    register_recent_signals,
    update_signal_performance,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.post("/signals/register")
async def trigger_signal_registration() -> dict:
    """최근 시그널을 성과 추적에 등록한다."""
    count = await register_recent_signals()
    return {"status": "ok", "registered": count}


@router.post("/signals/update")
async def trigger_performance_update() -> dict:
    """시그널 성과를 업데이트한다."""
    return await update_signal_performance()


@router.get("/signals/summary")
async def get_performance_summary(
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    """시그널 성과 요약."""
    return await get_signal_performance_summary(days)


@router.get("/signals/scatter")
async def get_scatter_data(
    days: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """Score vs Return 산점도 데이터."""
    return await get_score_vs_return(days)


@router.post("/snapshot")
async def trigger_daily_snapshot() -> dict:
    """일별 스냅샷을 수동 생성한다."""
    return await create_daily_snapshot()


@router.get("/snapshots")
async def get_snapshots(
    limit: int = Query(default=30, ge=1, le=365),
) -> list[dict]:
    """일별 스냅샷 이력."""
    return await get_daily_snapshots(limit)


@router.post("/report/weekly")
async def trigger_weekly_report() -> dict:
    """주간 리포트를 수동 생성한다."""
    return await generate_weekly_report()


@router.get("/reports")
async def get_reports(
    limit: int = Query(default=12, ge=1, le=52),
) -> list[dict]:
    """주간 리포트 이력."""
    return await get_weekly_reports(limit)
