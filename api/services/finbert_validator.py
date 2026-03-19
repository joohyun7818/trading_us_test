import logging
from datetime import datetime, timedelta

import numpy as np
from api.core.database import fetch_all, fetch_one
from api.services.finbert_sentiment import finbert_analyzer
from api.services.sentiment import analyze_sentiment_keywords

logger = logging.getLogger(__name__)


async def validate_finbert_vs_keyword(days: int = 90) -> dict:
    """최근 뉴스를 분석하여 키워드 vs FinBERT의 수익률 상관관계를 비교한다."""
    start_date = (datetime.now() - timedelta(days=days)).date()

    # stock_daily의 가장 최근 날짜를 조회하여 그보다 5일 이상 전인 뉴스만 불러온다.
    max_date_row = await fetch_one("SELECT MAX(trade_date) as max_date FROM stock_daily")
    if not max_date_row or not max_date_row["max_date"]:
        return {"error": "No price data in stock_daily", "sample_count": 0}
    
    max_price_date = max_date_row["max_date"]
    
    # 최근 90일 ~ (max_price_date - 5일) 전 뉴스 로드 (최대 2000건)
    query = """
        SELECT stock_symbol as symbol, title, body as content, 
               COALESCE(published_at, crawled_at)::date as trade_date, 
               sentiment_score as keyword_score
        FROM news_articles
        WHERE COALESCE(published_at, crawled_at) >= $1
          AND COALESCE(published_at, crawled_at) <= ($2::date - INTERVAL '5 days')
        ORDER BY COALESCE(published_at, crawled_at) DESC
        LIMIT 2000
    """
    articles = await fetch_all(query, start_date, max_price_date)
    if not articles:
        return {"error": "No articles found in the given range", "sample_count": 0}

    results = []
    for art in articles:
        symbol = art["symbol"]
        trade_date = art["trade_date"]
        
        # 5일 후 수익률 조회 (시점 대비 가장 가까운 미래 가격)
        five_days_later = trade_date + timedelta(days=5)
        price_query = """
            WITH start_price AS (
                SELECT close FROM stock_daily WHERE symbol = $1 AND trade_date <= $2 ORDER BY trade_date DESC LIMIT 1
            ), end_price AS (
                SELECT close FROM stock_daily WHERE symbol = $1 AND trade_date >= $3 ORDER BY trade_date ASC LIMIT 1
            )
            SELECT (e.close - s.close) / s.close * 100 as ret
            FROM start_price s, end_price e
        """
        ret_row = await fetch_one(price_query, symbol, trade_date, five_days_later)
        if not ret_row or ret_row["ret"] is None:
            continue

        # FinBERT 분석 (제목 + 본문 일부)
        text_to_analyze = f"{art['title']} {art['content'][:200]}"
        finbert_res = await finbert_analyzer.analyze(text_to_analyze)
        
        results.append({
            "keyword_score": float(art["keyword_score"] or 0.0),
            "finbert_score": float(finbert_res["sentiment_score"]),
            "return_5d": float(ret_row["ret"])
        })

    if len(results) < 10:
        return {"error": "Insufficient samples with price data", "sample_count": len(results)}

    # 상관관계 계산 (Pearson)
    kw_scores = [r["keyword_score"] for r in results]
    fb_scores = [r["finbert_score"] for r in results]
    returns = [r["return_5d"] for r in results]

    kw_corr = np.corrcoef(kw_scores, returns)[0, 1]
    fb_corr = np.corrcoef(fb_scores, returns)[0, 1]
    
    # NaN 처리
    kw_corr = 0.0 if np.isnan(kw_corr) else float(kw_corr)
    fb_corr = 0.0 if np.isnan(fb_corr) else float(fb_corr)
    
    improvement = fb_corr - kw_corr
    recommendation = "adopt_finbert" if fb_corr > (kw_corr + 0.03) else "keep_text_zero"
    
    if fb_corr <= 0 and kw_corr <= 0:
        recommendation = "keep_text_zero" # 둘 다 예측력이 없으면 감성분석 제외 권장

    return {
        "keyword_corr_5d": round(kw_corr, 4),
        "finbert_corr_5d": round(fb_corr, 4),
        "improvement": round(improvement, 4),
        "sample_count": len(results),
        "recommendation": recommendation,
        "details": f"FinBERT Correlation: {fb_corr:.4f}, Keyword Correlation: {kw_corr:.4f}"
    }
