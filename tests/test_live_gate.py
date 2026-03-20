"""
Tests for live gate evaluation service.
"""
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from api.services.live_gate import (
    evaluate_live_readiness,
    GATE_CRITERIA,
    _get_paper_trading_weeks,
    _calculate_sharpe_ratio,
    _calculate_max_drawdown,
    _calculate_win_rate,
    _calculate_profit_factor,
    _count_total_trades,
    _count_critical_alerts,
    _check_setting,
)


class TestLiveGate:
    """Test live gate evaluation functions."""

    @pytest.mark.asyncio
    async def test_evaluate_live_readiness_all_pass(self):
        """Test evaluation when all criteria pass."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            # Mock 12 weeks of data
            mock_fetch_one.side_effect = [
                # Paper trading weeks
                {
                    "first_date": date.today() - timedelta(days=84),
                    "last_date": date.today(),
                    "total_days": 84,
                },
                # Win rate
                {"total_trades": 100, "winning_trades": 55},
                # Profit factor
                {"gross_profit": 12000, "gross_loss": 8000},
                # Total trades
                {"count": 100},
                # Critical alerts
                {"count": 0},
                # Dynamic exit setting
                {"value": "2.5"},
                # ATR sizing setting
                {"value": "true"},
            ]

            # Mock daily returns for Sharpe (with variation)
            daily_returns = [{"daily_return_pct": 0.4 + (i % 5) * 0.1} for i in range(50)]
            # Mock total values for MDD
            total_values = [{"total_value": 100000 + (i * 100)} for i in range(50)]

            mock_fetch_all.side_effect = [
                daily_returns,  # For Sharpe ratio
                total_values,   # For max drawdown
            ]

            result = await evaluate_live_readiness()

            assert result["ready"] is True
            assert result["score"] == 100.0
            assert len(result["blocking"]) == 0
            assert "staged_plan" in result
            assert "stage1" in result["staged_plan"]
            assert result["criteria"]["paper_weeks"]["passed"] is True
            assert result["criteria"]["sharpe_ratio"]["passed"] is True

    @pytest.mark.asyncio
    async def test_evaluate_live_readiness_insufficient_weeks(self):
        """Test evaluation when paper trading duration is insufficient."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            # Mock only 4 weeks of data
            mock_fetch_one.side_effect = [
                # Paper trading weeks - only 4 weeks
                {
                    "first_date": date.today() - timedelta(days=28),
                    "last_date": date.today(),
                    "total_days": 28,
                },
                # Win rate
                {"total_trades": 100, "winning_trades": 55},
                # Profit factor
                {"gross_profit": 12000, "gross_loss": 8000},
                # Total trades
                {"count": 100},
                # Critical alerts
                {"count": 0},
                # Dynamic exit setting
                {"value": "2.5"},
                # ATR sizing setting
                {"value": "true"},
            ]

            # Mock daily returns for Sharpe (with variation)
            daily_returns = [{"daily_return_pct": 0.4 + (i % 5) * 0.1} for i in range(50)]
            # Mock total values for MDD
            total_values = [{"total_value": 100000 + (i * 100)} for i in range(50)]

            mock_fetch_all.side_effect = [
                daily_returns,
                total_values,
            ]

            result = await evaluate_live_readiness()

            assert result["ready"] is False
            assert result["criteria"]["paper_weeks"]["passed"] is False
            assert "Paper trading weeks: 4.0 < 12 required" in result["blocking"]

    @pytest.mark.asyncio
    async def test_evaluate_live_readiness_low_sharpe(self):
        """Test evaluation when Sharpe ratio is too low."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            mock_fetch_one.side_effect = [
                # Paper trading weeks
                {
                    "first_date": date.today() - timedelta(days=84),
                    "last_date": date.today(),
                    "total_days": 84,
                },
                # Win rate
                {"total_trades": 100, "winning_trades": 55},
                # Profit factor
                {"gross_profit": 12000, "gross_loss": 8000},
                # Total trades
                {"count": 100},
                # Critical alerts
                {"count": 0},
                # Dynamic exit setting
                {"value": "2.5"},
                # ATR sizing setting
                {"value": "true"},
            ]

            # Mock low daily returns for poor Sharpe
            daily_returns = [{"daily_return_pct": 0.01} for _ in range(50)]
            total_values = [{"total_value": 100000 + (i * 10)} for i in range(50)]

            mock_fetch_all.side_effect = [
                daily_returns,
                total_values,
            ]

            result = await evaluate_live_readiness()

            assert result["ready"] is False
            assert result["criteria"]["sharpe_ratio"]["passed"] is False
            assert any("Sharpe ratio" in b for b in result["blocking"])

    @pytest.mark.asyncio
    async def test_evaluate_live_readiness_critical_alerts(self):
        """Test evaluation when there are critical alerts."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            mock_fetch_one.side_effect = [
                # Paper trading weeks
                {
                    "first_date": date.today() - timedelta(days=84),
                    "last_date": date.today(),
                    "total_days": 84,
                },
                # Win rate
                {"total_trades": 100, "winning_trades": 55},
                # Profit factor
                {"gross_profit": 12000, "gross_loss": 8000},
                # Total trades
                {"count": 100},
                # Critical alerts - 3 alerts
                {"count": 3},
                # Dynamic exit setting
                {"value": "2.5"},
                # ATR sizing setting
                {"value": "true"},
            ]

            daily_returns = [{"daily_return_pct": 0.5} for _ in range(50)]
            total_values = [{"total_value": 100000 + (i * 100)} for i in range(50)]

            mock_fetch_all.side_effect = [
                daily_returns,
                total_values,
            ]

            result = await evaluate_live_readiness()

            assert result["ready"] is False
            assert result["criteria"]["critical_alerts_30d"]["passed"] is False
            assert "Critical alerts (30d): 3 > 0 allowed" in result["blocking"]

    @pytest.mark.asyncio
    async def test_evaluate_live_readiness_atr_sizing_disabled(self):
        """Test evaluation when ATR sizing is disabled."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            mock_fetch_one.side_effect = [
                # Paper trading weeks
                {
                    "first_date": date.today() - timedelta(days=84),
                    "last_date": date.today(),
                    "total_days": 84,
                },
                # Win rate
                {"total_trades": 100, "winning_trades": 55},
                # Profit factor
                {"gross_profit": 12000, "gross_loss": 8000},
                # Total trades
                {"count": 100},
                # Critical alerts
                {"count": 0},
                # Dynamic exit setting
                {"value": "2.5"},
                # ATR sizing setting - disabled
                {"value": "false"},
            ]

            daily_returns = [{"daily_return_pct": 0.5} for _ in range(50)]
            total_values = [{"total_value": 100000 + (i * 100)} for i in range(50)]

            mock_fetch_all.side_effect = [
                daily_returns,
                total_values,
            ]

            result = await evaluate_live_readiness()

            assert result["ready"] is False
            assert result["criteria"]["atr_sizing_enabled"]["passed"] is False
            assert any("ATR sizing not enabled" in b for b in result["blocking"])

    @pytest.mark.asyncio
    async def test_get_paper_trading_weeks(self):
        """Test paper trading weeks calculation."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {
                "first_date": date.today() - timedelta(days=84),
                "last_date": date.today(),
                "total_days": 84,
            }

            weeks = await _get_paper_trading_weeks()
            assert weeks == 12.0

    @pytest.mark.asyncio
    async def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        with patch("api.services.live_gate.fetch_all") as mock_fetch_all:
            # Mock varying positive returns (to ensure non-zero std dev)
            returns = [{"daily_return_pct": 0.3 + (i % 10) * 0.1} for i in range(100)]
            mock_fetch_all.return_value = returns

            sharpe = await _calculate_sharpe_ratio()
            assert sharpe is not None
            assert sharpe > 0

    @pytest.mark.asyncio
    async def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        with patch("api.services.live_gate.fetch_all") as mock_fetch_all:
            # Mock portfolio values with a drawdown
            values = [
                {"total_value": 100000},
                {"total_value": 110000},
                {"total_value": 105000},  # -4.5% from peak
                {"total_value": 95000},   # -13.6% from peak
                {"total_value": 100000},
            ]
            mock_fetch_all.return_value = values

            mdd = await _calculate_max_drawdown()
            assert mdd is not None
            assert mdd < 0
            assert mdd <= -13.0  # Should capture the drawdown

    @pytest.mark.asyncio
    async def test_calculate_win_rate(self):
        """Test win rate calculation."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {
                "total_trades": 100,
                "winning_trades": 60,
            }

            win_rate = await _calculate_win_rate()
            assert win_rate == 60.0

    @pytest.mark.asyncio
    async def test_calculate_profit_factor(self):
        """Test profit factor calculation."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {
                "gross_profit": 15000,
                "gross_loss": 10000,
            }

            pf = await _calculate_profit_factor()
            assert pf == 1.5

    @pytest.mark.asyncio
    async def test_count_total_trades(self):
        """Test total trades counting."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {"count": 75}

            count = await _count_total_trades()
            assert count == 75

    @pytest.mark.asyncio
    async def test_count_critical_alerts(self):
        """Test critical alerts counting."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {"count": 2}

            count = await _count_critical_alerts()
            assert count == 2

    @pytest.mark.asyncio
    async def test_check_setting(self):
        """Test setting value retrieval."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one:
            mock_fetch_one.return_value = {"value": "2.5"}

            value = await _check_setting("hard_stop_atr_mult")
            assert value == "2.5"

    @pytest.mark.asyncio
    async def test_staged_plan_structure(self):
        """Test that staged plan has the correct structure."""
        with patch("api.services.live_gate.fetch_one") as mock_fetch_one, \
             patch("api.services.live_gate.fetch_all") as mock_fetch_all:

            # Mock minimal data
            mock_fetch_one.side_effect = [
                {"first_date": date.today(), "last_date": date.today(), "total_days": 1},
                {"total_trades": 0, "winning_trades": 0},
                {"gross_profit": 0, "gross_loss": 1},
                {"count": 0},
                {"count": 0},
                None,  # Dynamic exit
                None,  # ATR sizing
            ]
            mock_fetch_all.side_effect = [[], []]

            result = await evaluate_live_readiness()

            assert "staged_plan" in result
            plan = result["staged_plan"]
            assert "stage1" in plan
            assert "stage2" in plan
            assert "stage3" in plan
            assert plan["stage1"]["capital_pct"] == 1
            assert plan["stage1"]["weeks"] == 4
            assert plan["stage2"]["capital_pct"] == 3
            assert plan["stage3"]["capital_pct"] == 5
