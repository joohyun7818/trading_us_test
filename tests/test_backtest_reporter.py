"""백테스트 리포터 테스트."""
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from api.services.backtester import _BACKTEST_RESULTS
from api.services.backtest_reporter import (
    generate_report,
    compare_reports,
    _generate_diagnoses,
)


@pytest.fixture
def sample_backtest_data():
    """샘플 백테스트 데이터."""
    return {
        "backtest_id": "test-bt-1",
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


@pytest.fixture
def sample_backtest_with_fixed_exits():
    """고정 청산 백테스트 데이터."""
    return {
        "backtest_id": "test-bt-fixed",
        "config": {
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000.0,
        },
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 4), 108000.0),
                (date(2023, 1, 5), 107000.0),
                (date(2023, 1, 6), 115000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 4),
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": 1500.0,
                    "return_pct": 15.0,
                    "exit_reason": "take_profit",
                },
                {
                    "entry_date": date(2023, 1, 4),
                    "exit_date": date(2023, 1, 5),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -800.0,
                    "return_pct": -8.0,
                    "exit_reason": "stop_loss",
                },
            ],
            "signals": [],
        },
    }


@pytest.mark.asyncio
async def test_generate_report_basic(sample_backtest_data):
    """기본 리포트 생성 테스트."""
    # Setup
    backtest_id = sample_backtest_data["backtest_id"]
    _BACKTEST_RESULTS[backtest_id] = sample_backtest_data

    # Mock yfinance
    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [
            {"Close": 380.0},  # first
            {"Close": 390.0},  # last
        ]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        # Execute
        report = await generate_report(backtest_id)

    # Verify
    assert report["backtest_id"] == backtest_id
    assert "metrics" in report
    assert "benchmark" in report
    assert "diagnoses" in report

    metrics = report["metrics"]
    assert "profit" in metrics
    assert "risk" in metrics
    assert "efficiency" in metrics
    assert "trading" in metrics
    assert "exit_distribution" in metrics

    # 수익률 검증
    profit = metrics["profit"]
    assert profit["total_return_pct"] == 5.0  # (105000 - 100000) / 100000 * 100
    assert "annualized_return_pct" in profit

    # 리스크 검증
    risk = metrics["risk"]
    assert "mdd_pct" in risk
    assert "mdd_duration_days" in risk
    assert "daily_volatility" in risk

    # 효율 검증
    efficiency = metrics["efficiency"]
    assert "sharpe" in efficiency
    assert "sortino" in efficiency
    assert "calmar" in efficiency

    # 거래 검증
    trading = metrics["trading"]
    assert trading["total_trades"] == 3
    assert trading["win_rate"] == pytest.approx(66.67, rel=0.1)  # 2승 1패
    assert "profit_factor" in trading
    assert "avg_win" in trading
    assert "avg_loss" in trading
    assert "avg_holding_days" in trading
    assert "max_consecutive_losses" in trading

    # 청산 분포 검증
    exit_dist = metrics["exit_distribution"]
    assert exit_dist["take_profit"] == 1
    assert exit_dist["stop_loss"] == 1
    assert exit_dist["trailing_stop"] == 1

    # 벤치마크 검증
    benchmark = report["benchmark"]
    assert "spy_return_pct" in benchmark
    assert "alpha" in benchmark

    # Clean up
    del _BACKTEST_RESULTS[backtest_id]


@pytest.mark.asyncio
async def test_generate_report_not_found():
    """존재하지 않는 백테스트 ID 테스트."""
    with pytest.raises(ValueError, match="not found"):
        await generate_report("non-existent-id")


@pytest.mark.asyncio
async def test_generate_report_empty_trades():
    """거래가 없는 백테스트 테스트."""
    backtest_data = {
        "backtest_id": "empty-bt",
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 4), 100000.0),
            ],
            "trades": [],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS["empty-bt"] = backtest_data

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 380.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        report = await generate_report("empty-bt")

    assert report["metrics"]["trading"]["total_trades"] == 0
    assert report["metrics"]["trading"]["win_rate"] == 0.0

    del _BACKTEST_RESULTS["empty-bt"]


@pytest.mark.asyncio
async def test_diagnoses_fixed_sl_tp_dependency(sample_backtest_with_fixed_exits):
    """고정 SL/TP 종속 진단 테스트."""
    backtest_id = sample_backtest_with_fixed_exits["backtest_id"]
    _BACKTEST_RESULTS[backtest_id] = sample_backtest_with_fixed_exits

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        report = await generate_report(backtest_id)

    diagnoses = report["diagnoses"]
    # 동적 청산이 0%이므로 CRITICAL 진단이 있어야 함
    critical_diag = [d for d in diagnoses if d["severity"] == "CRITICAL"]
    assert len(critical_diag) > 0
    assert any("고정 SL/TP 종속" in d["message"] for d in critical_diag)

    del _BACKTEST_RESULTS[backtest_id]


def test_generate_diagnoses_all_rules():
    """모든 진단 규칙 테스트."""
    # 모든 규칙을 트리거하는 시나리오
    diagnoses = _generate_diagnoses(
        exit_reason_dist={"stop_loss": 10, "take_profit": 10},  # 동적 청산 0%
        total_trades=20,
        trading_days=252,  # 1년, 월 평균 1.67건
        sharpe=0.3,  # < 0.5
        alpha=-15.0,  # < -10
        avg_holding_days=30.0,  # > 25
    )

    # 5개의 진단이 생성되어야 함
    assert len(diagnoses) >= 5

    # severity별 개수 확인
    severities = [d["severity"] for d in diagnoses]
    assert severities.count("CRITICAL") >= 2  # 고정청산 + alpha
    assert severities.count("HIGH") >= 2  # 저빈도 + Sharpe
    assert severities.count("MEDIUM") >= 1  # 과도보유

    # severity 순 정렬 확인 (CRITICAL -> HIGH -> MEDIUM)
    for i in range(len(diagnoses) - 1):
        curr = diagnoses[i]["severity"]
        next_sev = diagnoses[i + 1]["severity"]
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
        assert severity_order[curr] <= severity_order[next_sev]


def test_generate_diagnoses_healthy_backtest():
    """건강한 백테스트는 진단이 없어야 함."""
    diagnoses = _generate_diagnoses(
        exit_reason_dist={"trailing_stop": 50, "stop_loss": 50},  # 동적 청산 50%
        total_trades=100,
        trading_days=252,  # 월 평균 ~8.3건
        sharpe=1.5,  # > 0.5
        alpha=10.0,  # > -10
        avg_holding_days=10.0,  # < 25
    )

    # 모든 조건이 양호하므로 진단이 없어야 함
    assert len(diagnoses) == 0


@pytest.mark.asyncio
async def test_compare_reports(sample_backtest_data, sample_backtest_with_fixed_exits):
    """여러 백테스트 비교 테스트."""
    # Setup
    bt1 = sample_backtest_data
    bt2 = sample_backtest_with_fixed_exits
    _BACKTEST_RESULTS[bt1["backtest_id"]] = bt1
    _BACKTEST_RESULTS[bt2["backtest_id"]] = bt2

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        # Execute
        comparison = await compare_reports([bt1["backtest_id"], bt2["backtest_id"]])

    # Verify
    assert "comparison" in comparison
    reports = comparison["comparison"]
    assert len(reports) == 2

    # 각 리포트에 주요 지표가 포함되어 있는지 확인
    for report in reports:
        assert "backtest_id" in report
        assert "total_return_pct" in report
        assert "annualized_return_pct" in report
        assert "sharpe" in report
        assert "mdd_pct" in report
        assert "win_rate" in report
        assert "total_trades" in report
        assert "spy_alpha" in report
        assert "exit_distribution" in report

    # Clean up
    del _BACKTEST_RESULTS[bt1["backtest_id"]]
    del _BACKTEST_RESULTS[bt2["backtest_id"]]


@pytest.mark.asyncio
async def test_compare_reports_with_invalid_id(sample_backtest_data):
    """유효하지 않은 ID가 포함된 비교 테스트."""
    bt1 = sample_backtest_data
    _BACKTEST_RESULTS[bt1["backtest_id"]] = bt1

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        # 유효한 ID와 무효한 ID를 함께 전달
        comparison = await compare_reports([bt1["backtest_id"], "invalid-id"])

    # 유효한 ID만 결과에 포함되어야 함
    reports = comparison["comparison"]
    assert len(reports) == 1
    assert reports[0]["backtest_id"] == bt1["backtest_id"]

    del _BACKTEST_RESULTS[bt1["backtest_id"]]


@pytest.mark.asyncio
async def test_exit_reason_estimation():
    """exit_reason이 없을 때 return_pct로 추정하는 테스트."""
    backtest_data = {
        "backtest_id": "test-estimation",
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 1, 4), 108000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 4),
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": 1500.0,
                    "return_pct": 15.0,
                    # exit_reason 없음
                },
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 4),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -800.0,
                    "return_pct": -8.0,
                    # exit_reason 없음
                },
            ],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS["test-estimation"] = backtest_data

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        report = await generate_report("test-estimation")

    exit_dist = report["metrics"]["exit_distribution"]
    # return_pct가 15.0 -> fixed_tp, -8.0 -> fixed_sl로 추정되어야 함
    assert exit_dist.get("fixed_tp", 0) == 1
    assert exit_dist.get("fixed_sl", 0) == 1

    del _BACKTEST_RESULTS["test-estimation"]


@pytest.mark.asyncio
async def test_mdd_calculation():
    """MDD 계산 정확성 테스트."""
    backtest_data = {
        "backtest_id": "test-mdd",
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),  # peak
                (date(2023, 1, 4), 110000.0),  # new peak
                (date(2023, 1, 5), 105000.0),  # -4.5%
                (date(2023, 1, 6), 99000.0),   # -10% from peak (MDD)
                (date(2023, 1, 9), 102000.0),  # recovery
                (date(2023, 1, 10), 115000.0), # new high
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 10),
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": 1000.0,
                    "return_pct": 10.0,
                    "exit_reason": "take_profit",
                },
            ],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS["test-mdd"] = backtest_data

    with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
        mock_hist = AsyncMock()
        mock_hist.iloc = [{"Close": 380.0}, {"Close": 390.0}]
        mock_hist.empty = False
        mock_hist.__len__ = lambda self: 2
        mock_ticker.return_value.history.return_value = mock_hist

        report = await generate_report("test-mdd")

    mdd = report["metrics"]["risk"]["mdd_pct"]
    # 110000 -> 99000 = 10% 하락
    assert mdd == pytest.approx(10.0, rel=0.1)

    del _BACKTEST_RESULTS["test-mdd"]
