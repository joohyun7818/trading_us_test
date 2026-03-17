# 파일: api/services/geopolitical_engine.py
"""국제 정세 위기 수집 + 분석 + 리스크 스코어 산출 엔진."""
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import feedparser

from api.core.database import execute, fetch_all, fetch_one
from api.services.sentiment import analyze_sentiment_keywords

logger = logging.getLogger(__name__)

# ── 국제 정세 뉴스 소스 ────────────────────────────────────
GEOPOLITICAL_QUERIES = [
    "war conflict military attack",
    "financial crisis bank collapse recession",
    "sanctions embargo trade restriction",
    "terrorism attack security threat",
    "pandemic epidemic outbreak WHO",
    "political instability coup election crisis",
    "natural disaster earthquake hurricane flood",
    "trade war tariff duties import export",
    "nuclear threat missile test",
    "oil crisis OPEC energy supply disruption",
    "currency crisis inflation hyperinflation",
    "cyber attack infrastructure",
    "Middle East tension Iran Israel",
    "Russia Ukraine NATO",
    "China Taiwan geopolitical",
    "US debt ceiling government shutdown",
]

# ── 카테고리 분류 키워드 ────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "war": [
        "war", "military", "attack", "invasion", "bombing", "airstrike",
        "missile", "troops", "combat", "conflict", "armed", "artillery",
        "offensive", "ceasefire", "escalation", "nato", "defense",
        "casualties", "wounded", "killed", "battlefield",
    ],
    "financial_crisis": [
        "financial crisis", "bank collapse", "bank run", "credit crunch",
        "debt default", "sovereign debt", "lehman", "bailout", "contagion",
        "systemic risk", "liquidity crisis", "insolvency", "credit suisse",
        "bank failure", "deposit flight", "financial meltdown",
    ],
    "sanctions": [
        "sanctions", "embargo", "trade restriction", "asset freeze",
        "blacklist", "trade ban", "export control", "swift ban",
        "economic pressure", "financial sanctions",
    ],
    "pandemic": [
        "pandemic", "epidemic", "outbreak", "who emergency", "quarantine",
        "lockdown", "variant", "vaccine", "infection rate", "covid",
        "bird flu", "h5n1", "public health emergency",
    ],
    "political": [
        "coup", "political crisis", "impeachment", "election fraud",
        "protest", "civil unrest", "revolution", "government collapse",
        "political instability", "regime change", "assassination",
    ],
    "trade_war": [
        "trade war", "tariff", "duties", "import ban", "export ban",
        "trade dispute", "wto", "protectionism", "retaliatory",
        "trade deficit", "decoupling",
    ],
    "terrorism": [
        "terrorism", "terrorist", "terror attack", "isis", "al qaeda",
        "extremist", "radicalized", "suicide bomb", "hostage",
    ],
    "natural_disaster": [
        "earthquake", "tsunami", "hurricane", "typhoon", "flood",
        "wildfire", "volcanic", "tornado", "drought", "landslide",
    ],
}

# ── 심각도 키워드 (가중치) ──────────────────────────────────
SEVERITY_KEYWORDS: dict[str, float] = {
    "nuclear": 9.5, "world war": 10.0, "global crisis": 9.0,
    "invasion": 8.0, "collapse": 8.5, "catastrophe": 9.0,
    "emergency": 7.0, "devastating": 7.5, "unprecedented": 7.0,
    "escalation": 7.5, "massive": 6.5, "severe": 6.5,
    "critical": 6.0, "urgent": 5.5, "major": 5.0,
    "significant": 4.5, "growing": 4.0, "concern": 3.5,
    "tension": 3.0, "risk": 2.5, "potential": 2.0, "minor": 1.5,
}

# ── 리스크 레짐별 가중치 ───────────────────────────────────
RISK_CATEGORY_WEIGHTS = {
    "war": 0.25,
    "financial_crisis": 0.20,
    "sanctions": 0.10,
    "pandemic": 0.10,
    "political": 0.10,
    "trade_war": 0.10,
    "terrorism": 0.05,
    "natural_disaster": 0.10,
}

# ── 섹터별 영향 매핑 ──────────────────────────────────────
CATEGORY_SECTOR_IMPACT: dict[str, list[str]] = {
    "war": ["Energy", "Defense", "Industrials", "Technology"],
    "financial_crisis": ["Financials", "Real Estate", "Consumer Discretionary"],
    "sanctions": ["Energy", "Technology", "Financials", "Materials"],
    "pandemic": ["Health Care", "Consumer Staples", "Technology", "Consumer Discretionary"],
    "political": ["Financials", "Utilities", "Communication Services"],
    "trade_war": ["Technology", "Industrials", "Materials", "Consumer Discretionary"],
    "terrorism": ["Consumer Discretionary", "Communication Services", "Industrials"],
    "natural_disaster": ["Utilities", "Real Estate", "Energy", "Industrials"],
}



def _strip_html(text: str) -> str:
    """HTML 태그를 제거하고 텍스트만 추출한다."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
    return re.sub(r'\s+', ' ', clean).strip()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _classify_category(text: str) -> str:
    """텍스트에서 국제 정세 카테고리를 분류한다."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score
    if not scores:
        return "political"  # 기본값
    return max(scores, key=scores.get)


def _calculate_severity(text: str) -> float:
    """텍스트에서 심각도(0~10)를 산출한다."""
    text_lower = text.lower()
    matched = []
    for kw, weight in SEVERITY_KEYWORDS.items():
        if kw in text_lower:
            matched.append(weight)
    if not matched:
        return 2.0
    return min(10.0, round(sum(sorted(matched, reverse=True)[:3]) / 3, 2))


def _estimate_market_impact(severity: float, category: str) -> float:
    """심각도와 카테고리로 시장 영향 점수를 추정한다. -1(극부정) ~ 0(중립)."""
    base_impact = -(severity / 10.0)
    category_multipliers = {
        "war": 1.0, "financial_crisis": 1.0, "nuclear": 1.0,
        "sanctions": 0.7, "pandemic": 0.8, "trade_war": 0.6,
        "terrorism": 0.5, "political": 0.4, "natural_disaster": 0.5,
    }
    multiplier = category_multipliers.get(category, 0.5)
    return round(max(-1.0, base_impact * multiplier), 4)


async def crawl_geopolitical_news() -> dict:
    """Google News RSS에서 국제 정세 뉴스를 수집한다."""
    enabled_row = await fetch_one(
        "SELECT value FROM settings WHERE key = 'geopolitical_enabled'"
    )
    if not enabled_row or enabled_row["value"].lower() != "true":
        return {"status": "disabled", "articles": 0}

    total_count = 0
    start_time = time.time()

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        for query in GEOPOLITICAL_QUERIES:
            try:
                url = (
                    f"https://news.google.com/rss/search?"
                    f"q={query}&hl=en-US&gl=US&ceid=US:en"
                )
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()

                feed = feedparser.parse(text)

                for entry in feed.entries[:5]:
                    entry_url = entry.get("link", "")
                    uh = _url_hash(entry_url)

                    # 중복 체크
                    existing = await fetch_one(
                        "SELECT id FROM geopolitical_events WHERE url_hash = $1", uh
                    )
                    if existing:
                        continue

                    title = entry.get("title", "")
                    summary = _strip_html(entry.get("summary", ""))
                    full_text = f"{title} {summary}"

                    category = _classify_category(full_text)
                    severity = _calculate_severity(full_text)
                    sentiment = analyze_sentiment_keywords(full_text)
                    market_impact = _estimate_market_impact(severity, category)
                    affected_sectors = CATEGORY_SECTOR_IMPACT.get(category, [])

                    pub_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                    # severity 2.0 이하면 스킵 (노이즈 필터)
                    if severity < 2.5:
                        continue

                    await execute(
                        """
                        INSERT INTO geopolitical_events
                            (title, body, source, url, url_hash, published_at,
                             category, severity, sentiment_score,
                             market_impact_score, affected_sectors)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        ON CONFLICT (url_hash) DO NOTHING
                        """,
                        title, summary, "google_news", entry_url, uh, pub_at,
                        category, severity, sentiment["score"],
                        market_impact, affected_sectors,
                    )
                    total_count += 1

            except Exception as e:
                logger.error("Geopolitical crawl error for '%s': %s", query[:30], e)

    duration = round(time.time() - start_time, 2)
    logger.info("Geopolitical crawl: %d events in %.1fs", total_count, duration)
    return {"status": "ok", "articles": total_count, "duration_sec": duration}


async def calculate_geopolitical_regime() -> dict:
    """최근 48시간 국제 정세 이벤트로 리스크 레짐을 산출한다."""
    events = await fetch_all(
        """
        SELECT category, severity, market_impact_score, affected_sectors,
               is_escalation, title
        FROM geopolitical_events
        WHERE crawled_at > NOW() - INTERVAL '48 hours'
        ORDER BY severity DESC
        """,
    )

    if not events:
        result = {
            "war_risk": 0.0, "financial_crisis_risk": 0.0,
            "sanctions_risk": 0.0, "pandemic_risk": 0.0,
            "political_risk": 0.0, "trade_war_risk": 0.0,
            "terrorism_risk": 0.0, "natural_disaster_risk": 0.0,
            "composite_risk": 0.0,
            "risk_regime": "STABLE",
            "risk_trend": "STABLE",
            "market_sentiment_impact": 0.0,
            "safe_haven_signal": False,
            "top_events": [],
        }
        await _insert_regime(result)
        return result

    # 카테고리별 리스크 점수 계산
    category_risks: dict[str, list[float]] = {k: [] for k in RISK_CATEGORY_WEIGHTS}
    for event in events:
        cat = event["category"]
        if cat in category_risks:
            # severity (0~10) → 0~1 범위로 정규화
            risk_val = float(event["severity"]) / 10.0
            category_risks[cat].append(risk_val)

    risk_scores = {}
    for cat, values in category_risks.items():
        if values:
            # 상위 3개의 가중 평균 (최악의 상황 반영)
            top_vals = sorted(values, reverse=True)[:3]
            risk_scores[f"{cat}_risk"] = round(sum(top_vals) / len(top_vals), 4)
        else:
            risk_scores[f"{cat}_risk"] = 0.0

    # 종합 리스크 (가중 합산)
    composite = sum(
        risk_scores.get(f"{cat}_risk", 0.0) * weight
        for cat, weight in RISK_CATEGORY_WEIGHTS.items()
    )
    composite = round(min(1.0, composite), 4)

    # 리스크 레짐 결정
    if composite >= 0.7:
        risk_regime = "CRISIS"
    elif composite >= 0.5:
        risk_regime = "HIGH"
    elif composite >= 0.25:
        risk_regime = "ELEVATED"
    else:
        risk_regime = "STABLE"

    # 트렌드 계산 (이전 레짐과 비교)
    prev = await fetch_one(
        """
        SELECT composite_risk FROM geopolitical_regime
        ORDER BY created_at DESC LIMIT 1
        """
    )
    prev_risk = float(prev["composite_risk"]) if prev else 0.0
    if composite > prev_risk + 0.05:
        risk_trend = "DETERIORATING"
    elif composite < prev_risk - 0.05:
        risk_trend = "IMPROVING"
    else:
        risk_trend = "STABLE"

    # 시장 영향 추정 (-0.3 ~ +0.1)
    # CRISIS → -0.3, HIGH → -0.15, ELEVATED → -0.05, STABLE → 0
    impact_map = {"CRISIS": -0.30, "HIGH": -0.15, "ELEVATED": -0.05, "STABLE": 0.0}
    market_sentiment_impact = impact_map.get(risk_regime, 0.0)

    # 안전자산 신호
    safe_haven = risk_regime in ("CRISIS", "HIGH")

    # 주요 이벤트 (상위 5개)
    top_events = [
        {"title": e["title"], "category": e["category"], "severity": float(e["severity"])}
        for e in events[:5]
    ]

    result = {
        **risk_scores,
        "composite_risk": composite,
        "risk_regime": risk_regime,
        "risk_trend": risk_trend,
        "market_sentiment_impact": market_sentiment_impact,
        "safe_haven_signal": safe_haven,
        "top_events": top_events,
    }

    await _insert_regime(result)
    return result


async def _insert_regime(result: dict) -> None:
    """geopolitical_regime 테이블에 삽입한다."""
    try:
        await execute(
            """
            INSERT INTO geopolitical_regime
                (war_risk, financial_crisis_risk, sanctions_risk,
                 pandemic_risk, political_risk, trade_war_risk,
                 terrorism_risk, natural_disaster_risk,
                 composite_risk, risk_regime, risk_trend,
                 market_sentiment_impact, safe_haven_signal, top_events)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            result.get("war_risk", 0), result.get("financial_crisis_risk", 0),
            result.get("sanctions_risk", 0), result.get("pandemic_risk", 0),
            result.get("political_risk", 0), result.get("trade_war_risk", 0),
            result.get("terrorism_risk", 0), result.get("natural_disaster_risk", 0),
            result["composite_risk"], result["risk_regime"],
            result["risk_trend"], result["market_sentiment_impact"],
            result["safe_haven_signal"], json.dumps(result.get("top_events", [])),
        )
    except Exception as e:
        logger.error("Geopolitical regime insert failed: %s", e)
