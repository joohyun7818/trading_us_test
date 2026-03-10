# 영어 금융 키워드 사전 기반 감성 분석, 선반영(priced-in) 감지, 섹터 전망 사전
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── 긍정 키워드 사전 (150+ 항목, 가중치) ──────────────────────
POSITIVE_KEYWORDS: dict[str, float] = {
    "beat": 1.5, "beats": 1.5, "beating": 1.5, "exceeded": 1.5, "exceeds": 1.5,
    "surpassed": 1.5, "outperformed": 1.5, "outperform": 1.3, "upgrade": 1.8,
    "upgraded": 1.8, "upgrades": 1.5, "upside": 1.3, "bullish": 1.5,
    "rally": 1.4, "rallied": 1.4, "rallies": 1.4, "soar": 1.6, "soared": 1.6,
    "soaring": 1.6, "surge": 1.5, "surged": 1.5, "surging": 1.5, "jump": 1.3,
    "jumped": 1.3, "jumping": 1.3, "gain": 1.2, "gained": 1.2, "gains": 1.2,
    "rise": 1.1, "risen": 1.1, "rising": 1.1, "rose": 1.1, "climbed": 1.2,
    "climbing": 1.2, "boom": 1.5, "booming": 1.5, "breakthrough": 1.6,
    "record high": 2.0, "all-time high": 2.0, "new high": 1.8, "strong": 1.2,
    "stronger": 1.3, "strongest": 1.5, "robust": 1.3, "solid": 1.2,
    "impressive": 1.3, "stellar": 1.5, "outstanding": 1.4, "excellent": 1.4,
    "exceptional": 1.5, "remarkable": 1.3, "phenomenal": 1.5, "accelerate": 1.3,
    "accelerated": 1.3, "accelerating": 1.3, "growth": 1.2, "growing": 1.2,
    "grew": 1.2, "expand": 1.2, "expanded": 1.2, "expanding": 1.2,
    "expansion": 1.2, "profit": 1.3, "profitable": 1.3, "profitability": 1.3,
    "revenue beat": 1.8, "earnings beat": 1.8, "eps beat": 1.8,
    "above estimate": 1.5, "above expectations": 1.5, "topped estimates": 1.5,
    "positive": 1.1, "optimistic": 1.3, "optimism": 1.3, "confidence": 1.2,
    "confident": 1.2, "momentum": 1.2, "tailwind": 1.3, "catalyst": 1.3,
    "innovation": 1.3, "innovative": 1.3, "disruptive": 1.3, "disruption": 1.2,
    "opportunity": 1.2, "opportunities": 1.2, "recovery": 1.3, "recovering": 1.3,
    "rebound": 1.3, "rebounded": 1.3, "turnaround": 1.4, "dividend": 1.2,
    "dividend increase": 1.5, "buyback": 1.3, "share repurchase": 1.3,
    "acquisition": 1.2, "merger": 1.2, "partnership": 1.2, "deal": 1.1,
    "contract": 1.2, "contract win": 1.5, "approval": 1.4, "approved": 1.4,
    "fda approval": 2.0, "patent": 1.3, "market share": 1.2, "market leader": 1.4,
    "outpace": 1.3, "overweight": 1.3, "buy rating": 1.5, "price target raise": 1.8,
    "target raised": 1.8, "initiated buy": 1.5, "strong buy": 1.8,
    "blowout": 1.6, "blockbuster": 1.6, "windfall": 1.5, "upbeat": 1.3,
    "favorable": 1.2, "positive outlook": 1.5, "guidance raise": 1.8,
    "raised guidance": 1.8, "better than expected": 1.6, "beat estimates": 1.6,
    "top line growth": 1.4, "bottom line growth": 1.4, "margin expansion": 1.5,
    "cost reduction": 1.3, "efficiency": 1.2, "synergy": 1.3, "synergies": 1.3,
    "accretive": 1.4, "value creation": 1.3, "shareholder value": 1.3,
    "double digit growth": 1.6, "triple digit": 1.8, "transformative": 1.4,
    "milestone": 1.3, "landmark": 1.3, "historic": 1.3, "unprecedented growth": 1.7,
    "inflection point": 1.4, "secular growth": 1.4, "pricing power": 1.3,
    "competitive advantage": 1.3, "moat": 1.3, "dominant": 1.2, "dominance": 1.2,
    "best in class": 1.4, "industry leading": 1.4, "high demand": 1.3,
    "backlog": 1.2, "order backlog": 1.3, "pipeline": 1.2, "healthy": 1.1,
    "resilient": 1.2, "resilience": 1.2, "stable growth": 1.3, "sustained": 1.2,
    "consecutive beat": 1.6, "consecutive growth": 1.5, "upward revision": 1.5,
    "positive revision": 1.4, "reiterate buy": 1.3, "overperform": 1.3,
    "top pick": 1.5, "conviction buy": 1.6, "best idea": 1.5, "breakout": 1.4,
}

# ── 부정 키워드 사전 (150+ 항목, 가중치) ──────────────────────
NEGATIVE_KEYWORDS: dict[str, float] = {
    "miss": 1.5, "missed": 1.5, "missing": 1.3, "below estimate": 1.5,
    "below expectations": 1.5, "disappointed": 1.5, "disappointing": 1.5,
    "disappointment": 1.5, "downgrade": 1.8, "downgraded": 1.8,
    "downgrades": 1.5, "bearish": 1.5, "sell-off": 1.6, "selloff": 1.6,
    "crash": 1.8, "crashed": 1.8, "crashing": 1.8, "plunge": 1.6,
    "plunged": 1.6, "plunging": 1.6, "tumble": 1.5, "tumbled": 1.5,
    "tumbling": 1.5, "decline": 1.3, "declined": 1.3, "declining": 1.3,
    "drop": 1.3, "dropped": 1.3, "dropping": 1.3, "fall": 1.2, "fallen": 1.2,
    "falling": 1.2, "fell": 1.2, "sink": 1.4, "sank": 1.4, "sinking": 1.4,
    "slump": 1.5, "slumped": 1.5, "slumping": 1.5, "slide": 1.3,
    "slid": 1.3, "sliding": 1.3, "loss": 1.3, "losses": 1.3, "lost": 1.2,
    "losing": 1.2, "weak": 1.2, "weaker": 1.3, "weakness": 1.3,
    "weakened": 1.3, "headwind": 1.3, "headwinds": 1.3, "risk": 1.1,
    "risks": 1.1, "risky": 1.2, "concern": 1.2, "concerns": 1.2,
    "worried": 1.2, "worry": 1.2, "worries": 1.2, "fear": 1.3, "fears": 1.3,
    "recession": 1.6, "recessionary": 1.6, "slowdown": 1.4, "slowing": 1.3,
    "contraction": 1.5, "shrink": 1.4, "shrinking": 1.4, "stagnation": 1.4,
    "stagnant": 1.4, "underperform": 1.3, "underperformed": 1.3,
    "underweight": 1.3, "sell rating": 1.5, "price target cut": 1.8,
    "target lowered": 1.8, "target cut": 1.8, "guidance cut": 1.8,
    "lowered guidance": 1.8, "reduced guidance": 1.8, "revenue miss": 1.8,
    "earnings miss": 1.8, "eps miss": 1.8, "shortfall": 1.5, "deficit": 1.3,
    "default": 1.6, "bankruptcy": 2.0, "bankrupt": 2.0, "insolvency": 1.8,
    "insolvent": 1.8, "restructuring": 1.3, "layoff": 1.4, "layoffs": 1.4,
    "job cuts": 1.4, "workforce reduction": 1.4, "downsizing": 1.3,
    "lawsuit": 1.3, "litigation": 1.3, "sued": 1.3, "investigation": 1.4,
    "probe": 1.3, "fraud": 1.8, "scandal": 1.7, "violation": 1.4,
    "penalty": 1.4, "fine": 1.3, "fined": 1.3, "regulatory": 1.1,
    "regulatory risk": 1.3, "recall": 1.4, "recalled": 1.4, "safety concern": 1.4,
    "warning": 1.3, "profit warning": 1.8, "margin pressure": 1.5,
    "margin compression": 1.5, "cost overrun": 1.4, "debt": 1.2,
    "overleveraged": 1.5, "write-down": 1.5, "writedown": 1.5,
    "impairment": 1.4, "goodwill impairment": 1.5, "dilution": 1.3,
    "dilutive": 1.3, "negative": 1.1, "pessimistic": 1.3, "pessimism": 1.3,
    "uncertainty": 1.2, "volatile": 1.2, "volatility": 1.2, "inflation": 1.2,
    "inflationary": 1.2, "tariff": 1.3, "tariffs": 1.3, "trade war": 1.5,
    "sanctions": 1.4, "embargo": 1.5, "supply chain": 1.2,
    "supply chain disruption": 1.5, "shortage": 1.3, "bottleneck": 1.3,
    "overvalued": 1.3, "bubble": 1.5, "correction": 1.3, "bear market": 1.5,
    "capitulation": 1.6, "panic": 1.5, "panic selling": 1.7,
    "market crash": 1.8, "black swan": 1.8, "contagion": 1.5,
    "negative outlook": 1.5, "adverse": 1.3, "deteriorating": 1.4,
    "deterioration": 1.4, "worst": 1.4, "terrible": 1.4, "dismal": 1.5,
    "abysmal": 1.5, "grim": 1.4, "bleak": 1.4, "critical": 1.2,
    "crisis": 1.5, "meltdown": 1.7, "collapse": 1.7, "collapsed": 1.7,
    "evaporate": 1.5, "evaporated": 1.5, "wipeout": 1.6, "erased": 1.4,
    "consecutive miss": 1.6, "downward revision": 1.5, "negative revision": 1.4,
    "reduce buy": 1.2, "sector rotation": 1.1, "outflow": 1.3, "outflows": 1.3,
    "redemption": 1.3, "margin call": 1.6, "death cross": 1.5,
}

# ── 선반영(priced-in) 정규식 패턴 10개 ──────────────────────
PRICED_IN_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bpriced[\s-]?in\b", re.IGNORECASE),
    re.compile(r"\balready[\s]+(?:reflected|factored|discounted|incorporated)\b", re.IGNORECASE),
    re.compile(r"\bfully[\s]+(?:valued|priced|reflected|discounted)\b", re.IGNORECASE),
    re.compile(r"\bbaked[\s]+in(?:to)?\b", re.IGNORECASE),
    re.compile(r"\bmarket[\s]+(?:has|already)[\s]+(?:priced|factored|adjusted)\b", re.IGNORECASE),
    re.compile(r"\b(?:no|little)[\s]+(?:surprise|upside|catalyst)\b", re.IGNORECASE),
    re.compile(r"\bexpected[\s]+(?:by|and)[\s]+(?:the[\s]+)?market\b", re.IGNORECASE),
    re.compile(r"\bconsensus[\s]+(?:already|largely)[\s]+(?:reflects|expects)\b", re.IGNORECASE),
    re.compile(r"\bwell[\s-]?known\b", re.IGNORECASE),
    re.compile(r"\bold[\s]+news\b", re.IGNORECASE),
]

# ── 섹터 전망 사전 ──────────────────────────────────────────
SECTOR_OUTLOOK: dict[str, dict[str, float]] = {
    "Technology": {"growth_bias": 0.1, "volatility_factor": 1.2},
    "Health Care": {"growth_bias": 0.05, "volatility_factor": 1.1},
    "Financials": {"growth_bias": 0.0, "volatility_factor": 1.0},
    "Consumer Discretionary": {"growth_bias": 0.05, "volatility_factor": 1.15},
    "Consumer Staples": {"growth_bias": -0.05, "volatility_factor": 0.8},
    "Communication Services": {"growth_bias": 0.05, "volatility_factor": 1.1},
    "Industrials": {"growth_bias": 0.0, "volatility_factor": 1.0},
    "Energy": {"growth_bias": 0.0, "volatility_factor": 1.3},
    "Utilities": {"growth_bias": -0.1, "volatility_factor": 0.7},
    "Real Estate": {"growth_bias": -0.05, "volatility_factor": 0.9},
    "Materials": {"growth_bias": 0.0, "volatility_factor": 1.1},
}


def _check_priced_in(text: str) -> bool:
    """선반영 여부를 정규식 패턴으로 확인한다."""
    for pattern in PRICED_IN_PATTERNS:
        if pattern.search(text):
            return True
    return False


def analyze_sentiment_keywords(text: str) -> dict:
    """키워드 사전 기반으로 1차 감성 분석을 수행한다."""
    if not text:
        return {"score": 0.0, "label": "neutral", "is_priced_in": False}

    text_lower = text.lower()
    pos_score = 0.0
    neg_score = 0.0
    pos_count = 0
    neg_count = 0

    for keyword, weight in POSITIVE_KEYWORDS.items():
        occurrences = text_lower.count(keyword.lower())
        if occurrences > 0:
            pos_score += weight * occurrences
            pos_count += occurrences

    for keyword, weight in NEGATIVE_KEYWORDS.items():
        occurrences = text_lower.count(keyword.lower())
        if occurrences > 0:
            neg_score += weight * occurrences
            neg_count += occurrences

    total = pos_score + neg_score
    if total == 0:
        normalized_score = 0.0
    else:
        normalized_score = round((pos_score - neg_score) / total, 4)

    if normalized_score > 0.15:
        label = "positive"
    elif normalized_score < -0.15:
        label = "negative"
    else:
        label = "neutral"

    is_priced_in = _check_priced_in(text)

    return {
        "score": normalized_score,
        "label": label,
        "is_priced_in": is_priced_in,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "positive_score": round(pos_score, 4),
        "negative_score": round(neg_score, 4),
    }
