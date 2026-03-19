"""백테스트 파라미터 그리드 탐색 모듈."""
import logging
from datetime import date
from itertools import product
from typing import Any

import numpy as np

from api.services.backtester import BacktestConfig, run_backtest

logger = logging.getLogger(__name__)


def _calculate_sharpe(daily_equity: list[tuple[date, float]], rf_annual: float = 0.05) -> float:
    """일별 equity에서 Sharpe ratio를 계산한다.

    Args:
        daily_equity: (date, equity_value) 튜플의 리스트
        rf_annual: 연간 무위험 수익률 (기본값: 5%)

    Returns:
        Sharpe ratio (연율화)
    """
    if len(daily_equity) < 2:
        return 0.0

    equities = [eq for _, eq in daily_equity]
    daily_returns = []
    for i in range(1, len(equities)):
        ret = (equities[i] - equities[i-1]) / equities[i-1]
        daily_returns.append(ret)

    if not daily_returns:
        return 0.0

    mean_return = np.mean(daily_returns)
    std_return = np.std(daily_returns, ddof=1)

    if std_return == 0:
        return 0.0

    rf_daily = rf_annual / 252.0
    excess_return = mean_return - rf_daily
    sharpe = excess_return / std_return * np.sqrt(252)

    return round(float(sharpe), 4)


def _calculate_total_return(daily_equity: list[tuple[date, float]], initial_capital: float) -> float:
    """총 수익률을 계산한다.

    Args:
        daily_equity: (date, equity_value) 튜플의 리스트
        initial_capital: 초기 자본

    Returns:
        총 수익률 (%)
    """
    if not daily_equity:
        return 0.0

    final_equity = daily_equity[-1][1]
    total_return = ((final_equity - initial_capital) / initial_capital) * 100
    return round(float(total_return), 4)


def _calculate_calmar(daily_equity: list[tuple[date, float]], initial_capital: float) -> float:
    """Calmar ratio를 계산한다 (연율화 수익률 / MDD).

    Args:
        daily_equity: (date, equity_value) 튜플의 리스트
        initial_capital: 초기 자본

    Returns:
        Calmar ratio
    """
    if len(daily_equity) < 2:
        return 0.0

    # Calculate annualized return
    final_equity = daily_equity[-1][1]
    total_days = len(daily_equity)
    years = total_days / 252.0

    if years == 0:
        return 0.0

    annualized_return = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

    # Calculate maximum drawdown
    peak = initial_capital
    max_dd = 0.0

    for _, equity in daily_equity:
        if equity > peak:
            peak = equity
        dd = ((equity - peak) / peak) * 100
        if dd < max_dd:
            max_dd = dd

    if max_dd == 0:
        return 0.0

    calmar = annualized_return / abs(max_dd)
    return round(float(calmar), 4)


def _extract_objective_value(
    result: dict,
    objective: str,
    initial_capital: float
) -> float:
    """백테스트 결과에서 목표 지표 값을 추출한다.

    Args:
        result: run_backtest()의 반환 결과
        objective: "sharpe", "total_return", "calmar" 중 하나
        initial_capital: 초기 자본

    Returns:
        목표 지표 값
    """
    daily_equity = result["result"]["daily_equity"]

    if objective == "sharpe":
        return _calculate_sharpe(daily_equity)
    elif objective == "total_return":
        return _calculate_total_return(daily_equity, initial_capital)
    elif objective == "calmar":
        return _calculate_calmar(daily_equity, initial_capital)
    else:
        raise ValueError(f"Unknown objective: {objective}. Must be 'sharpe', 'total_return', or 'calmar'")


def _split_trade_days(
    daily_equity: list[tuple[date, float]],
    train_ratio: float
) -> tuple[date, date]:
    """Walk-forward를 위해 전체 기간을 train/test로 분할한다.

    Args:
        daily_equity: (date, equity_value) 튜플의 리스트
        train_ratio: train 구간 비율 (0.0 ~ 1.0)

    Returns:
        (train_end_date, test_start_date) 튜플
    """
    if not daily_equity:
        raise ValueError("daily_equity is empty")

    total_days = len(daily_equity)
    train_days = int(total_days * train_ratio)

    if train_days < 1:
        train_days = 1
    if train_days >= total_days:
        train_days = total_days - 1

    train_end_date = daily_equity[train_days - 1][0]
    test_start_date = daily_equity[train_days][0]

    return train_end_date, test_start_date


async def run_sensitivity(
    base_config: dict,
    search_space: dict,
    objective: str = "sharpe",
    walk_forward: bool = False,
    train_ratio: float = 0.7
) -> dict:
    """파라미터 그리드 탐색을 수행한다.

    Args:
        base_config: BacktestConfig의 기본 설정 (dict)
        search_space: 탐색할 파라미터와 값들 {"param_name": [val1, val2, ...], ...}
        objective: 최적화할 목표 지표 ("sharpe", "total_return", "calmar")
        walk_forward: Walk-forward 검증 수행 여부
        train_ratio: Walk-forward 시 train 구간 비율 (기본값: 0.7)

    Returns:
        {
            "ranked": 상위 20개 조합 리스트,
            "best": 최고 성능 조합,
            "sensitivity": 파라미터별 영향도 분석,
            "overfit_warning": 과적합 경고 여부
        }
    """
    if not search_space:
        raise ValueError("search_space cannot be empty")

    if objective not in ["sharpe", "total_return", "calmar"]:
        raise ValueError(f"Invalid objective: {objective}. Must be 'sharpe', 'total_return', or 'calmar'")

    # Generate all combinations
    param_names = list(search_space.keys())
    param_values = [search_space[name] for name in param_names]
    combinations = list(product(*param_values))

    total_combinations = len(combinations)
    logger.info(f"Starting grid search with {total_combinations} combinations")

    results = []

    for idx, combo in enumerate(combinations, 1):
        # Create config for this combination
        config_dict = base_config.copy()
        combo_params = {}
        for param_name, param_value in zip(param_names, combo):
            config_dict[param_name] = param_value
            combo_params[param_name] = param_value

        # Log progress every 10 combinations
        if idx % 10 == 0 or idx == total_combinations:
            logger.info(f"Progress: {idx}/{total_combinations} combinations completed")

        try:
            config = BacktestConfig(**config_dict)

            if walk_forward:
                # Run full backtest first to determine split dates
                full_result = await run_backtest(config)
                daily_equity = full_result["result"]["daily_equity"]

                if len(daily_equity) < 10:
                    logger.warning(f"Combo {idx}: Insufficient data for walk-forward")
                    continue

                train_end, test_start = _split_trade_days(daily_equity, train_ratio)

                # Train phase
                train_config = config.model_copy(update={
                    "end_date": train_end
                })
                train_result = await run_backtest(train_config)
                train_objective = _extract_objective_value(
                    train_result,
                    objective,
                    config.initial_capital
                )

                # Test phase
                test_config = config.model_copy(update={
                    "start_date": test_start
                })
                test_result = await run_backtest(test_config)
                test_objective = _extract_objective_value(
                    test_result,
                    objective,
                    config.initial_capital
                )

                overfit_gap = train_objective - test_objective

                results.append({
                    "params": combo_params,
                    "train_objective": round(float(train_objective), 4),
                    "test_objective": round(float(test_objective), 4),
                    "overfit_gap": round(float(overfit_gap), 4),
                    "objective_value": round(float(test_objective), 4)  # Use test for ranking
                })
            else:
                # Standard grid search without walk-forward
                result = await run_backtest(config)
                objective_value = _extract_objective_value(
                    result,
                    objective,
                    config.initial_capital
                )

                results.append({
                    "params": combo_params,
                    "objective_value": round(float(objective_value), 4)
                })

        except Exception as e:
            logger.error(f"Combo {idx} failed: {e}")
            continue

    if not results:
        raise ValueError("No valid results generated from grid search")

    # Sort by objective value (descending - higher is better)
    results.sort(key=lambda x: x["objective_value"], reverse=True)

    # Get top 20 (or less if fewer results)
    ranked = results[:20]
    best = results[0]

    # Calculate sensitivity: for each parameter, compute average objective by value
    sensitivity: dict[str, dict[Any, float]] = {}

    for param_name in param_names:
        param_values_map: dict[Any, list[float]] = {}

        for result_item in results:
            param_val = result_item["params"].get(param_name)
            obj_val = result_item["objective_value"]

            if param_val not in param_values_map:
                param_values_map[param_val] = []
            param_values_map[param_val].append(obj_val)

        # Average objective for each parameter value
        sensitivity[param_name] = {
            val: round(float(np.mean(objectives)), 4)
            for val, objectives in param_values_map.items()
        }

    # Check for overfit warning (walk-forward only)
    overfit_warning = False
    if walk_forward:
        top_5 = results[:5]
        for item in top_5:
            if item.get("overfit_gap", 0) > 0.5:
                overfit_warning = True
                break

    return {
        "ranked": ranked,
        "best": best,
        "sensitivity": sensitivity,
        "overfit_warning": overfit_warning,
        "total_combinations": total_combinations,
        "successful_combinations": len(results),
        "objective": objective
    }
