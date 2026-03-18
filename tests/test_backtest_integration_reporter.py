"""백테스트와 리포터의 통합 테스트."""
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from api.services.backtester import run_backtest, BacktestConfig, _BACKTEST_RESULTS
from api.services.backtest_reporter import generate_report, compare_reports


@pytest.fixture
async def sample_backtest_run():
    """실제 백테스트를 실행하여 결과를 생성."""
    # Mock database fetch to return sample data
    sample_data = [
        {
            "symbol": "AAPL",
            "trade_date": date(2023, 1, 3),
            "open": 130.0,
            "high": 132.0,
            "low": 129.0,
            "close": 131.0,
            "rsi_14": 55.0,
            "sma_20": 128.0,
            "sma_60": 125.0,
            "macd": 0.5,
            "macd_signal": 0.3,
            "macd_histogram": 0.2,
            "bollinger_pct_b": 0.6,
            "volume_ratio": 1.2,
            "atr_14": 2.5,
        },
        {
            "symbol": "AAPL",
            "trade_date": date(2023, 1, 4),
            "open": 131.0,
            "high": 133.0,
            "low": 130.0,
            "close": 132.5,
            "rsi_14": 60.0,
            "sma_20": 128.5,
            "sma_60": 125.5,
            "macd": 0.6,
            "macd_signal": 0.4,
            "macd_histogram": 0.2,
            "bollinger_pct_b": 0.65,
            "volume_ratio": 1.3,
            "atr_14": 2.6,
        },
        {
            "symbol": "AAPL",
            "trade_date": date(2023, 1, 5),
            "open": 132.5,
            "high": 135.0,
            "low": 132.0,
            "close": 134.0,
            "rsi_14": 65.0,
            "sma_20": 129.0,
            "sma_60": 126.0,
            "macd": 0.7,
            "macd_signal": 0.5,
            "macd_histogram": 0.2,
            "bollinger_pct_b": 0.7,
            "volume_ratio": 1.4,
            "atr_14": 2.7,
        },
    ]

    with patch("api.services.backtester.fetch_all", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = sample_data

        config = BacktestConfig(
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 5),
            initial_capital=100000.0,
            exit_strategy="fixed",
        )

        result = await run_backtest(config)
        backtest_id = result["backtest_id"]

        yield backtest_id

        # Cleanup
        if backtest_id in _BACKTEST_RESULTS:
            del _BACKTEST_RESULTS[backtest_id]


@pytest.mark.asyncio
async def test_integration_backtest_to_report(sample_backtest_run):
    """백테스트 실행 후 리포트 생성 통합 테스트."""
    backtest_id = sample_backtest_run

    # Mock yfinance for benchmark
    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 385.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        # Generate report
        report = await generate_report(backtest_id)

    # Verify report structure
    assert report["backtest_id"] == backtest_id
    assert "metrics" in report
    assert "benchmark" in report
    assert "diagnoses" in report

    # Verify all required metrics are present
    metrics = report["metrics"]

    # 수익률
    assert "total_return_pct" in metrics["profit"]
    assert "annualized_return_pct" in metrics["profit"]

    # 리스크
    assert "mdd_pct" in metrics["risk"]
    assert "mdd_duration_days" in metrics["risk"]
    assert "daily_volatility" in metrics["risk"]

    # 효율
    assert "sharpe" in metrics["efficiency"]
    assert "sortino" in metrics["efficiency"]
    assert "calmar" in metrics["efficiency"]

    # 거래
    assert "total_trades" in metrics["trading"]
    assert "win_rate" in metrics["trading"]
    assert "profit_factor" in metrics["trading"]
    assert "avg_win" in metrics["trading"]
    assert "avg_loss" in metrics["trading"]
    assert "avg_holding_days" in metrics["trading"]
    assert "max_consecutive_losses" in metrics["trading"]

    # 청산 분포
    assert "exit_distribution" in metrics

    # 벤치마크
    assert "spy_return_pct" in report["benchmark"]
    assert "alpha" in report["benchmark"]

    # 진단은 리스트여야 함
    assert isinstance(report["diagnoses"], list)


@pytest.mark.asyncio
async def test_integration_compare_multiple_backtests():
    """여러 백테스트 비교 통합 테스트."""
    sample_data_1 = [
        {
            "symbol": "AAPL",
            "trade_date": date(2023, 1, 3),
            "open": 130.0,
            "high": 132.0,
            "low": 129.0,
            "close": 131.0,
            "rsi_14": 55.0,
            "sma_20": 128.0,
            "sma_60": 125.0,
            "macd": 0.5,
            "macd_signal": 0.3,
            "macd_histogram": 0.2,
            "bollinger_pct_b": 0.6,
            "volume_ratio": 1.2,
            "atr_14": 2.5,
        },
    ]

    sample_data_2 = [
        {
            "symbol": "MSFT",
            "trade_date": date(2023, 1, 3),
            "open": 240.0,
            "high": 242.0,
            "low": 239.0,
            "close": 241.0,
            "rsi_14": 60.0,
            "sma_20": 238.0,
            "sma_60": 235.0,
            "macd": 0.4,
            "macd_signal": 0.2,
            "macd_histogram": 0.2,
            "bollinger_pct_b": 0.65,
            "volume_ratio": 1.1,
            "atr_14": 3.0,
        },
    ]

    with patch("api.services.backtester.fetch_all", new_callable=AsyncMock) as mock_fetch:
        # First backtest - fixed strategy
        mock_fetch.return_value = sample_data_1
        config1 = BacktestConfig(
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 3),
            exit_strategy="fixed",
        )
        result1 = await run_backtest(config1)
        bt1_id = result1["backtest_id"]

        # Second backtest - dynamic strategy
        mock_fetch.return_value = sample_data_2
        config2 = BacktestConfig(
            start_date=date(2023, 1, 3),
            end_date=date(2023, 1, 3),
            exit_strategy="dynamic",
        )
        result2 = await run_backtest(config2)
        bt2_id = result2["backtest_id"]

    try:
        with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
            mock_hist = AsyncMock()
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 385.0}]
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            # Compare backtests
            comparison = await compare_reports([bt1_id, bt2_id])

        # Verify comparison structure
        assert "comparison" in comparison
        reports = comparison["comparison"]
        assert len(reports) == 2

        # Verify each report has all key metrics
        for report in reports:
            assert "backtest_id" in report
            assert "total_return_pct" in report
            assert "annualized_return_pct" in report
            assert "sharpe" in report
            assert "sortino" in report
            assert "calmar" in report
            assert "mdd_pct" in report
            assert "win_rate" in report
            assert "total_trades" in report
            assert "profit_factor" in report
            assert "avg_holding_days" in report
            assert "spy_alpha" in report
            assert "exit_distribution" in report

    finally:
        # Cleanup
        if bt1_id in _BACKTEST_RESULTS:
            del _BACKTEST_RESULTS[bt1_id]
        if bt2_id in _BACKTEST_RESULTS:
            del _BACKTEST_RESULTS[bt2_id]
