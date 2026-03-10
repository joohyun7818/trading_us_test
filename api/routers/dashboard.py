# GET summary/sectors/signals/stocks 대시보드 라우터
import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.core.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_summary() -> dict:
    """대시보드 요약 정보를 반환한다."""
    total_stocks = await fetch_one("SELECT COUNT(*) as cnt FROM stocks WHERE is_sp500 = TRUE")
    total_signals = await fetch_one(
        "SELECT COUNT(*) as cnt FROM signals WHERE created_at > NOW() - INTERVAL '24 hours'"
    )
    active_positions = await fetch_one("SELECT COUNT(*) as cnt FROM portfolio")
    total_trades = await fetch_one(
        "SELECT COUNT(*) as cnt FROM trades WHERE created_at > NOW() - INTERVAL '24 hours'"
    )
    today_pnl = await fetch_one(
        "SELECT COALESCE(SUM(pnl), 0) as total_pnl FROM trades WHERE created_at::date = CURRENT_DATE AND pnl IS NOT NULL"
    )
    total_value = await fetch_one(
        "SELECT COALESCE(SUM(qty * current_price), 0) as total FROM portfolio"
    )
    macro = await fetch_one(
        "SELECT regime, regime_score FROM macro_regime ORDER BY created_at DESC LIMIT 1"
    )

    return {
        "total_stocks": total_stocks["cnt"] if total_stocks else 0,
        "today_signals": total_signals["cnt"] if total_signals else 0,
        "active_positions": active_positions["cnt"] if active_positions else 0,
        "today_trades": total_trades["cnt"] if total_trades else 0,
        "today_pnl": float(today_pnl["total_pnl"]) if today_pnl else 0,
        "portfolio_value": float(total_value["total"]) if total_value else 0,
        "macro_regime": macro["regime"] if macro else "UNKNOWN",
        "macro_score": float(macro["regime_score"]) if macro else 0.5,
    }


@router.get("/sectors")
async def get_sectors() -> list[dict]:
    """섹터별 통계를 반환한다."""
    rows = await fetch_all(
        """
        SELECT s.name as sector_name,
               COUNT(st.id) as stock_count,
               ROUND(AVG(st.rsi_14)::numeric, 2) as avg_rsi,
               ROUND(AVG(st.price_change_pct)::numeric, 2) as avg_change_pct,
               ROUND(AVG(
                   (SELECT AVG(na.sentiment_score)
                    FROM news_articles na
                    WHERE na.stock_symbol = st.symbol
                      AND na.published_at > NOW() - INTERVAL '7 days')
               )::numeric, 4) as avg_sentiment
        FROM sectors s
        JOIN stocks st ON st.sector_id = s.id AND st.is_sp500 = TRUE
        GROUP BY s.name
        ORDER BY s.name
        """
    )
    return rows


@router.get("/signals")
async def get_signals(
    limit: int = Query(default=50, ge=1, le=200),
    signal_type: Optional[str] = Query(default=None),
) -> list[dict]:
    """최근 시그널 목록을 반환한다."""
    if signal_type:
        rows = await fetch_all(
            """
            SELECT id, stock_symbol, signal_type, final_score,
                   text_score, numeric_score, visual_score, macro_score,
                   analysis_mode, rationale, adjustments, executed, created_at
            FROM signals
            WHERE signal_type = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            signal_type, limit,
        )
    else:
        rows = await fetch_all(
            """
            SELECT id, stock_symbol, signal_type, final_score,
                   text_score, numeric_score, visual_score, macro_score,
                   analysis_mode, rationale, adjustments, executed, created_at
            FROM signals
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return rows


@router.get("/stocks")
async def get_stocks(
    sector: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """종목 목록을 반환한다."""
    if sector:
        rows = await fetch_all(
            """
            SELECT st.symbol, st.name, s.name as sector_name,
                   st.current_price, st.price_change_pct, st.rsi_14,
                   st.macd, st.volume_ratio, st.updated_at
            FROM stocks st
            LEFT JOIN sectors s ON s.id = st.sector_id
            WHERE st.is_sp500 = TRUE AND s.name = $1
            ORDER BY st.symbol
            LIMIT $2
            """,
            sector, limit,
        )
    else:
        rows = await fetch_all(
            """
            SELECT st.symbol, st.name, s.name as sector_name,
                   st.current_price, st.price_change_pct, st.rsi_14,
                   st.macd, st.volume_ratio, st.updated_at
            FROM stocks st
            LEFT JOIN sectors s ON s.id = st.sector_id
            WHERE st.is_sp500 = TRUE
            ORDER BY st.symbol
            LIMIT $1
            """,
            limit,
        )
    return rows
