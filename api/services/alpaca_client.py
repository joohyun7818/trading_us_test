# alpaca-py SDK 래퍼 - 계정/포지션/주문/가격 조회, 안전장치
import logging
from datetime import datetime, timezone
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.data.live import StockDataStream
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from api.core.config import settings
from api.core.database import execute, fetch_one, fetch_all

logger = logging.getLogger(__name__)

_trading_client: Optional[TradingClient] = None
_data_client: Optional[StockHistoricalDataClient] = None


def _get_trading_client() -> TradingClient:
    """Alpaca TradingClient 싱글턴을 반환한다."""
    global _trading_client
    if _trading_client is None:
        is_paper = "paper" in settings.ALPACA_BASE_URL.lower()
        _trading_client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=is_paper,
        )
    return _trading_client


def _get_data_client() -> StockHistoricalDataClient:
    """Alpaca StockHistoricalDataClient 싱글턴을 반환한다."""
    global _data_client
    if _data_client is None:
        _data_client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
        )
    return _data_client


async def get_account() -> dict:
    """Alpaca 계정 정보를 조회한다."""
    try:
        client = _get_trading_client()
        account = client.get_account()
        return {
            "status": "ok",
            "buying_power": str(account.buying_power),
            "cash": str(account.cash),
            "portfolio_value": str(account.portfolio_value),
            "equity": str(account.equity),
            "long_market_value": str(account.long_market_value),
            "short_market_value": str(account.short_market_value),
            "account_blocked": account.account_blocked,
            "trading_blocked": account.trading_blocked,
        }
    except Exception as e:
        logger.error("Alpaca account fetch failed: %s", e)
        return {"status": "error", "error": str(e)}


async def get_positions() -> list[dict]:
    """현재 포지션 목록을 조회한다."""
    try:
        client = _get_trading_client()
        positions = client.get_all_positions()
        result = []
        for pos in positions:
            result.append({
                "symbol": pos.symbol,
                "qty": str(pos.qty),
                "avg_entry_price": str(pos.avg_entry_price),
                "current_price": str(pos.current_price),
                "market_value": str(pos.market_value),
                "unrealized_pl": str(pos.unrealized_pl),
                "unrealized_plpc": str(pos.unrealized_plpc),
                "side": pos.side.value if hasattr(pos.side, "value") else str(pos.side),
            })
        return result
    except Exception as e:
        logger.error("Alpaca positions fetch failed: %s", e)
        return []


async def _check_safety(symbol: str, qty: float, side: str) -> Optional[str]:
    """안전장치를 확인한다. 통과하면 None, 위반 시 에러 메시지를 반환한다."""
    max_amount_row = await fetch_one("SELECT value FROM settings WHERE key = 'max_order_amount'")
    max_amount = float(max_amount_row["value"]) if max_amount_row else 1000.0

    daily_limit_row = await fetch_one("SELECT value FROM settings WHERE key = 'daily_order_limit'")
    daily_limit = int(daily_limit_row["value"]) if daily_limit_row else 50

    max_exposure_row = await fetch_one("SELECT value FROM settings WHERE key = 'max_exposure_pct'")
    max_exposure = float(max_exposure_row["value"]) if max_exposure_row else 0.70

    total_cap_row = await fetch_one("SELECT value FROM settings WHERE key = 'total_capital'")
    total_capital = float(total_cap_row["value"]) if total_cap_row else 100000.0

    try:
        price = await get_latest_price(symbol)
        if price and price > 0:
            order_amount = qty * price
            if order_amount > max_amount:
                return f"Order amount ${order_amount:.2f} exceeds max ${max_amount:.2f}"
    except Exception:
        pass

    today_orders = await fetch_all(
        """
        SELECT COUNT(*) as cnt FROM trades
        WHERE created_at::date = CURRENT_DATE
        """
    )
    today_count = today_orders[0]["cnt"] if today_orders else 0
    if today_count >= daily_limit:
        return f"Daily order limit ({daily_limit}) reached"

    if side == "buy":
        try:
            account = await get_account()
            portfolio_value = float(account.get("portfolio_value", 0))
            long_value = float(account.get("long_market_value", 0))
            if portfolio_value > 0 and (long_value / portfolio_value) >= max_exposure:
                return f"Max exposure {max_exposure*100:.0f}% reached"
        except Exception:
            pass

    return None


async def submit_order(
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "market",
    limit_price: Optional[float] = None,
    signal_id: Optional[int] = None,
) -> dict:
    """주문을 제출한다."""
    safety_error = await _check_safety(symbol, qty, side)
    if safety_error:
        return {"status": "rejected", "error": safety_error}

    try:
        client = _get_trading_client()
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

        if order_type == "limit" and limit_price:
            req = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                type=OrderType.LIMIT,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
            )
        else:
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )

        order = client.submit_order(req)

        await execute(
            """
            INSERT INTO trades (stock_symbol, side, qty, price, order_type, order_id, status, signal_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            symbol, side, qty, limit_price, order_type,
            str(order.id), str(order.status.value if hasattr(order.status, "value") else order.status),
            signal_id,
        )

        logger.info("Order submitted: %s %s %.4f %s", side, symbol, qty, order.id)
        return {
            "status": "ok",
            "order_id": str(order.id),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_status": str(order.status.value if hasattr(order.status, "value") else order.status),
        }

    except Exception as e:
        logger.error("Order submission failed: %s", e)
        return {"status": "error", "error": str(e)}


async def cancel_order(order_id: str) -> dict:
    """주문을 취소한다."""
    try:
        client = _get_trading_client()
        client.cancel_order_by_id(order_id)
        await execute(
            "UPDATE trades SET status = 'cancelled', updated_at = NOW() WHERE order_id = $1",
            order_id,
        )
        logger.info("Order cancelled: %s", order_id)
        return {"status": "ok", "order_id": order_id}
    except Exception as e:
        logger.error("Order cancel failed: %s", e)
        return {"status": "error", "error": str(e)}


async def get_orders(status: str = "open") -> list[dict]:
    """주문 목록을 조회한다."""
    try:
        client = _get_trading_client()
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }
        req = GetOrdersRequest(status=status_map.get(status, QueryOrderStatus.OPEN))
        orders = client.get_orders(req)
        result = []
        for o in orders:
            result.append({
                "id": str(o.id),
                "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, "value") else str(o.side),
                "qty": str(o.qty),
                "type": o.type.value if hasattr(o.type, "value") else str(o.type),
                "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "created_at": str(o.created_at),
            })
        return result
    except Exception as e:
        logger.error("Get orders failed: %s", e)
        return []


async def get_latest_price(symbol: str) -> Optional[float]:
    """최신 가격을 조회한다."""
    try:
        client = _get_data_client()
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = client.get_stock_latest_quote(req)
        if symbol in quotes:
            return float(quotes[symbol].ask_price)
    except Exception as e:
        logger.error("Latest price failed for %s: %s", symbol, e)
    return None
