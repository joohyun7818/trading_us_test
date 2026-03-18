"""백테스트 리포터 API 엔드포인트 테스트."""
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from api.routers import backtest
from api.services.backtester import _BACKTEST_RESULTS


@pytest.fixture
def sample_backtest_stored():
    """백테스트 결과를 미리 저장."""
    backtest_id = "api-test-bt-1"
    backtest_data = {
        "backtest_id": backtest_id,
        "config": {
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000.0,
        },
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 4), 101000.0),
                (date(2023, 1, 5), 102000.0),
                (date(2023, 1, 6), 101500.0),
                (date(2023, 1, 9), 103000.0),
                (date(2023, 1, 10), 104000.0),
                (date(2023, 1, 11), 103500.0),
                (date(2023, 1, 12), 105000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 5),
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": 500.0,
                    "return_pct": 5.0,
                    "exit_reason": "take_profit",
                },
                {
                    "entry_date": date(2023, 1, 4),
                    "exit_date": date(2023, 1, 6),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -300.0,
                    "return_pct": -3.0,
                    "exit_reason": "stop_loss",
                },
                {
                    "entry_date": date(2023, 1, 9),
                    "exit_date": date(2023, 1, 12),
                    "symbol": "GOOGL",
                    "side": "LONG",
                    "pnl": 800.0,
                    "return_pct": 8.0,
                    "exit_reason": "trailing_stop",
                },
            ],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS[backtest_id] = backtest_data
    yield backtest_id
    # Cleanup
    if backtest_id in _BACKTEST_RESULTS:
        del _BACKTEST_RESULTS[backtest_id]


@pytest.mark.asyncio
async def test_get_backtest_report_endpoint(sample_backtest_stored):
    """GET /api/backtest/results/{backtest_id}/report 엔드포인트 테스트."""
    backtest_id = sample_backtest_stored

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        data = await backtest.get_backtest_report(backtest_id)

    assert data["backtest_id"] == backtest_id
    assert "metrics" in data
    assert "benchmark" in data
    assert "diagnoses" in data

    # 주요 지표가 모두 포함되어 있는지 확인
    metrics = data["metrics"]
    assert "profit" in metrics
    assert "risk" in metrics
    assert "efficiency" in metrics
    assert "trading" in metrics
    assert "exit_distribution" in metrics

    # 수익률 지표
    assert "total_return_pct" in metrics["profit"]
    assert "annualized_return_pct" in metrics["profit"]

    # 리스크 지표
    assert "mdd_pct" in metrics["risk"]
    assert "mdd_duration_days" in metrics["risk"]
    assert "daily_volatility" in metrics["risk"]

    # 효율 지표
    assert "sharpe" in metrics["efficiency"]
    assert "sortino" in metrics["efficiency"]
    assert "calmar" in metrics["efficiency"]

    # 거래 지표
    assert metrics["trading"]["total_trades"] == 3
    assert "win_rate" in metrics["trading"]
    assert "profit_factor" in metrics["trading"]
    assert "avg_win" in metrics["trading"]
    assert "avg_loss" in metrics["trading"]
    assert "avg_holding_days" in metrics["trading"]
    assert "max_consecutive_losses" in metrics["trading"]

    # 청산 분포
    exit_dist = metrics["exit_distribution"]
    assert "take_profit" in exit_dist
    assert "stop_loss" in exit_dist
    assert "trailing_stop" in exit_dist

    # 벤치마크
    assert "spy_return_pct" in data["benchmark"]
    assert "alpha" in data["benchmark"]

    # 진단
    assert isinstance(data["diagnoses"], list)


@pytest.mark.asyncio
async def test_get_backtest_report_not_found():
    """존재하지 않는 백테스트 ID로 리포트 요청 시 404 반환."""
    with pytest.raises(HTTPException) as exc:
        await backtest.get_backtest_report("non-existent-id")

    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail


@pytest.mark.asyncio
async def test_compare_backtests_endpoint():
    """POST /api/backtest/compare 엔드포인트 테스트."""
    # Setup - 두 개의 백테스트 생성
    bt1_id = "compare-bt-1"
    bt2_id = "compare-bt-2"

    bt1_data = {
        "backtest_id": bt1_id,
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 10), 110000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 10),
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": 1000.0,
                    "return_pct": 10.0,
                    "exit_reason": "trailing_stop",
                },
            ],
            "signals": [],
        },
    }

    bt2_data = {
        "backtest_id": bt2_id,
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 10), 105000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 10),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": 500.0,
                    "return_pct": 5.0,
                    "exit_reason": "take_profit",
                },
            ],
            "signals": [],
        },
    }

    _BACKTEST_RESULTS[bt1_id] = bt1_data
    _BACKTEST_RESULTS[bt2_id] = bt2_data

    try:
        with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
            mock_hist = AsyncMock()
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            request = backtest.CompareRequest(ids=[bt1_id, bt2_id])
            data = await backtest.compare_backtests(request)

        assert "comparison" in data
        reports = data["comparison"]
        assert len(reports) == 2

        # 각 리포트에 주요 지표가 포함되어 있는지 확인
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
        del _BACKTEST_RESULTS[bt1_id]
        del _BACKTEST_RESULTS[bt2_id]


@pytest.mark.asyncio
async def test_compare_backtests_empty_list():
    """빈 ID 리스트로 비교 요청 시 400 반환."""
    request = backtest.CompareRequest(ids=[])
    with pytest.raises(HTTPException) as exc:
        await backtest.compare_backtests(request)

    assert exc.value.status_code == 400
    assert "cannot be empty" in exc.value.detail
