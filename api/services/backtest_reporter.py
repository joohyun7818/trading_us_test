"""백테스트 결과 자동 분석 및 진단 리포트 시스템."""
import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

import yfinance as yf

from api.services.backtester import _BACKTEST_RESULTS

logger = logging.getLogger(__name__)


async def generate_report(backtest_id: str) -> dict:
    """백테스트 결과를 분석하고 자동 진단 리포트를 생성한다.

    Args:
        backtest_id: 분석할 백테스트 ID

    Returns:
        분석 리포트 딕셔너리 (metrics, benchmark, diagnoses 포함)

    Raises:
        ValueError: backtest_id가 존재하지 않을 경우
    """
    backtest_data = _BACKTEST_RESULTS.get(backtest_id)
    if not backtest_data:
        raise ValueError(f"Backtest {backtest_id} not found")

    config = backtest_data["config"]
    result = backtest_data["result"]
    daily_equity = result["daily_equity"]
    trades = result["trades"]

    if not daily_equity:
        return {
            "backtest_id": backtest_id,
            "metrics": {},
            "benchmark": {},
            "diagnoses": []
        }

    # 수익률 지표 계산
    initial_equity = daily_equity[0][1]
    final_equity = daily_equity[-1][1]
    total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100

    # 연율화 수익률 (252 거래일 기준)
    start_date = daily_equity[0][0]
    end_date = daily_equity[-1][0]
    if isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)

    trading_days = len(daily_equity)
    years = trading_days / 252.0 if trading_days > 0 else 1.0
    annualized_return_pct = ((final_equity / initial_equity) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # 일일 수익률 계산
    daily_returns = []
    for i in range(1, len(daily_equity)):
        prev_equity = daily_equity[i-1][1]
        curr_equity = daily_equity[i][1]
        if prev_equity > 0:
            daily_returns.append((curr_equity - prev_equity) / prev_equity)

    # 리스크 지표
    import numpy as np
    daily_returns_arr = np.array(daily_returns)
    daily_volatility = float(np.std(daily_returns_arr)) if len(daily_returns_arr) > 0 else 0.0

    # MDD (Maximum Drawdown) 계산
    peak = daily_equity[0][1]
    max_dd = 0.0
    max_dd_start_idx = 0
    max_dd_end_idx = 0
    current_dd_start_idx = 0

    for i, (_, equity) in enumerate(daily_equity):
        if equity > peak:
            peak = equity
            current_dd_start_idx = i
        dd = (equity - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            max_dd_start_idx = current_dd_start_idx
            max_dd_end_idx = i

    mdd_pct = abs(max_dd) * 100
    mdd_duration_days = max_dd_end_idx - max_dd_start_idx if max_dd_end_idx > max_dd_start_idx else 0

    # 효율 지표
    # Sharpe Ratio (rf=5% 연율)
    rf_daily = 0.05 / 252.0
    excess_returns = daily_returns_arr - rf_daily
    sharpe = float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)) if len(excess_returns) > 0 and np.std(excess_returns) > 0 else 0.0

    # Sortino Ratio (하방 변동성만 고려)
    downside_returns = excess_returns[excess_returns < 0]
    downside_std = float(np.std(downside_returns)) if len(downside_returns) > 0 else 0.0
    sortino = float(np.mean(excess_returns) / downside_std * np.sqrt(252)) if downside_std > 0 else 0.0

    # Calmar Ratio
    calmar = annualized_return_pct / mdd_pct if mdd_pct > 0 else 0.0

    # 거래 지표
    total_trades = len(trades)
    winning_trades = [t for t in trades if t["pnl"] > 0]
    losing_trades = [t for t in trades if t["pnl"] < 0]

    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0

    avg_win = sum(t["pnl"] for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
    avg_loss = sum(t["pnl"] for t in losing_trades) / len(losing_trades) if losing_trades else 0.0

    total_gains = sum(t["pnl"] for t in winning_trades)
    total_losses = abs(sum(t["pnl"] for t in losing_trades))
    profit_factor = total_gains / total_losses if total_losses > 0 else 0.0

    # 평균 보유 기간
    holding_days = []
    for trade in trades:
        entry = trade["entry_date"]
        exit_dt = trade["exit_date"]
        if isinstance(entry, str):
            entry = date.fromisoformat(entry)
        if isinstance(exit_dt, str):
            exit_dt = date.fromisoformat(exit_dt)
        holding_days.append((exit_dt - entry).days)
    avg_holding_days = sum(holding_days) / len(holding_days) if holding_days else 0.0

    # 최대 연속 손실
    max_consecutive_losses = 0
    current_consecutive = 0
    for trade in trades:
        if trade["pnl"] < 0:
            current_consecutive += 1
            max_consecutive_losses = max(max_consecutive_losses, current_consecutive)
        else:
            current_consecutive = 0

    # 청산 분포
    exit_reason_dist = {}
    for trade in trades:
        reason = trade.get("exit_reason")
        if not reason:
            # exit_reason이 없으면 return_pct로 추정
            ret = trade.get("return_pct", 0.0)
            if abs(ret - (-8.0)) < 0.5:
                reason = "fixed_sl"
            elif abs(ret - 15.0) < 0.5:
                reason = "fixed_tp"
            else:
                reason = "other"
        exit_reason_dist[reason] = exit_reason_dist.get(reason, 0) + 1

    # 벤치마크 (SPY) 조회
    benchmark = await _fetch_spy_benchmark(start_date, end_date)
    alpha = total_return_pct - benchmark.get("spy_return_pct", 0.0)

    # 자동 진단
    diagnoses = _generate_diagnoses(
        exit_reason_dist=exit_reason_dist,
        total_trades=total_trades,
        trading_days=trading_days,
        sharpe=sharpe,
        alpha=alpha,
        avg_holding_days=avg_holding_days
    )

    return {
        "backtest_id": backtest_id,
        "metrics": {
            "profit": {
                "total_return_pct": round(total_return_pct, 2),
                "annualized_return_pct": round(annualized_return_pct, 2),
            },
            "risk": {
                "mdd_pct": round(mdd_pct, 2),
                "mdd_duration_days": mdd_duration_days,
                "daily_volatility": round(daily_volatility, 4),
            },
            "efficiency": {
                "sharpe": round(sharpe, 2),
                "sortino": round(sortino, 2),
                "calmar": round(calmar, 2),
            },
            "trading": {
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "avg_holding_days": round(avg_holding_days, 1),
                "max_consecutive_losses": max_consecutive_losses,
            },
            "exit_distribution": exit_reason_dist,
        },
        "benchmark": {
            "spy_return_pct": benchmark.get("spy_return_pct", 0.0),
            "alpha": round(alpha, 2),
        },
        "diagnoses": diagnoses,
    }


async def _fetch_spy_benchmark(start_date: date, end_date: date) -> dict:
    """SPY 벤치마크 수익률을 yfinance로 조회한다.

    Args:
        start_date: 시작일
        end_date: 종료일

    Returns:
        SPY 수익률 정보
    """
    def _fetch_spy():
        try:
            # yfinance는 동기 함수이므로 별도 스레드에서 실행
            spy = yf.Ticker("SPY")
            # 종료일에 +1일 해서 inclusive하게 조회
            hist = spy.history(start=start_date, end=end_date + timedelta(days=1))
            if hist.empty or len(hist) < 2:
                return {"spy_return_pct": 0.0}

            first_close = hist.iloc[0]["Close"]
            last_close = hist.iloc[-1]["Close"]
            spy_return = ((last_close - first_close) / first_close) * 100
            return {"spy_return_pct": round(spy_return, 2)}
        except Exception as e:
            logger.warning("Failed to fetch SPY benchmark: %s", e)
            return {"spy_return_pct": 0.0}

    return await asyncio.to_thread(_fetch_spy)


def _generate_diagnoses(
    *,
    exit_reason_dist: dict,
    total_trades: int,
    trading_days: int,
    sharpe: float,
    alpha: float,
    avg_holding_days: float
) -> list[dict]:
    """자동 진단 결과를 생성한다.

    Returns:
        진단 결과 리스트 (severity 순으로 정렬)
    """
    diagnoses = []

    # 동적 청산 비율 체크
    dynamic_exits = sum(
        count for reason, count in exit_reason_dist.items()
        if reason in ["atr_hard_stop", "trailing_stop", "time_limit", "partial_take_profit"]
    )
    dynamic_ratio = (dynamic_exits / total_trades * 100) if total_trades > 0 else 0.0
    if dynamic_ratio < 5.0:
        diagnoses.append({
            "severity": "CRITICAL",
            "message": "고정 SL/TP 종속",
            "detail": f"동적 청산 비율 {dynamic_ratio:.1f}% < 5%"
        })

    # 월 평균 거래 빈도
    months = trading_days / 21.0 if trading_days > 0 else 1.0
    monthly_trades = total_trades / months
    if monthly_trades < 5.0:
        diagnoses.append({
            "severity": "HIGH",
            "message": "저빈도",
            "detail": f"월 평균 거래 {monthly_trades:.1f}건 < 5건"
        })

    # Sharpe ratio
    if sharpe < 0.5:
        diagnoses.append({
            "severity": "HIGH",
            "message": "낮은 위험조정 수익",
            "detail": f"Sharpe {sharpe:.2f} < 0.5"
        })

    # Alpha (벤치마크 대비)
    if alpha < -10:
        diagnoses.append({
            "severity": "CRITICAL",
            "message": "심각한 벤치마크 언더퍼폼",
            "detail": f"Alpha {alpha:.2f}% < -10%"
        })

    # 평균 보유 기간
    if avg_holding_days > 25:
        diagnoses.append({
            "severity": "MEDIUM",
            "message": "과도 보유",
            "detail": f"평균 보유 {avg_holding_days:.1f}일 > 25일"
        })

    # severity 순으로 정렬
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
    diagnoses.sort(key=lambda d: severity_order.get(d["severity"], 99))

    return diagnoses


async def compare_reports(backtest_ids: list[str]) -> dict:
    """여러 백테스트의 주요 지표를 비교한다.

    Args:
        backtest_ids: 비교할 백테스트 ID 리스트

    Returns:
        비교 테이블 (각 백테스트의 주요 지표 포함)
    """
    reports = []
    for backtest_id in backtest_ids:
        try:
            report = await generate_report(backtest_id)
            # 주요 지표만 추출
            metrics = report["metrics"]
            benchmark = report["benchmark"]

            summary = {
                "backtest_id": backtest_id,
                "total_return_pct": metrics["profit"]["total_return_pct"],
                "annualized_return_pct": metrics["profit"]["annualized_return_pct"],
                "sharpe": metrics["efficiency"]["sharpe"],
                "sortino": metrics["efficiency"]["sortino"],
                "calmar": metrics["efficiency"]["calmar"],
                "mdd_pct": metrics["risk"]["mdd_pct"],
                "win_rate": metrics["trading"]["win_rate"],
                "total_trades": metrics["trading"]["total_trades"],
                "profit_factor": metrics["trading"]["profit_factor"],
                "avg_holding_days": metrics["trading"]["avg_holding_days"],
                "spy_alpha": benchmark["alpha"],
                "exit_distribution": metrics["exit_distribution"],
            }
            reports.append(summary)
        except ValueError as e:
            logger.warning("Failed to generate report for %s: %s", backtest_id, e)

    return {"comparison": reports}
