"""완료 기준 검증 테스트 - 실제 사용 시나리오."""
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from api.services.backtester import run_backtest, BacktestConfig, _BACKTEST_RESULTS
from api.services.backtest_reporter import generate_report, compare_reports


@pytest.mark.asyncio
async def test_completion_criteria_all_metrics_present():
    """완료 기준: 리포트에 Sharpe, MDD, win_rate, exit_reason 분포, SPY alpha가 모두 포함."""
    # Create a backtest result with comprehensive data
    backtest_id = "completion-test-1"
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
                (date(2023, 2, 1), 105000.0),
                (date(2023, 3, 1), 108000.0),
                (date(2023, 4, 3), 107000.0),
                (date(2023, 5, 1), 110000.0),
                (date(2023, 6, 1), 112000.0),
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
                {
                    "entry_date": date(2023, 1, 15),
                    "exit_date": date(2023, 1, 20),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -500.0,
                    "return_pct": -5.0,
                    "exit_reason": "stop_loss",
                },
                {
                    "entry_date": date(2023, 2, 1),
                    "exit_date": date(2023, 2, 10),
                    "symbol": "GOOGL",
                    "side": "LONG",
                    "pnl": 1500.0,
                    "return_pct": 12.0,
                    "exit_reason": "trailing_stop",
                },
                {
                    "entry_date": date(2023, 3, 1),
                    "exit_date": date(2023, 3, 5),
                    "symbol": "AMZN",
                    "side": "LONG",
                    "pnl": 800.0,
                    "return_pct": 8.0,
                    "exit_reason": "atr_hard_stop",
                },
                {
                    "entry_date": date(2023, 4, 1),
                    "exit_date": date(2023, 4, 3),
                    "symbol": "TSLA",
                    "side": "LONG",
                    "pnl": -200.0,
                    "return_pct": -2.0,
                    "exit_reason": "time_limit",
                },
            ],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS[backtest_id] = backtest_data

    try:
        with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
            mock_hist = AsyncMock()
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 395.0}]
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            report = await generate_report(backtest_id)

        # ✓ Sharpe 포함 확인
        assert "sharpe" in report["metrics"]["efficiency"]
        sharpe = report["metrics"]["efficiency"]["sharpe"]
        print(f"✓ Sharpe Ratio: {sharpe}")

        # ✓ MDD 포함 확인
        assert "mdd_pct" in report["metrics"]["risk"]
        mdd = report["metrics"]["risk"]["mdd_pct"]
        print(f"✓ MDD: {mdd}%")

        # ✓ win_rate 포함 확인
        assert "win_rate" in report["metrics"]["trading"]
        win_rate = report["metrics"]["trading"]["win_rate"]
        print(f"✓ Win Rate: {win_rate}%")

        # ✓ exit_reason 분포 포함 확인
        assert "exit_distribution" in report["metrics"]
        exit_dist = report["metrics"]["exit_distribution"]
        print(f"✓ Exit Distribution: {exit_dist}")
        # 다양한 exit_reason이 포함되어 있는지 확인
        assert "take_profit" in exit_dist
        assert "stop_loss" in exit_dist
        assert "trailing_stop" in exit_dist
        assert "atr_hard_stop" in exit_dist
        assert "time_limit" in exit_dist

        # ✓ SPY alpha 포함 확인
        assert "alpha" in report["benchmark"]
        alpha = report["benchmark"]["alpha"]
        print(f"✓ SPY Alpha: {alpha}%")

        print("\n✅ 완료 기준 1: 모든 주요 지표(Sharpe, MDD, win_rate, exit_reason 분포, SPY alpha) 포함 - 통과")

    finally:
        del _BACKTEST_RESULTS[backtest_id]


@pytest.mark.asyncio
async def test_completion_criteria_auto_diagnosis_with_severity():
    """완료 기준: 자동 진단 결과 3건 이상, severity 순 정렬."""
    # Create a backtest with poor performance to trigger multiple diagnoses
    backtest_id = "diagnosis-test"
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
                (date(2023, 3, 1), 95000.0),
                (date(2023, 6, 1), 90000.0),
                (date(2023, 9, 1), 85000.0),
                (date(2023, 12, 29), 80000.0),
            ],
            "trades": [
                # Only 2 trades over the year (low frequency)
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 2, 28),  # 56 days (over 25)
                    "symbol": "AAPL",
                    "side": "LONG",
                    "pnl": -5000.0,
                    "return_pct": -8.0,
                    "exit_reason": "stop_loss",  # Fixed exit
                },
                {
                    "entry_date": date(2023, 6, 1),
                    "exit_date": date(2023, 7, 30),  # 59 days (over 25)
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -10000.0,
                    "return_pct": -15.0,
                    "exit_reason": "take_profit",  # Fixed exit
                },
            ],
            "signals": [],
        },
    }
    _BACKTEST_RESULTS[backtest_id] = backtest_data

    try:
        with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
            # Mock SPY with positive return to trigger alpha underperformance
            mock_hist = AsyncMock()
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 425.0}]  # ~12% gain
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            report = await generate_report(backtest_id)

        diagnoses = report["diagnoses"]
        print(f"\n진단 결과 개수: {len(diagnoses)}")

        # ✓ 진단 결과 3건 이상
        assert len(diagnoses) >= 3, f"Expected at least 3 diagnoses, got {len(diagnoses)}"
        print("✓ 진단 결과 3건 이상")

        # ✓ Severity 순 정렬 확인 (CRITICAL -> HIGH -> MEDIUM -> INFO)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
        for i in range(len(diagnoses) - 1):
            current = diagnoses[i]["severity"]
            next_sev = diagnoses[i + 1]["severity"]
            assert severity_order[current] <= severity_order[next_sev], \
                f"Diagnoses not sorted: {current} comes before {next_sev}"
        print("✓ Severity 순 정렬 확인")

        # 진단 내용 출력
        print("\n진단 상세:")
        for idx, diag in enumerate(diagnoses, 1):
            print(f"  {idx}. [{diag['severity']}] {diag['message']}: {diag['detail']}")

        print("\n✅ 완료 기준 2: 자동 진단 3건 이상, severity 순 정렬 - 통과")

    finally:
        del _BACKTEST_RESULTS[backtest_id]


@pytest.mark.asyncio
async def test_completion_criteria_compare_multiple_backtests():
    """완료 기준: compare에서 두 백테스트를 나란히 비교 가능."""
    # Create two backtests
    bt1_id = "compare-test-1"
    bt2_id = "compare-test-2"

    bt1_data = {
        "backtest_id": bt1_id,
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 12, 29), 110000.0),
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

    bt2_data = {
        "backtest_id": bt2_id,
        "config": {"start_date": "2023-01-01", "end_date": "2023-12-31"},
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 12, 29), 115000.0),
            ],
            "trades": [
                {
                    "entry_date": date(2023, 1, 3),
                    "exit_date": date(2023, 1, 10),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": 1500.0,
                    "return_pct": 15.0,
                    "exit_reason": "trailing_stop",
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
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 395.0}]
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            comparison = await compare_reports([bt1_id, bt2_id])

        # ✓ 비교 결과 구조 확인
        assert "comparison" in comparison
        reports = comparison["comparison"]
        assert len(reports) == 2
        print(f"✓ 2개 백테스트 비교 결과 포함")

        # ✓ 각 리포트에 주요 지표가 포함되어 있는지 확인
        required_fields = [
            "backtest_id",
            "total_return_pct",
            "annualized_return_pct",
            "sharpe",
            "sortino",
            "calmar",
            "mdd_pct",
            "win_rate",
            "total_trades",
            "profit_factor",
            "avg_holding_days",
            "spy_alpha",
            "exit_distribution",
        ]

        print("\n비교 리포트 상세:")
        for report in reports:
            print(f"\n백테스트 ID: {report['backtest_id']}")
            for field in required_fields:
                assert field in report, f"Missing field: {field}"
                if field != "backtest_id" and field != "exit_distribution":
                    print(f"  {field}: {report[field]}")

        print("\n✓ 모든 주요 지표가 나란히 비교 가능")
        print("\n✅ 완료 기준 3: 두 백테스트를 나란히 비교 가능 - 통과")

    finally:
        del _BACKTEST_RESULTS[bt1_id]
        del _BACKTEST_RESULTS[bt2_id]


@pytest.mark.asyncio
async def test_completion_criteria_backtest_id_compatibility():
    """완료 기준: 기존 Backtest 1, 2의 backtest_id로 리포트 생성 가능."""
    # Simulate existing backtest results with any backtest_id
    existing_bt_id = "existing-backtest-123"

    # Mock a realistic existing backtest result
    existing_data = {
        "backtest_id": existing_bt_id,
        "config": {
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000.0,
            "exit_strategy": "fixed",
        },
        "result": {
            "daily_equity": [
                (date(2023, 1, 3), 100000.0),
                (date(2023, 6, 30), 105000.0),
                (date(2023, 12, 29), 112000.0),
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
                {
                    "entry_date": date(2023, 2, 1),
                    "exit_date": date(2023, 2, 5),
                    "symbol": "MSFT",
                    "side": "LONG",
                    "pnl": -500.0,
                    "return_pct": -5.0,
                    "exit_reason": "stop_loss",
                },
            ],
            "signals": [],
        },
    }

    _BACKTEST_RESULTS[existing_bt_id] = existing_data

    try:
        with patch("api.services.backtest_reporter.yf.Ticker") as mock_ticker:
            mock_hist = AsyncMock()
            mock_hist.iloc = [{"Close": 380.0}, {"Close": 395.0}]
            mock_hist.empty = False
            mock_hist.__len__ = lambda self: 2
            mock_ticker.return_value.history.return_value = mock_hist

            # ✓ 기존 백테스트 ID로 리포트 생성 가능
            report = await generate_report(existing_bt_id)

        assert report["backtest_id"] == existing_bt_id
        assert "metrics" in report
        assert "benchmark" in report
        assert "diagnoses" in report

        print(f"✓ 기존 백테스트 ID '{existing_bt_id}'로 리포트 생성 성공")
        print(f"  - 총 수익률: {report['metrics']['profit']['total_return_pct']}%")
        print(f"  - Sharpe: {report['metrics']['efficiency']['sharpe']}")
        print(f"  - Win Rate: {report['metrics']['trading']['win_rate']}%")

        print("\n✅ 완료 기준 4: 기존 백테스트 ID로 리포트 생성 가능 - 통과")

    finally:
        del _BACKTEST_RESULTS[existing_bt_id]


if __name__ == "__main__":
    # Run all completion criteria tests
    import asyncio

    async def run_all():
        print("=" * 80)
        print("백테스트 리포트 시스템 완료 기준 검증")
        print("=" * 80)

        await test_completion_criteria_all_metrics_present()
        print()
        await test_completion_criteria_auto_diagnosis_with_severity()
        print()
        await test_completion_criteria_compare_multiple_backtests()
        print()
        await test_completion_criteria_backtest_id_compatibility()

        print("\n" + "=" * 80)
        print("✅ 모든 완료 기준 통과!")
        print("=" * 80)

    asyncio.run(run_all())
