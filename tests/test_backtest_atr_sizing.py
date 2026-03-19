"""Integration tests for backtester with ATR-based position sizing."""
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from api.services.backtester import run_backtest, BacktestConfig


@pytest.mark.asyncio
async def test_backtest_with_atr_sizing_disabled():
    """Test that backtester works with use_atr_sizing=False (default behavior)."""
    with patch("api.services.backtester.fetch_all", new_callable=AsyncMock) as mock_fetch_all:
        # Mock empty data
        mock_fetch_all.return_value = []

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            use_atr_sizing=False,  # Use fixed order amount
            max_order_amount=1000.0,
        )

        result = await run_backtest(config)

        assert result is not None
        assert "backtest_id" in result
        assert "config" in result
        assert "result" in result
        assert result["config"]["use_atr_sizing"] is False


@pytest.mark.asyncio
async def test_backtest_with_atr_sizing_enabled():
    """Test that backtester works with use_atr_sizing=True."""
    with patch("api.services.backtester.fetch_all", new_callable=AsyncMock) as mock_fetch_all:
        # Mock empty data
        mock_fetch_all.return_value = []

        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            use_atr_sizing=True,  # Use ATR-based sizing
            risk_per_trade_pct=1.0,
            max_single_order_pct=5.0,
            sector_cap_pct=30.0,
        )

        result = await run_backtest(config)

        assert result is not None
        assert "backtest_id" in result
        assert "config" in result
        assert "result" in result
        assert result["config"]["use_atr_sizing"] is True
        assert result["config"]["risk_per_trade_pct"] == 1.0
        assert result["config"]["max_single_order_pct"] == 5.0
        assert result["config"]["sector_cap_pct"] == 30.0


@pytest.mark.asyncio
async def test_backtest_atr_sizing_with_mock_data():
    """Test backtester with ATR sizing using mock data."""
    with patch("api.services.backtester.fetch_all", new_callable=AsyncMock) as mock_fetch_all:
        # Mock stock data with different ATR values
        # Need data over multiple days for 52w high/low calculations
        mock_data = []
        for day_offset in range(5):
            trade_date = date(2024, 1, 2 + day_offset)
            mock_data.extend([
                {
                    "symbol": "HIGH_VOL",
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "rsi_14": 75.0,
                    "sma_20": 98.0,
                    "sma_60": 95.0,
                    "macd": 1.5,
                    "macd_signal": 1.0,
                    "macd_histogram": 0.5,
                    "bollinger_pct_b": 0.8,
                    "volume_ratio": 1.5,
                    "atr_14": 10.0,  # High volatility
                },
                {
                    "symbol": "LOW_VOL",
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "rsi_14": 75.0,
                    "sma_20": 98.0,
                    "sma_60": 95.0,
                    "macd": 1.5,
                    "macd_signal": 1.0,
                    "macd_histogram": 0.5,
                    "bollinger_pct_b": 0.8,
                    "volume_ratio": 1.5,
                    "atr_14": 1.0,  # Low volatility
                },
            ])
        mock_fetch_all.return_value = mock_data

        # Test with ATR sizing enabled
        config = BacktestConfig(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            use_atr_sizing=True,
            risk_per_trade_pct=1.0,
            max_single_order_pct=5.0,
            sector_cap_pct=30.0,
            buy_threshold=70.0,  # Should trigger BUY signals
            screening_upper=80.0,  # Adjust to allow signals through
            screening_lower=40.0,
        )

        result = await run_backtest(config)

        assert result is not None
        assert "backtest_id" in result
        # Signals may or may not be generated depending on scoring logic
        assert "signals" in result["result"]


@pytest.mark.asyncio
async def test_calculate_atr_position_size_helper():
    """Test the _calculate_atr_position_size helper function."""
    from api.services.backtester import _calculate_atr_position_size, BacktestConfig

    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        use_atr_sizing=True,
        risk_per_trade_pct=1.0,
        max_single_order_pct=5.0,
        sector_cap_pct=30.0,
        hard_stop_atr_mult=2.5,
    )

    # Test with high volatility stock
    order_amount_high_vol = _calculate_atr_position_size(
        final_score=75.0,
        atr_14=10.0,  # High ATR
        price=100.0,
        account_equity=100000.0,
        positions={},
        config=config,
    )

    # Test with low volatility stock
    order_amount_low_vol = _calculate_atr_position_size(
        final_score=75.0,
        atr_14=1.0,  # Low ATR
        price=100.0,
        account_equity=100000.0,
        positions={},
        config=config,
    )

    # High volatility should result in smaller position size
    assert order_amount_high_vol < order_amount_low_vol
    assert order_amount_high_vol > 0
    assert order_amount_low_vol > 0


@pytest.mark.asyncio
async def test_signal_score_scaling_in_backtest():
    """Test that signal score scaling works correctly in backtest."""
    from api.services.backtester import _calculate_atr_position_size, BacktestConfig

    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        use_atr_sizing=True,
        risk_per_trade_pct=1.0,
        max_single_order_pct=50.0,  # High enough to not cap
        sector_cap_pct=80.0,  # High enough to not cap
        hard_stop_atr_mult=2.5,
    )

    # Test different signal scores
    order_moderate = _calculate_atr_position_size(
        final_score=60.0,  # Moderate signal (0.7x)
        atr_14=2.5,
        price=100.0,
        account_equity=100000.0,
        positions={},
        config=config,
    )

    order_good = _calculate_atr_position_size(
        final_score=75.0,  # Good signal (1.0x)
        atr_14=2.5,
        price=100.0,
        account_equity=100000.0,
        positions={},
        config=config,
    )

    order_exceptional = _calculate_atr_position_size(
        final_score=95.0,  # Exceptional signal (1.5x)
        atr_14=2.5,
        price=100.0,
        account_equity=100000.0,
        positions={},
        config=config,
    )

    # Higher signal scores should result in larger position sizes
    assert order_moderate < order_good < order_exceptional
    assert order_moderate > 0  # Should not be zero


@pytest.mark.asyncio
async def test_minimum_order_constraint_in_backtest():
    """Test that minimum order constraint ($200) is enforced in backtest."""
    from api.services.backtester import _calculate_atr_position_size, BacktestConfig

    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        use_atr_sizing=True,
        risk_per_trade_pct=0.001,  # Very low risk to trigger minimum
        max_single_order_pct=5.0,
        sector_cap_pct=30.0,
        hard_stop_atr_mult=2.5,
    )

    order_amount = _calculate_atr_position_size(
        final_score=75.0,
        atr_14=2.5,
        price=100.0,
        account_equity=10000.0,  # Small account
        positions={},
        config=config,
    )

    # Should return 0 if below minimum
    assert order_amount == 0.0


def test_apply_sector_cap_in_backtest_caps_requested_notional():
    """Sector info가 있는 경우 sector cap을 적용한다."""
    from api.services.backtester import _apply_sector_cap_in_backtest

    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        sector_cap_pct=30.0,
    )
    positions = {
        "AAA": {"qty": 100.0, "sector_id": 1},
    }
    close_prices = {"AAA": 250.0}  # existing exposure = 25,000

    capped = _apply_sector_cap_in_backtest(
        symbol="BBB",
        symbol_sector_id=1,
        positions=positions,
        close_prices=close_prices,
        account_equity=100000.0,  # sector cap = 30,000
        requested_notional=10000.0,
        config=config,
    )

    assert capped == 5000.0


def test_apply_sector_cap_in_backtest_ignores_missing_sector_info():
    """sector 정보가 없으면 cap을 건너뛰고 원요청 금액을 유지한다."""
    from api.services.backtester import _apply_sector_cap_in_backtest

    config = BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        sector_cap_pct=30.0,
    )

    requested = 7777.0
    result = _apply_sector_cap_in_backtest(
        symbol="NOSECTOR",
        symbol_sector_id=None,
        positions={},
        close_prices={},
        account_equity=100000.0,
        requested_notional=requested,
        config=config,
    )

    assert result == requested
