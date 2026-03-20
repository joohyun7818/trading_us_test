"""
Live trading readiness gate evaluation service.

Evaluates whether the system is ready to transition from paper to live trading
based on performance metrics, risk indicators, and system configuration.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from api.core.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)

# Gate criteria for live trading readiness
GATE_CRITERIA = {
    "min_paper_weeks": 12,
    "min_sharpe": 0.8,
    "max_mdd_pct": -15.0,
    "min_win_rate_pct": 45.0,
    "min_profit_factor": 1.2,
    "min_total_trades": 50,
    "max_critical_alerts_30d": 0,
    "dynamic_exit_enabled": True,
    "atr_sizing_enabled": True,
}


async def evaluate_live_readiness() -> dict:
    """
    Evaluate whether the system is ready for live trading.

    Checks:
    - Minimum paper trading duration (12 weeks)
    - Performance metrics (Sharpe ratio, MDD, win rate, profit factor)
    - Minimum number of trades
    - System configuration (dynamic exit, ATR sizing)
    - Critical alerts in last 30 days

    Returns:
        Dictionary containing:
        - ready: bool - whether all criteria are met
        - score: float - percentage of criteria passed (0-100)
        - criteria: dict - detailed breakdown of each criterion
        - blocking: list - list of failed criteria
        - staged_plan: dict - phased rollout plan
    """
    criteria_results = {}
    blocking = []

    # 1. Check paper trading duration (using daily_snapshot)
    paper_weeks_actual = await _get_paper_trading_weeks()
    criteria_results["paper_weeks"] = {
        "required": GATE_CRITERIA["min_paper_weeks"],
        "actual": paper_weeks_actual,
        "passed": paper_weeks_actual >= GATE_CRITERIA["min_paper_weeks"],
    }
    if not criteria_results["paper_weeks"]["passed"]:
        blocking.append(f"Paper trading weeks: {paper_weeks_actual} < {GATE_CRITERIA['min_paper_weeks']} required")

    # 2. Calculate Sharpe ratio from daily returns
    sharpe_actual = await _calculate_sharpe_ratio()
    criteria_results["sharpe_ratio"] = {
        "required": GATE_CRITERIA["min_sharpe"],
        "actual": round(sharpe_actual, 2) if sharpe_actual is not None else None,
        "passed": sharpe_actual is not None and sharpe_actual >= GATE_CRITERIA["min_sharpe"],
    }
    if not criteria_results["sharpe_ratio"]["passed"]:
        sharpe_str = f"{sharpe_actual:.2f}" if sharpe_actual is not None else "N/A"
        blocking.append(f"Sharpe ratio: {sharpe_str} < {GATE_CRITERIA['min_sharpe']} required")

    # 3. Calculate maximum drawdown
    mdd_actual = await _calculate_max_drawdown()
    criteria_results["max_drawdown"] = {
        "required": GATE_CRITERIA["max_mdd_pct"],
        "actual": round(mdd_actual, 2) if mdd_actual is not None else None,
        "passed": mdd_actual is not None and mdd_actual >= GATE_CRITERIA["max_mdd_pct"],
    }
    if not criteria_results["max_drawdown"]["passed"]:
        mdd_str = f"{mdd_actual:.2f}" if mdd_actual is not None else "N/A"
        blocking.append(f"Max drawdown: {mdd_str}% worse than {GATE_CRITERIA['max_mdd_pct']}% limit")

    # 4. Calculate win rate
    win_rate_actual = await _calculate_win_rate()
    criteria_results["win_rate"] = {
        "required": GATE_CRITERIA["min_win_rate_pct"],
        "actual": round(win_rate_actual, 2) if win_rate_actual is not None else None,
        "passed": win_rate_actual is not None and win_rate_actual >= GATE_CRITERIA["min_win_rate_pct"],
    }
    if not criteria_results["win_rate"]["passed"]:
        win_rate_str = f"{win_rate_actual:.2f}" if win_rate_actual is not None else "N/A"
        blocking.append(f"Win rate: {win_rate_str}% < {GATE_CRITERIA['min_win_rate_pct']}% required")

    # 5. Calculate profit factor
    profit_factor_actual = await _calculate_profit_factor()
    criteria_results["profit_factor"] = {
        "required": GATE_CRITERIA["min_profit_factor"],
        "actual": round(profit_factor_actual, 2) if profit_factor_actual is not None else None,
        "passed": profit_factor_actual is not None and profit_factor_actual >= GATE_CRITERIA["min_profit_factor"],
    }
    if not criteria_results["profit_factor"]["passed"]:
        pf_str = f"{profit_factor_actual:.2f}" if profit_factor_actual is not None else "N/A"
        blocking.append(f"Profit factor: {pf_str} < {GATE_CRITERIA['min_profit_factor']} required")

    # 6. Check total trades
    total_trades_actual = await _count_total_trades()
    criteria_results["total_trades"] = {
        "required": GATE_CRITERIA["min_total_trades"],
        "actual": total_trades_actual,
        "passed": total_trades_actual >= GATE_CRITERIA["min_total_trades"],
    }
    if not criteria_results["total_trades"]["passed"]:
        blocking.append(f"Total trades: {total_trades_actual} < {GATE_CRITERIA['min_total_trades']} required")

    # 7. Check critical alerts in last 30 days
    critical_alerts_actual = await _count_critical_alerts()
    criteria_results["critical_alerts_30d"] = {
        "required": GATE_CRITERIA["max_critical_alerts_30d"],
        "actual": critical_alerts_actual,
        "passed": critical_alerts_actual <= GATE_CRITERIA["max_critical_alerts_30d"],
    }
    if not criteria_results["critical_alerts_30d"]["passed"]:
        blocking.append(f"Critical alerts (30d): {critical_alerts_actual} > {GATE_CRITERIA['max_critical_alerts_30d']} allowed")

    # 8. Check dynamic exit enabled
    dynamic_exit_actual = await _check_setting("hard_stop_atr_mult")
    criteria_results["dynamic_exit_enabled"] = {
        "required": GATE_CRITERIA["dynamic_exit_enabled"],
        "actual": dynamic_exit_actual is not None,
        "passed": dynamic_exit_actual is not None,
    }
    if not criteria_results["dynamic_exit_enabled"]["passed"]:
        blocking.append("Dynamic exit not configured (hard_stop_atr_mult setting missing)")

    # 9. Check ATR sizing enabled
    atr_sizing_actual = await _check_setting("use_atr_sizing")
    criteria_results["atr_sizing_enabled"] = {
        "required": GATE_CRITERIA["atr_sizing_enabled"],
        "actual": atr_sizing_actual == "true" if atr_sizing_actual else False,
        "passed": atr_sizing_actual == "true" if atr_sizing_actual else False,
    }
    if not criteria_results["atr_sizing_enabled"]["passed"]:
        blocking.append("ATR sizing not enabled (use_atr_sizing=false)")

    # Calculate overall score
    total_criteria = len(criteria_results)
    passed_criteria = sum(1 for c in criteria_results.values() if c["passed"])
    score = round((passed_criteria / total_criteria) * 100, 2)

    # All criteria must pass for readiness
    ready = len(blocking) == 0

    # Staged rollout plan
    staged_plan = {
        "stage1": {
            "capital_pct": 1,
            "weeks": 4,
            "gate": "Sharpe≥0.5",
        },
        "stage2": {
            "capital_pct": 3,
            "weeks": 4,
            "gate": "Sharpe≥0.8",
        },
        "stage3": {
            "capital_pct": 5,
            "weeks": 4,
            "gate": "monthly alpha>0",
        },
    }

    return {
        "ready": ready,
        "score": score,
        "criteria": criteria_results,
        "blocking": blocking,
        "staged_plan": staged_plan,
    }


async def _get_paper_trading_weeks() -> float:
    """Calculate number of weeks of paper trading data available."""
    try:
        row = await fetch_one(
            """
            SELECT
                MIN(snapshot_date) as first_date,
                MAX(snapshot_date) as last_date,
                COUNT(*) as total_days
            FROM daily_snapshot
            """
        )
        if row and row["first_date"] and row["last_date"]:
            days = (row["last_date"] - row["first_date"]).days
            return round(days / 7, 1)
        return 0.0
    except Exception as e:
        logger.error("Error calculating paper trading weeks: %s", e)
        return 0.0


async def _calculate_sharpe_ratio() -> Optional[float]:
    """Calculate annualized Sharpe ratio from daily returns."""
    try:
        rows = await fetch_all(
            """
            SELECT daily_return_pct
            FROM daily_snapshot
            WHERE daily_return_pct IS NOT NULL
            ORDER BY snapshot_date DESC
            LIMIT 252
            """
        )
        if not rows or len(rows) < 20:
            return None

        returns = [float(row["daily_return_pct"]) for row in rows]

        # Calculate mean and std dev
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        if std_dev == 0:
            return None

        # Annualize (assuming 252 trading days)
        sharpe = (mean_return / std_dev) * (252 ** 0.5)
        return sharpe

    except Exception as e:
        logger.error("Error calculating Sharpe ratio: %s", e)
        return None


async def _calculate_max_drawdown() -> Optional[float]:
    """Calculate maximum drawdown percentage."""
    try:
        rows = await fetch_all(
            """
            SELECT total_value
            FROM daily_snapshot
            ORDER BY snapshot_date ASC
            """
        )
        if not rows or len(rows) < 2:
            return None

        values = [float(row["total_value"]) for row in rows]
        peak = values[0]
        max_dd = 0.0

        for value in values:
            if value > peak:
                peak = value
            dd = ((value - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd

        return max_dd

    except Exception as e:
        logger.error("Error calculating max drawdown: %s", e)
        return None


async def _calculate_win_rate() -> Optional[float]:
    """Calculate win rate percentage from closed trades."""
    try:
        row = await fetch_one(
            """
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl > 0) as winning_trades
            FROM trades
            WHERE pnl IS NOT NULL
            """
        )
        if row and row["total_trades"] and row["total_trades"] > 0:
            win_rate = (row["winning_trades"] / row["total_trades"]) * 100
            return win_rate
        return None
    except Exception as e:
        logger.error("Error calculating win rate: %s", e)
        return None


async def _calculate_profit_factor() -> Optional[float]:
    """Calculate profit factor (gross profit / gross loss)."""
    try:
        row = await fetch_one(
            """
            SELECT
                COALESCE(SUM(pnl) FILTER (WHERE pnl > 0), 0) as gross_profit,
                COALESCE(ABS(SUM(pnl)) FILTER (WHERE pnl < 0), 0) as gross_loss
            FROM trades
            WHERE pnl IS NOT NULL
            """
        )
        if row and row["gross_loss"] and float(row["gross_loss"]) > 0:
            profit_factor = float(row["gross_profit"]) / float(row["gross_loss"])
            return profit_factor
        return None
    except Exception as e:
        logger.error("Error calculating profit factor: %s", e)
        return None


async def _count_total_trades() -> int:
    """Count total number of trades."""
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM trades
            """
        )
        return row["count"] if row else 0
    except Exception as e:
        logger.error("Error counting trades: %s", e)
        return 0


async def _count_critical_alerts() -> int:
    """Count critical alerts in the last 30 days."""
    try:
        row = await fetch_one(
            """
            SELECT COUNT(*) as count
            FROM system_alerts
            WHERE severity = 'CRITICAL'
            AND created_at > NOW() - INTERVAL '30 days'
            """
        )
        return row["count"] if row else 0
    except Exception as e:
        logger.error("Error counting critical alerts: %s", e)
        return 0


async def _check_setting(key: str) -> Optional[str]:
    """Check if a setting exists and return its value."""
    try:
        row = await fetch_one(
            """
            SELECT value
            FROM settings
            WHERE key = $1
            """,
            key
        )
        return row["value"] if row else None
    except Exception as e:
        logger.error("Error checking setting %s: %s", key, e)
        return None
