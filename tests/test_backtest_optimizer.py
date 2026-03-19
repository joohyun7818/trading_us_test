"""백테스트 파라미터 그리드 탐색 테스트."""
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from api.services.backtest_optimizer import (
    run_sensitivity,
    _calculate_sharpe,
    _calculate_total_return,
    _calculate_calmar,
    _extract_objective_value,
    _split_trade_days,
)


@pytest.fixture
def sample_daily_equity():
    """샘플 일별 equity 데이터."""
    return [
        (date(2023, 1, 3), 100000.0),
        (date(2023, 1, 4), 101000.0),
        (date(2023, 1, 5), 102000.0),
        (date(2023, 1, 6), 101500.0),
        (date(2023, 1, 9), 103000.0),
        (date(2023, 1, 10), 104000.0),
        (date(2023, 1, 11), 103500.0),
        (date(2023, 1, 12), 105000.0),
    ]


@pytest.fixture
def sample_backtest_result():
    """샘플 백테스트 결과."""
    return {
        "backtest_id": "test-1",
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
            ],
            "trades": [],
            "signals": [],
        }
    }


@pytest.fixture
def base_config():
    """기본 백테스트 설정."""
    return {
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
        "initial_capital": 100000.0,
        "exit_strategy": "dynamic",
    }


class TestCalculations:
    """지표 계산 함수 테스트."""

    def test_calculate_sharpe(self, sample_daily_equity):
        """Sharpe ratio 계산 테스트."""
        sharpe = _calculate_sharpe(sample_daily_equity)
        assert isinstance(sharpe, float)
        assert sharpe != 0.0

    def test_calculate_sharpe_empty(self):
        """빈 데이터에 대한 Sharpe ratio 계산."""
        assert _calculate_sharpe([]) == 0.0

    def test_calculate_sharpe_single_value(self):
        """단일 데이터 포인트에 대한 Sharpe ratio."""
        equity = [(date(2023, 1, 3), 100000.0)]
        assert _calculate_sharpe(equity) == 0.0

    def test_calculate_total_return(self, sample_daily_equity):
        """총 수익률 계산 테스트."""
        total_return = _calculate_total_return(sample_daily_equity, 100000.0)
        assert isinstance(total_return, float)
        assert total_return == 5.0  # (105000 - 100000) / 100000 * 100

    def test_calculate_total_return_empty(self):
        """빈 데이터에 대한 총 수익률."""
        assert _calculate_total_return([], 100000.0) == 0.0

    def test_calculate_calmar(self, sample_daily_equity):
        """Calmar ratio 계산 테스트."""
        calmar = _calculate_calmar(sample_daily_equity, 100000.0)
        assert isinstance(calmar, float)

    def test_calculate_calmar_empty(self):
        """빈 데이터에 대한 Calmar ratio."""
        assert _calculate_calmar([], 100000.0) == 0.0

    def test_calculate_calmar_single_value(self):
        """단일 데이터 포인트에 대한 Calmar ratio."""
        equity = [(date(2023, 1, 3), 100000.0)]
        assert _calculate_calmar(equity, 100000.0) == 0.0


class TestExtractObjective:
    """목표 지표 추출 테스트."""

    def test_extract_sharpe(self, sample_backtest_result):
        """Sharpe ratio 추출."""
        value = _extract_objective_value(sample_backtest_result, "sharpe", 100000.0)
        assert isinstance(value, float)

    def test_extract_total_return(self, sample_backtest_result):
        """총 수익률 추출."""
        value = _extract_objective_value(sample_backtest_result, "total_return", 100000.0)
        assert isinstance(value, float)
        assert value == 3.0  # (103000 - 100000) / 100000 * 100

    def test_extract_calmar(self, sample_backtest_result):
        """Calmar ratio 추출."""
        value = _extract_objective_value(sample_backtest_result, "calmar", 100000.0)
        assert isinstance(value, float)

    def test_extract_invalid_objective(self, sample_backtest_result):
        """잘못된 목표 지표."""
        with pytest.raises(ValueError, match="Unknown objective"):
            _extract_objective_value(sample_backtest_result, "invalid", 100000.0)


class TestSplitTradeDays:
    """거래일 분할 테스트."""

    def test_split_70_30(self, sample_daily_equity):
        """70/30 분할 테스트."""
        train_end, test_start = _split_trade_days(sample_daily_equity, 0.7)
        assert isinstance(train_end, date)
        assert isinstance(test_start, date)
        assert train_end < test_start

    def test_split_empty(self):
        """빈 데이터 분할."""
        with pytest.raises(ValueError, match="daily_equity is empty"):
            _split_trade_days([], 0.7)

    def test_split_extreme_ratio(self, sample_daily_equity):
        """극단적인 비율 테스트."""
        # Very small train ratio
        train_end, test_start = _split_trade_days(sample_daily_equity, 0.1)
        assert train_end < test_start

        # Very large train ratio
        train_end, test_start = _split_trade_days(sample_daily_equity, 0.95)
        assert train_end < test_start


class TestRunSensitivity:
    """run_sensitivity 함수 테스트."""

    @pytest.mark.asyncio
    async def test_basic_grid_search(self, base_config):
        """기본 그리드 탐색 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
            "trailing_stop_atr_mult": [1.5, 2.0],
        }

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": [
                    (date(2023, 1, 3), 100000.0),
                    (date(2023, 1, 4), 101000.0),
                    (date(2023, 1, 5), 102000.0),
                ],
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe"
            )

            assert "ranked" in result
            assert "best" in result
            assert "sensitivity" in result
            assert "overfit_warning" in result
            assert result["total_combinations"] == 4  # 2 * 2 = 4
            assert len(result["ranked"]) <= 20

    @pytest.mark.asyncio
    async def test_empty_search_space(self, base_config):
        """빈 탐색 공간 테스트."""
        with pytest.raises(ValueError, match="search_space cannot be empty"):
            await run_sensitivity(
                base_config=base_config,
                search_space={},
                objective="sharpe"
            )

    @pytest.mark.asyncio
    async def test_invalid_objective(self, base_config):
        """잘못된 목표 지표 테스트."""
        search_space = {"hard_stop_atr_mult": [2.0, 2.5]}

        with pytest.raises(ValueError, match="Invalid objective"):
            await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="invalid"
            )

    @pytest.mark.asyncio
    async def test_total_return_objective(self, base_config):
        """총 수익률 목표 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
        }

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": [
                    (date(2023, 1, 3), 100000.0),
                    (date(2023, 1, 4), 105000.0),
                ],
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="total_return"
            )

            assert result["objective"] == "total_return"
            assert result["best"]["objective_value"] == 5.0

    @pytest.mark.asyncio
    async def test_calmar_objective(self, base_config):
        """Calmar ratio 목표 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0],
        }

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": [
                    (date(2023, 1, 3), 100000.0),
                    (date(2023, 1, 4), 101000.0),
                    (date(2023, 1, 5), 102000.0),
                    (date(2023, 1, 6), 101500.0),
                    (date(2023, 1, 9), 103000.0),
                ],
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="calmar"
            )

            assert result["objective"] == "calmar"
            assert isinstance(result["best"]["objective_value"], float)

    @pytest.mark.asyncio
    async def test_sensitivity_analysis(self, base_config):
        """파라미터 민감도 분석 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5, 3.0],
            "trailing_stop_atr_mult": [1.5, 2.0],
        }

        call_count = 0

        async def mock_run_backtest(config):
            nonlocal call_count
            call_count += 1
            return {
                "backtest_id": f"test-{call_count}",
                "config": config.model_dump(),
                "result": {
                    "daily_equity": [
                        (date(2023, 1, 3), 100000.0),
                        (date(2023, 1, 4), 100000.0 + call_count * 1000),
                    ],
                    "trades": [],
                    "signals": [],
                }
            }

        with patch("api.services.backtest_optimizer.run_backtest", side_effect=mock_run_backtest):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="total_return"
            )

            # Check sensitivity structure
            assert "sensitivity" in result
            assert "hard_stop_atr_mult" in result["sensitivity"]
            assert "trailing_stop_atr_mult" in result["sensitivity"]

            # Each parameter value should have an average objective
            for param_name, param_dict in result["sensitivity"].items():
                for param_val, avg_obj in param_dict.items():
                    assert isinstance(avg_obj, float)

    @pytest.mark.asyncio
    async def test_walk_forward_validation(self, base_config):
        """Walk-forward 검증 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
        }

        # Create longer daily equity for split
        long_equity = [(date(2023, 1, i+1), 100000.0 + i * 100) for i in range(20)]

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": long_equity,
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe",
                walk_forward=True,
                train_ratio=0.7
            )

            assert "ranked" in result
            assert "overfit_warning" in result

            # Check that results have train/test split info
            best = result["best"]
            assert "train_objective" in best
            assert "test_objective" in best
            assert "overfit_gap" in best

    @pytest.mark.asyncio
    async def test_overfit_warning(self, base_config):
        """과적합 경고 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
        }

        long_equity = [(date(2023, 1, i+1), 100000.0 + i * 100) for i in range(20)]

        call_count = 0

        async def mock_run_backtest_overfit(config):
            nonlocal call_count
            call_count += 1
            # Simulate overfitting: train performs much better than test
            return {
                "backtest_id": f"test-{call_count}",
                "config": config.model_dump(),
                "result": {
                    "daily_equity": long_equity,
                    "trades": [],
                    "signals": [],
                }
            }

        with patch("api.services.backtest_optimizer.run_backtest", side_effect=mock_run_backtest_overfit):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe",
                walk_forward=True,
                train_ratio=0.7
            )

            # Check structure exists
            assert "overfit_warning" in result
            assert isinstance(result["overfit_warning"], bool)

    @pytest.mark.asyncio
    async def test_large_combination_count(self, base_config):
        """많은 조합 수 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5, 3.0],
            "trailing_stop_atr_mult": [1.5, 2.0, 2.5],
            "max_holding_days": [10, 15, 20],
        }

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": [
                    (date(2023, 1, 3), 100000.0),
                    (date(2023, 1, 4), 101000.0),
                ],
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe"
            )

            # 3 * 3 * 3 = 27 combinations
            assert result["total_combinations"] == 27
            assert result["successful_combinations"] <= 27

    @pytest.mark.asyncio
    async def test_failed_combinations_handling(self, base_config):
        """실패한 조합 처리 테스트."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
        }

        call_count = 0

        async def mock_run_backtest_with_failure(config):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated failure")
            return {
                "backtest_id": f"test-{call_count}",
                "config": config.model_dump(),
                "result": {
                    "daily_equity": [
                        (date(2023, 1, 3), 100000.0),
                        (date(2023, 1, 4), 101000.0),
                    ],
                    "trades": [],
                    "signals": [],
                }
            }

        with patch("api.services.backtest_optimizer.run_backtest", side_effect=mock_run_backtest_with_failure):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe"
            )

            # Should have 1 successful result (2nd call)
            assert result["total_combinations"] == 2
            assert result["successful_combinations"] == 1

    @pytest.mark.asyncio
    async def test_all_combinations_fail(self, base_config):
        """모든 조합이 실패하는 경우."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 2.5],
        }

        async def mock_run_backtest_always_fail(config):
            raise ValueError("All combinations fail")

        with patch("api.services.backtest_optimizer.run_backtest", side_effect=mock_run_backtest_always_fail):
            with pytest.raises(ValueError, match="No valid results generated"):
                await run_sensitivity(
                    base_config=base_config,
                    search_space=search_space,
                    objective="sharpe"
                )

    @pytest.mark.asyncio
    async def test_multiple_parameters(self, base_config):
        """여러 파라미터 동시 탐색."""
        search_space = {
            "hard_stop_atr_mult": [2.0, 3.0],
            "trailing_stop_atr_mult": [1.5, 2.5],
            "max_holding_days": [10, 20],
            "risk_per_trade_pct": [0.5, 1.0],
        }

        mock_result = {
            "backtest_id": "test-1",
            "config": base_config,
            "result": {
                "daily_equity": [
                    (date(2023, 1, 3), 100000.0),
                    (date(2023, 1, 4), 101000.0),
                ],
                "trades": [],
                "signals": [],
            }
        }

        with patch("api.services.backtest_optimizer.run_backtest", new=AsyncMock(return_value=mock_result)):
            result = await run_sensitivity(
                base_config=base_config,
                search_space=search_space,
                objective="sharpe"
            )

            # 2^4 = 16 combinations
            assert result["total_combinations"] == 16

            # All parameters should be in sensitivity analysis
            assert len(result["sensitivity"]) == 4
            assert "hard_stop_atr_mult" in result["sensitivity"]
            assert "trailing_stop_atr_mult" in result["sensitivity"]
            assert "max_holding_days" in result["sensitivity"]
            assert "risk_per_trade_pct" in result["sensitivity"]
