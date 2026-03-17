# Alpaca 연결, 상태, 계정, 보유, 주문, 취소 라우터
import logging
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel

from api.core.config import settings
from api.core.auth import verify_api_key
from api.services.alpaca_client import (
    cancel_order,
    get_account,
    get_orders,
    get_positions,
    submit_order,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alpaca", tags=["alpaca"])


class OrderRequest(BaseModel):
    """주문 요청 모델."""
    symbol: str
    qty: float
    side: str
    order_type: str = "market"
    limit_price: Optional[float] = None


@router.get("/connect")
async def check_connection() -> dict:
    """Alpaca API 연결 상태를 확인한다."""
    if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
        return {"status": "not_configured", "message": "API keys not set"}
    account = await get_account()
    if account.get("status") == "ok":
        return {"status": "connected", "base_url": settings.ALPACA_BASE_URL}
    return {"status": "error", "error": account.get("error", "Unknown")}


@router.get("/status")
async def get_status() -> dict:
    """Alpaca 연결 상태 및 기본 계정 정보를 반환한다."""
    connected = bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY)
    is_paper = "paper" in settings.ALPACA_BASE_URL.lower()
    account = await get_account() if connected else {}
    return {
        "connected": connected,
        "is_paper": is_paper,
        "base_url": settings.ALPACA_BASE_URL,
        "account_blocked": account.get("account_blocked", None),
        "trading_blocked": account.get("trading_blocked", None),
    }


@router.get("/account")
async def get_account_info() -> dict:
    """상세 계정 정보를 반환한다."""
    return await get_account()


@router.get("/holdings")
async def get_holdings() -> list[dict]:
    """현재 보유 종목을 반환한다."""
    return await get_positions()


@router.post("/order/buy", dependencies=[Depends(verify_api_key)])
async def place_buy_order(order: OrderRequest) -> dict:
    """매수 주문을 제출한다."""
    return await submit_order(
        symbol=order.symbol,
        qty=order.qty,
        side="buy",
        order_type=order.order_type,
        limit_price=order.limit_price,
    )


@router.post("/order/sell", dependencies=[Depends(verify_api_key)])
async def place_sell_order(order: OrderRequest) -> dict:
    """매도 주문을 제출한다."""
    return await submit_order(
        symbol=order.symbol,
        qty=order.qty,
        side="sell",
        order_type=order.order_type,
        limit_price=order.limit_price,
    )


@router.get("/orders")
async def list_orders(
    status: str = Query(default="open", pattern="^(open|closed|all)$"),
) -> list[dict]:
    """주문 목록을 조회한다."""
    return await get_orders(status=status)


@router.post("/cancel/{order_id}", dependencies=[Depends(verify_api_key)])
async def cancel_order_endpoint(order_id: str) -> dict:
    """주문을 취소한다."""
    return await cancel_order(order_id)
