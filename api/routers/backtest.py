from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services.backtester import BacktestConfig, get_backtest_result, run_backtest
from api.services.backtest_reporter import compare_reports, generate_report
from api.services.historical_loader import get_history_status, load_history

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class CompareRequest(BaseModel):
    ids: list[str]


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


@router.post("/run")
async def run_backtest_api(config: BacktestConfig) -> dict:
    """백테스트를 실행하고 결과를 반환한다."""
    try:
        return await run_backtest(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/results/{backtest_id}")
async def get_backtest_results(backtest_id: str) -> dict:
    """저장된 백테스트 결과를 조회한다."""
    result = await get_backtest_result(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="backtest result not found")
    return result


@router.get("/results/{backtest_id}/report")
async def get_backtest_report(backtest_id: str) -> dict:
    """백테스트 결과를 분석하고 자동 진단 리포트를 생성한다."""
    try:
        return await generate_report(backtest_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/compare")
async def compare_backtests(request: CompareRequest) -> dict:
    """여러 백테스트의 주요 지표를 비교한다."""
    if not request.ids:
        raise HTTPException(status_code=400, detail="ids list cannot be empty")
    return await compare_reports(request.ids)
