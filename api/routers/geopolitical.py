"""국제정세 관련 API 엔드포인트."""
import logging

from fastapi import APIRouter, Query

from api.core.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/geopolitical", tags=["geopolitical"])


@router.post("/crawl")
async def trigger_geopolitical_crawl() -> dict:
    """국제정세 뉴스를 수동 수집한다."""
    from api.services.geopolitical_engine import crawl_geopolitical_news
    result = await crawl_geopolitical_news()
    return result


@router.post("/regime")
async def trigger_regime_calculation() -> dict:
    """국제정세 리스크 레짐을 계산한다."""
    from api.services.geopolitical_engine import calculate_geopolitical_regime
    result = await calculate_geopolitical_regime()
    return result


@router.get("/events")
async def get_recent_events(
    limit: int = Query(default=50, ge=1, le=200),
    hours: int = Query(default=48, ge=1, le=168),
) -> list[dict]:
    """최근 국제정세 이벤트를 반환한다."""
    rows = await fetch_all(
        """
        SELECT id, title, body, source, url, published_at, crawled_at,
               category, severity, sentiment_score, market_impact_score,
               affected_regions, affected_sectors,
               is_escalation, crisis_id
        FROM geopolitical_events
        WHERE crawled_at > NOW() - ($1 || ' hours')::INTERVAL
        ORDER BY market_impact_score DESC, crawled_at DESC
        LIMIT $2
        """,
        str(hours), limit,
    )
    return rows


@router.get("/regime/current")
async def get_current_regime() -> dict:
    """현재 국제정세 레짐을 반환한다."""
    row = await fetch_one(
        """
        SELECT id, war_risk, financial_crisis_risk, sanctions_risk,
               pandemic_risk, political_risk, trade_war_risk,
               terrorism_risk, natural_disaster_risk,
               composite_risk, risk_regime, risk_trend,
               market_sentiment_impact, safe_haven_signal,
               top_events, created_at
        FROM geopolitical_regime
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    if not row:
        return {"risk_regime": "UNKNOWN", "composite_risk": 0, "message": "No regime data yet"}
    return row


@router.get("/regime/history")
async def get_regime_history(
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict]:
    """국제정세 레짐 이력을 반환한다."""
    rows = await fetch_all(
        """
        SELECT composite_risk, risk_regime, risk_trend,
               market_sentiment_impact, safe_haven_signal, created_at
        FROM geopolitical_regime
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    return rows
