import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.finbert_sentiment import finbert_analyzer
from api.services.finbert_validator import validate_finbert_vs_keyword

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/finbert", tags=["FinBERT"])


class AnalyzeRequest(BaseModel):
    text: str


@router.post("/analyze")
async def analyze_text(req: AnalyzeRequest) -> dict[str, Any]:
    """단일 텍스트에 대한 FinBERT 감성 분석을 수행한다."""
    try:
        return await finbert_analyzer.analyze(req.text)
    except Exception as e:
        logger.error("FinBERT analysis endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_finbert(days: int = 90) -> dict[str, Any]:
    """키워드 기반 분석과 FinBERT 분석의 과거 성과(수익률 상관관계)를 비교한다."""
    try:
        return await validate_finbert_vs_keyword(days=days)
    except Exception as e:
        logger.error("FinBERT validation endpoint failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
