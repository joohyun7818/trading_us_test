"""ATR 기반 변동성 비례 포지션 사이징 모듈."""
import logging
from typing import Any, Optional

from api.core.database import fetch_one

logger = logging.getLogger(__name__)


def _normalize_ratio(value: float, default: float) -> float:
    """설정값을 비율(0~1)로 정규화한다."""
    if value <= 0:
        return default
    return value / 100.0 if value >= 1 else value


async def calculate_position_size(
    symbol: str,
    signal_score: float,
    account_equity: float,
    current_positions: list[dict],
    max_positions: int,
) -> dict[str, Any]:
    """
    ATR 기반 변동성 비례 포지션 사이징을 계산한다.

    Args:
        symbol: 종목 심볼
        signal_score: 시그널 점수 (0-100)
        account_equity: 계좌 자산 총액
        current_positions: 현재 보유 포지션 목록
        max_positions: 최대 포지션 수

    Returns:
        dict: {
            "symbol": str,
            "order_amount": float,  # 주문 금액 (USD)
            "quantity": int,        # 주문 수량
            "risk_per_trade": float,  # 거래당 리스크 (USD)
            "atr_14": float,        # 14일 ATR
            "sizing_reason": str,   # 사이징 사유
        }
    """
    # 1. 설정값 조회
    risk_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'risk_per_trade_pct'")
    risk_pct = _normalize_ratio(float(risk_pct_row["value"]), 0.01) if risk_pct_row else 0.01

    hard_stop_mult_row = await fetch_one("SELECT value FROM settings WHERE key = 'hard_stop_atr_mult'")
    hard_stop_atr_mult = float(hard_stop_mult_row["value"]) if hard_stop_mult_row else 2.5

    max_single_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'max_single_order_pct'")
    max_single_pct = _normalize_ratio(float(max_single_pct_row["value"]), 0.05) if max_single_pct_row else 0.05

    sector_cap_pct_row = await fetch_one("SELECT value FROM settings WHERE key = 'sector_cap_pct'")
    sector_cap_pct = _normalize_ratio(float(sector_cap_pct_row["value"]), 0.30) if sector_cap_pct_row else 0.30

    min_order_row = await fetch_one("SELECT value FROM settings WHERE key = 'min_order_amount'")
    min_order_amount = float(min_order_row["value"]) if min_order_row else 200.0

    # 2. 종목 정보 조회 (ATR, 현재가, 섹터)
    stock_info = await fetch_one(
        """
        SELECT atr_14, latest_price, sector_id
        FROM stocks
        WHERE symbol = $1
        """,
        symbol,
    )

    if not stock_info:
        logger.warning("Stock %s not found in stocks table", symbol)
        return {
            "symbol": symbol,
            "order_amount": 0.0,
            "quantity": 0,
            "risk_per_trade": 0.0,
            "atr_14": 0.0,
            "sizing_reason": "stock_not_found",
        }

    atr_14 = float(stock_info["atr_14"]) if stock_info.get("atr_14") else None
    latest_price = float(stock_info["latest_price"]) if stock_info.get("latest_price") else None
    sector_id = stock_info.get("sector_id")

    if not latest_price or latest_price <= 0:
        logger.warning("Invalid price for %s: %s", symbol, latest_price)
        return {
            "symbol": symbol,
            "order_amount": 0.0,
            "quantity": 0,
            "risk_per_trade": 0.0,
            "atr_14": atr_14 or 0.0,
            "sizing_reason": "invalid_price",
        }

    # ATR이 없으면 가격의 2%로 추정
    if not atr_14 or atr_14 <= 0:
        atr_14 = latest_price * 0.02

    # 3. 기본 포지션 사이징 계산
    risk_amount = account_equity * risk_pct
    dollar_risk = atr_14 * hard_stop_atr_mult
    base_shares = risk_amount / dollar_risk if dollar_risk > 0 else 0
    base_order_amount = base_shares * latest_price

    # 4. signal_score 스케일링
    if signal_score < 55:
        score_multiplier = 0.0  # 너무 낮으면 거래 안함
        sizing_reason = "signal_too_low"
    elif 55 <= signal_score < 65:
        score_multiplier = 0.7
        sizing_reason = "moderate_signal"
    elif 65 <= signal_score < 80:
        score_multiplier = 1.0
        sizing_reason = "good_signal"
    elif 80 <= signal_score < 90:
        score_multiplier = 1.2
        sizing_reason = "strong_signal"
    else:  # signal_score >= 90
        score_multiplier = 1.5
        sizing_reason = "exceptional_signal"

    scaled_order_amount = base_order_amount * score_multiplier

    # 5. 최대 단일 주문 제약 (계좌 자산의 5%)
    max_single_order = account_equity * max_single_pct
    if scaled_order_amount > max_single_order:
        scaled_order_amount = max_single_order
        sizing_reason += "_capped_max_single"

    # 6. 최소 주문 제약 ($200)
    if scaled_order_amount < min_order_amount:
        if scaled_order_amount > 0:
            sizing_reason += "_below_minimum"
        return {
            "symbol": symbol,
            "order_amount": 0.0,
            "quantity": 0,
            "risk_per_trade": risk_amount,
            "atr_14": atr_14,
            "sizing_reason": sizing_reason,
        }

    # 7. 섹터 제약 체크 (동일 섹터 합계: 계좌 자산의 30% 이하)
    if sector_id is not None:
        # 현재 포지션에서 같은 섹터의 exposure 계산
        sector_exposure = 0.0
        for pos in current_positions:
            pos_symbol = pos.get("stock_symbol") or pos.get("symbol")
            if pos_symbol:
                pos_stock = await fetch_one(
                    "SELECT sector_id FROM stocks WHERE symbol = $1", pos_symbol
                )
                if pos_stock and pos_stock.get("sector_id") == sector_id:
                    # 포지션의 현재 가치 계산
                    pos_qty = float(pos.get("qty", 0) or 0)
                    pos_price = float(pos.get("current_price", 0) or pos.get("avg_price", 0) or 0)
                    if pos_price > 0:
                        sector_exposure += pos_qty * pos_price

        sector_cap = account_equity * sector_cap_pct
        remaining_sector_capacity = sector_cap - sector_exposure

        if remaining_sector_capacity <= 0:
            logger.info(
                "Sector %s is at capacity: exposure=%.2f cap=%.2f",
                sector_id,
                sector_exposure,
                sector_cap,
            )
            return {
                "symbol": symbol,
                "order_amount": 0.0,
                "quantity": 0,
                "risk_per_trade": risk_amount,
                "atr_14": atr_14,
                "sizing_reason": "sector_cap_exceeded",
            }

        if scaled_order_amount > remaining_sector_capacity:
            scaled_order_amount = remaining_sector_capacity
            sizing_reason += "_capped_sector"

    # 8. 최종 수량 계산
    quantity = max(1, int(scaled_order_amount / latest_price))
    final_order_amount = quantity * latest_price

    return {
        "symbol": symbol,
        "order_amount": final_order_amount,
        "quantity": quantity,
        "risk_per_trade": risk_amount,
        "atr_14": atr_14,
        "sizing_reason": sizing_reason,
    }
