from unittest.mock import AsyncMock, patch

import pytest
from api.services.exit_manager import evaluate_exit
from datetime import datetime, timezone

from api.services.trading_engine import check_exit


class TestCheckExitRealtime:
    @pytest.mark.asyncio
    async def test_check_exit_uses_realtime_unrealized_pl_percentage_for_stop_loss(self):
        async def mock_fetch_one(query: str, *args):
            if "FROM portfolio" in query:
                return {"stock_symbol": "AAPL", "qty": 1, "unrealized_pnl_pct": 2.0}
            if "key = 'stop_loss_pct'" in query:
                return {"value": "-8"}
            if "key = 'take_profit_pct'" in query:
                return {"value": "15"}
            return None

        with patch("api.services.trading_engine.fetch_one", new=AsyncMock(side_effect=mock_fetch_one)):
            with patch("api.services.trading_engine.calculate_numeric_score", new=AsyncMock(return_value={"score": 55.0})):
                result = await check_exit(
                    "AAPL",
                    current_positions=[{"symbol": "AAPL", "qty": "10", "unrealized_plpc": "-0.09"}],
                )

        assert result is not None
        assert result["action"] == "SELL"
        assert result["trigger_reason"] == "stop_loss"
        assert result["qty"] == 10.0

    @pytest.mark.asyncio
    async def test_check_exit_falls_back_to_portfolio_when_realtime_not_provided(self):
        async def mock_fetch_one(query: str, *args):
            if "FROM portfolio" in query:
                return {"stock_symbol": "AAPL", "qty": 3, "unrealized_pnl_pct": 12.0}
            if "key = 'stop_loss_pct'" in query:
                return {"value": "-8"}
            if "key = 'take_profit_pct'" in query:
                return {"value": "10"}
            return None

        with patch("api.services.trading_engine.fetch_one", new=AsyncMock(side_effect=mock_fetch_one)):
            with patch("api.services.trading_engine.calculate_numeric_score", new=AsyncMock(return_value={"score": 45.0})):
                result = await check_exit("AAPL")

        assert result is not None
        assert result["action"] == "SELL"
        assert result["trigger_reason"] == "take_profit"
        assert result["qty"] == 3.0


class TestAutoTradeLoopExit:
    @pytest.mark.asyncio
    async def test_auto_trade_loop_uses_dynamic_exit_manager_and_persists_exit_reason(self):
        from api.services import auto_trader

        async def mock_fetch_all(query: str, *args):
            if "FROM signals" in query:
                return []
            if "FROM portfolio" in query:
                return [{"stock_symbol": "AAPL", "qty": 5, "avg_price": 100.0, "highest_price": 112.0, "entry_atr": 3.0}]
            return []

        async def mock_fetch_one(query: str, *args):
            if "FROM trades" in query and "created_at" in query:
                return {"created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
            return None

        with patch("api.services.auto_trader.fetch_all", new=AsyncMock(side_effect=mock_fetch_all)):
            with patch("api.services.auto_trader.fetch_one", new=AsyncMock(side_effect=mock_fetch_one)):
                with patch("api.services.auto_trader.get_positions", new=AsyncMock(return_value=[{"symbol": "AAPL", "qty": "5", "current_price": "90", "avg_entry_price": "100"}])):
                    with patch("api.services.auto_trader.evaluate_exit", new=AsyncMock(return_value={
                        "should_exit": True,
                        "exit_reason": "atr_hard_stop",
                        "exit_quantity": 5,
                        "details": "test",
                    })) as mock_evaluate_exit:
                        with patch("api.services.auto_trader.submit_order", new=AsyncMock(return_value={"status": "ok", "order_id": "oid-1"})):
                            with patch("api.services.auto_trader.execute", new=AsyncMock()) as mock_execute:
                                result = await auto_trader.auto_trade_loop()

        assert result["status"] == "ok"
        assert result["exits"] == 1
        mock_evaluate_exit.assert_awaited_once()
        assert any(
            "UPDATE trades SET exit_reason" in call.args[0]
            for call in mock_execute.await_args_list
        )


class TestExitManager:
    @pytest.mark.asyncio
    async def test_evaluate_exit_priority_hard_stop(self):
        async def mock_fetch_one(query: str, *args):
            return None

        with patch("api.services.exit_manager.fetch_one", new=AsyncMock(side_effect=mock_fetch_one)):
            result = await evaluate_exit(
                {
                    "symbol": "AAPL",
                    "entry_price": 100.0,
                    "current_price": 94.0,
                    "highest_price_since_entry": 110.0,
                    "days_held": 3,
                    "entry_atr": 2.0,
                    "quantity": 5,
                }
            )

        assert result["should_exit"] is True
        assert result["exit_reason"] == "atr_hard_stop"

    @pytest.mark.asyncio
    async def test_evaluate_exit_partial_take_profit(self):
        async def mock_fetch_one(query: str, *args):
            return None

        with patch("api.services.exit_manager.fetch_one", new=AsyncMock(side_effect=mock_fetch_one)):
            result = await evaluate_exit(
                {
                    "symbol": "AAPL",
                    "entry_price": 100.0,
                    "current_price": 108.0,
                    "highest_price_since_entry": 108.0,
                    "days_held": 2,
                    "entry_atr": 2.0,
                    "quantity": 5,
                }
            )

        assert result["should_exit"] is True
        assert result["exit_reason"] == "partial_take_profit"
        assert result["exit_quantity"] == 2
