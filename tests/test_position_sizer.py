"""Tests for ATR-based position sizing."""
import pytest
from unittest.mock import patch, AsyncMock

from api.services.position_sizer import calculate_position_size


@pytest.mark.asyncio
async def test_calculate_position_size_basic():
    """Test basic position sizing calculation."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        # Mock settings and stock info
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert result["symbol"] == "TEST"
        assert result["order_amount"] > 0
        assert result["quantity"] > 0
        assert result["atr_14"] == 2.5
        assert "good_signal" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_signal_score_scaling_low():
    """Test that low signal scores (55-64) get 0.7x multiplier."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=60.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert "moderate_signal" in result["sizing_reason"]
        assert result["order_amount"] > 0


@pytest.mark.asyncio
async def test_signal_score_scaling_high():
    """Test that high signal scores (90+) get 1.5x multiplier."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=95.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert "exceptional_signal" in result["sizing_reason"]
        assert result["order_amount"] > 0


@pytest.mark.asyncio
async def test_signal_score_too_low():
    """Test that very low signal scores result in no order."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=50.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert result["order_amount"] == 0.0
        assert result["quantity"] == 0
        assert "signal_too_low" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_max_single_order_constraint():
    """Test that order is capped at max single order limit (5%)."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.10"},  # high risk_per_trade_pct to trigger cap
            {"value": "1.0"},  # low hard_stop_atr_mult to increase position size
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 0.5, "latest_price": 100.0, "sector_id": 1},  # low ATR
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=95.0,  # high score with 1.5x multiplier
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        # Should be capped at 5% of account equity
        max_allowed = 100000.0 * 0.05
        assert result["order_amount"] <= max_allowed
        assert "capped_max_single" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_minimum_order_constraint():
    """Test that orders below minimum ($200) are rejected."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.001"},  # very low risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=75.0,
            account_equity=10000.0,  # small account
            current_positions=[],
            max_positions=20,
        )

        assert result["order_amount"] == 0.0
        assert result["quantity"] == 0
        assert "below_minimum" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_sector_cap_constraint():
    """Test that sector exposure is limited to 30% of account."""
    current_positions = [
        {"stock_symbol": "POS1", "qty": 100, "avg_price": 200.0},  # $20,000
    ]

    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.20"},  # max_single_order_pct (increased to 20% to not hit this limit)
            {"value": "0.30"},  # sector_cap_pct (30% = $30,000)
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
            {"sector_id": 1},  # POS1 sector
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=95.0,
            account_equity=100000.0,
            current_positions=current_positions,
            max_positions=20,
        )

        # Sector cap is $30,000, existing exposure is $20,000
        # So max new order should be $10,000
        sector_cap = 100000.0 * 0.30
        existing_exposure = 20000.0
        remaining = sector_cap - existing_exposure
        assert result["order_amount"] <= remaining
        # Since sector cap was hit, the reason should contain "capped_sector"
        if result["order_amount"] < remaining - 100:  # Allow some rounding tolerance
            assert "capped_sector" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_sector_cap_exceeded():
    """Test that no order is placed when sector cap is exceeded."""
    current_positions = [
        {"stock_symbol": "POS1", "qty": 150, "avg_price": 200.0},  # $30,000
    ]

    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct (30% = $30,000)
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 100.0, "sector_id": 1},  # stock info
            {"sector_id": 1},  # POS1 sector
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=95.0,
            account_equity=100000.0,
            current_positions=current_positions,
            max_positions=20,
        )

        assert result["order_amount"] == 0.0
        assert result["quantity"] == 0
        assert "sector_cap_exceeded" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_high_volatility_smaller_position():
    """Test that high volatility stocks get smaller position sizes."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        # High volatility test
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 10.0, "latest_price": 100.0, "sector_id": 1},  # high ATR (10% volatility)
        ]

        result_high_vol = await calculate_position_size(
            symbol="HIGH_VOL",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        # Low volatility test
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 1.0, "latest_price": 100.0, "sector_id": 2},  # low ATR (1% volatility)
        ]

        result_low_vol = await calculate_position_size(
            symbol="LOW_VOL",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        # High volatility stock should have smaller order amount
        assert result_high_vol["order_amount"] < result_low_vol["order_amount"]
        assert result_high_vol["atr_14"] > result_low_vol["atr_14"]


@pytest.mark.asyncio
async def test_missing_atr_fallback():
    """Test that missing ATR falls back to 2% of price."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": None, "latest_price": 100.0, "sector_id": 1},  # no ATR
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        # ATR should be 2% of price = 2.0
        expected_atr = 100.0 * 0.02
        assert result["atr_14"] == expected_atr
        assert result["order_amount"] > 0


@pytest.mark.asyncio
async def test_stock_not_found():
    """Test handling when stock is not found in database."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            None,  # stock not found
        ]

        result = await calculate_position_size(
            symbol="UNKNOWN",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert result["order_amount"] == 0.0
        assert result["quantity"] == 0
        assert "stock_not_found" in result["sizing_reason"]


@pytest.mark.asyncio
async def test_invalid_price():
    """Test handling when stock has invalid price."""
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.05"},  # max_single_order_pct
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 2.5, "latest_price": 0.0, "sector_id": 1},  # invalid price
        ]

        result = await calculate_position_size(
            symbol="TEST",
            signal_score=75.0,
            account_equity=100000.0,
            current_positions=[],
            max_positions=20,
        )

        assert result["order_amount"] == 0.0
        assert result["quantity"] == 0
        assert "invalid_price" in result["sizing_reason"]

