from unittest.mock import AsyncMock, patch

import pytest

from api.services.trading_engine import check_exit


class TestCheckExitRealtime:
    @pytest.mark.asyncio
    async def test_check_exit_uses_realtime_unrealized_plpc_for_stop_loss(self):
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
    async def test_auto_trade_loop_persists_trigger_reason_for_stop_loss(self):
        from api.services import auto_trader

        async def mock_fetch_all(query: str, *args):
            if "FROM signals" in query:
                return []
            if "FROM portfolio" in query:
                return [{"stock_symbol": "AAPL"}]
            return []

        with patch("api.services.auto_trader.fetch_all", new=AsyncMock(side_effect=mock_fetch_all)):
            with patch("api.services.auto_trader.asyncio.to_thread", new=AsyncMock(return_value=[{"symbol": "AAPL", "qty": "5", "unrealized_plpc": "-0.10"}])):
                with patch("api.services.auto_trader.check_exit", new=AsyncMock(return_value={
                    "symbol": "AAPL",
                    "action": "SELL",
                    "reason": "Stop-loss triggered: P&L=-10.00%",
                    "qty": 5.0,
                    "trigger_reason": "stop_loss",
                })) as mock_check_exit:
                    with patch("api.services.auto_trader.submit_order", new=AsyncMock(return_value={"status": "ok", "order_id": "oid-1"})):
                        with patch("api.services.auto_trader.execute", new=AsyncMock()) as mock_execute:
                            result = await auto_trader.auto_trade_loop()

        assert result["status"] == "ok"
        assert result["exits"] == 1
        mock_check_exit.assert_awaited_once_with(
            "AAPL",
            current_positions=[{"symbol": "AAPL", "qty": "5", "unrealized_plpc": "-0.10"}],
        )
        assert any(
            "UPDATE trades SET trigger_reason" in call.args[0]
            for call in mock_execute.await_args_list
        )
