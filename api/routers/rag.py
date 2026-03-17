# POST index, GET status, POST analysis/{symbol}, GET history RAG 라우터
import logging

from fastapi import APIRouter, Query, Depends

from api.core.auth import verify_api_key
from api.services.news_indexer import get_index_status, index_unembedded_articles
from api.services.rag_analyzer import analyze_stock, get_analysis_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/index", dependencies=[Depends(verify_api_key)])
async def trigger_indexing() -> dict:
    """미임베딩 뉴스 기사를 수동으로 인덱싱한다."""
    result = await index_unembedded_articles()
    return result


@router.get("/status")
async def get_rag_status() -> dict:
    """RAG 인덱싱 상태를 반환한다."""
    return await get_index_status()


@router.post("/analysis/{symbol}", dependencies=[Depends(verify_api_key)])
async def run_rag_analysis(symbol: str) -> dict:
    """특정 종목에 대한 RAG 심층 분석을 실행한다."""
    result = await analyze_stock(symbol.upper())
    return {"symbol": symbol.upper(), "analysis": result}


@router.get("/history/{symbol}")
async def get_rag_history(
    symbol: str,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    """종목의 RAG 분석 이력을 반환한다."""
    rows = await get_analysis_history(symbol.upper(), limit=limit)
    result = []
    for row in rows:
        result.append({
            "stock_symbol": row["stock_symbol"],
            "analysis_type": row["analysis_type"],
            "model_used": row["model_used"],
            "result": row["result"],
            "created_at": str(row["created_at"]),
        })
    return result
