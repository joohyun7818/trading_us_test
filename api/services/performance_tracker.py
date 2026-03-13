# 시그널 성과 추적, 일별 스냅샷, 주간 리포트 생성
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import yfinance as yf

from api.core.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)


# ================================================================
# 1. 시그널 성과 추적
# ================================================================

async def register_signal_for_tracking(signal_id: int) -> bool:
    """새 시그널을 성과 추적 대상으로 등록한다."""
    signal = await fetch_one(
        """
        SELECT id, stock_symbol, signal_type, final_score, created_at
        FROM signals WHERE id = $1
        """,
        signal_id,
    )
    if not signal:
        return False

    # 시그널 시점 가격 조회
    stock = await fetch_one(
        "SELECT current_price FROM stocks WHERE symbol = $1",
        signal["stock_symbol"],
    )
    price = float(stock["current_price"]) if stock and stock["current_price"] else None
    if not price:
        logger.warning("No price for %s, skip tracking", signal["stock_symbol"])
        return False

    # 중복 방지
    existing = await fetch_one(
        "SELECT id FROM signal_performance WHERE signal_id = $1", signal_id,
    )
    if existing:
        return False

    await execute(
        """
        INSERT INTO signal_performance
            (signal_id, stock_symbol, signal_type, final_score,
             signal_date, price_at_signal, status)
        VALUES ($1, $2, $3, $4, $5, $6, 'pending')
        """,
        signal_id,
        signal["stock_symbol"],
        signal["signal_type"],
        float(signal["final_score"]),
        signal["created_at"].date() if hasattr(signal["created_at"], "date") else date.today(),
        price,
    )
    return True


async def register_recent_signals() -> int:
    """최근 24시간 시그널 중 미등록 건을 일괄 등록한다."""
    signals = await fetch_all(
        """
        SELECT s.id FROM signals s
        LEFT JOIN signal_performance sp ON sp.signal_id = s.id
        WHERE s.created_at > NOW() - INTERVAL '24 hours'
          AND sp.id IS NULL
          AND s.signal_type IN ('BUY', 'SELL')
        """
    )
    registered = 0
    for sig in signals:
        if await register_signal_for_tracking(sig["id"]):
            registered += 1
    logger.info("Registered %d signals for tracking", registered)
    return registered


async def update_signal_performance() -> dict:
    """pending/partial 상태의 시그널 성과를 업데이트한다."""
    pending = await fetch_all(
        """
        SELECT id, stock_symbol, signal_type, signal_date, price_at_signal
        FROM signal_performance
        WHERE status IN ('pending', 'partial')
        ORDER BY signal_date
        """
    )

    if not pending:
        return {"updated": 0}

    updated = 0
    today = date.today()

    for record in pending:
        symbol = record["stock_symbol"]
        signal_date = record["signal_date"]
        price_at_signal = float(record["price_at_signal"])
        signal_type = record["signal_type"]
        days_elapsed = (today - signal_date).days

        if days_elapsed < 1:
            continue

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(
                start=signal_date.isoformat(),
                end=(today + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
            if hist.empty:
                continue

            closes = hist["Close"]
            trading_days = len(closes)

            # 각 기간별 가격/수익률 계산
            updates = {}
            for period_days, col_price, col_return, col_hit in [
                (1, "price_1d", "return_1d", "hit_1d"),
                (5, "price_5d", "return_5d", "hit_5d"),
                (10, "price_10d", "return_10d", "hit_10d"),
                (20, "price_20d", "return_20d", "hit_20d"),
            ]:
                if trading_days > period_days:
                    price = float(closes.iloc[period_days])
                    ret = round(((price - price_at_signal) / price_at_signal) * 100, 4)
                    # BUY는 상승이면 적중, SELL은 하락이면 적중
                    if signal_type == "BUY":
                        hit = ret > 0
                    elif signal_type == "SELL":
                        hit = ret < 0
                    else:
                        hit = None
                    updates[col_price] = price
                    updates[col_return] = ret
                    updates[col_hit] = hit

            # 5일 이내 최대 유리/불리
            max_fav = None
            max_adv = None
            window = min(5, trading_days - 1)
            if window > 0:
                returns_series = [
                    ((float(closes.iloc[i]) - price_at_signal) / price_at_signal) * 100
                    for i in range(1, window + 1)
                ]
                if signal_type == "BUY":
                    max_fav = round(max(returns_series), 4)
                    max_adv = round(min(returns_series), 4)
                elif signal_type == "SELL":
                    max_fav = round(-max(returns_series), 4)  # SELL은 하락이 유리
                    max_adv = round(-min(returns_series), 4)

            # 상태 결정
            if "return_20d" in updates:
                status = "completed"
            elif any(k in updates for k in ["return_1d", "return_5d", "return_10d"]):
                status = "partial"
            else:
                status = "pending"

            # UPDATE 실행
            set_parts = ["status = $1", "last_updated = NOW()"]
            params = [status]
            idx = 2

            for col, val in updates.items():
                set_parts.append(f"{col} = ${idx}")
                params.append(val)
                idx += 1

            if max_fav is not None:
                set_parts.append(f"max_favorable = ${idx}")
                params.append(max_fav)
                idx += 1
            if max_adv is not None:
                set_parts.append(f"max_adverse = ${idx}")
                params.append(max_adv)
                idx += 1

            params.append(record["id"])
            set_clause = ", ".join(set_parts)

            await execute(
                f"UPDATE signal_performance SET {set_clause} WHERE id = ${idx}",
                *params,
            )
            updated += 1

        except Exception as e:
            logger.error("Performance update failed for %s: %s", symbol, e)

    logger.info("Updated %d signal performances", updated)
    return {"updated": updated, "total_pending": len(pending)}


# ================================================================
# 2. 일별 스냅샷
# ================================================================

async def create_daily_snapshot() -> dict:
    """오늘의 포트폴리오 스냅샷을 생성한다."""
    today = date.today()

    # 중복 방지
    existing = await fetch_one(
        "SELECT id FROM daily_snapshot WHERE snapshot_date = $1", today,
    )
    if existing:
        logger.info("Snapshot already exists for %s", today)
        return {"status": "already_exists"}

    # 포트폴리오 가치
    positions = await fetch_all("SELECT stock_symbol, qty, current_price FROM portfolio")
    positions_value = sum(
        float(p["qty"]) * float(p["current_price"])
        for p in positions if p["current_price"]
    )

    # 현금 (Alpaca 또는 설정에서)
    total_cap_row = await fetch_one("SELECT value FROM settings WHERE key = 'total_capital'")
    total_capital = float(total_cap_row["value"]) if total_cap_row else 100000.0
    cash_balance = total_capital - positions_value
    total_value = total_capital  # 초기에는 총 자본 = 현금 + 포지션

    try:
        from api.services.alpaca_client import get_account
        account = await get_account()
        if account.get("status") == "ok":
            total_value = float(account.get("portfolio_value", total_capital))
            cash_balance = float(account.get("cash", cash_balance))
            positions_value = total_value - cash_balance
    except Exception:
        total_value = cash_balance + positions_value

    # 전일 스냅샷과 비교
    yesterday = await fetch_one(
        "SELECT total_value, cumulative_pnl FROM daily_snapshot ORDER BY snapshot_date DESC LIMIT 1"
    )
    if yesterday:
        prev_value = float(yesterday["total_value"])
        daily_pnl = round(total_value - prev_value, 4)
        daily_return_pct = round((daily_pnl / prev_value) * 100, 4) if prev_value > 0 else 0
        cumulative_pnl = round(float(yesterday["cumulative_pnl"] or 0) + daily_pnl, 4)
    else:
        daily_pnl = 0
        daily_return_pct = 0
        cumulative_pnl = 0

    # 첫 스냅샷 기준 누적 수익률
    first = await fetch_one(
        "SELECT total_value FROM daily_snapshot ORDER BY snapshot_date ASC LIMIT 1"
    )
    base_value = float(first["total_value"]) if first else total_value
    cumulative_return = round(((total_value - base_value) / base_value) * 100, 4) if base_value > 0 else 0

    # 당일 시그널 통계
    signals_today = await fetch_all(
        """
        SELECT signal_type, COUNT(*) as cnt FROM signals
        WHERE created_at::date = $1
        GROUP BY signal_type
        """,
        today,
    )
    signals_map = {r["signal_type"]: r["cnt"] for r in signals_today}
    signals_buy = signals_map.get("BUY", 0)
    signals_sell = signals_map.get("SELL", 0)
    signals_hold = signals_map.get("HOLD", 0)
    signals_generated = signals_buy + signals_sell + signals_hold

    # 당일 거래 통계
    trades_today = await fetch_all(
        """
        SELECT side, COUNT(*) as cnt FROM trades
        WHERE created_at::date = $1
        GROUP BY side
        """,
        today,
    )
    trades_map = {r["side"]: r["cnt"] for r in trades_today}

    # SPY 벤치마크
    spy_price = None
    spy_daily_return = None
    spy_cumulative = None
    try:
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="5d", auto_adjust=True)
        if not spy_hist.empty and len(spy_hist) >= 2:
            spy_price = round(float(spy_hist["Close"].iloc[-1]), 4)
            spy_prev = float(spy_hist["Close"].iloc[-2])
            spy_daily_return = round(((spy_price - spy_prev) / spy_prev) * 100, 4)

        # SPY 누적 수익률 (첫 스냅샷 날짜 기준)
        first_snap = await fetch_one(
            "SELECT snapshot_date, spy_price FROM daily_snapshot ORDER BY snapshot_date ASC LIMIT 1"
        )
        if first_snap and first_snap["spy_price"]:
            spy_base = float(first_snap["spy_price"])
            spy_cumulative = round(((spy_price - spy_base) / spy_base) * 100, 4) if spy_base > 0 else 0
    except Exception as e:
        logger.error("SPY data fetch failed: %s", e)

    # 매크로
    macro = await fetch_one(
        "SELECT regime, regime_score FROM macro_regime ORDER BY created_at DESC LIMIT 1"
    )

    await execute(
        """
        INSERT INTO daily_snapshot
            (snapshot_date, total_value, cash_balance, positions_value,
             position_count, daily_pnl, daily_return_pct,
             cumulative_pnl, cumulative_return,
             buy_count, sell_count,
             signals_generated, signals_buy, signals_sell, signals_hold,
             spy_price, spy_daily_return, spy_cumulative,
             macro_regime, macro_score)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
        """,
        today, round(total_value, 4), round(cash_balance, 4), round(positions_value, 4),
        len(positions), daily_pnl, daily_return_pct,
        cumulative_pnl, cumulative_return,
        trades_map.get("buy", 0), trades_map.get("sell", 0),
        signals_generated, signals_buy, signals_sell, signals_hold,
        spy_price, spy_daily_return, spy_cumulative,
        macro["regime"] if macro else "UNKNOWN",
        float(macro["regime_score"]) if macro else 0.5,
    )

    logger.info(
        "Daily snapshot: value=%.2f pnl=%.2f return=%.2f%% spy=%.2f%%",
        total_value, daily_pnl, daily_return_pct, spy_daily_return or 0,
    )

    return {
        "status": "ok",
        "snapshot_date": today.isoformat(),
        "total_value": total_value,
        "daily_pnl": daily_pnl,
        "daily_return_pct": daily_return_pct,
        "cumulative_return": cumulative_return,
        "spy_daily_return": spy_daily_return,
        "spy_cumulative": spy_cumulative,
    }


# ================================================================
# 3. 주간 리포트
# ================================================================

async def generate_weekly_report() -> dict:
    """주간 모델 성능 리포트를 생성한다."""
    today = date.today()
    week_end = today
    week_start = today - timedelta(days=7)

    # 해당 주 시그널 성과 (5d 기준)
    performances = await fetch_all(
        """
        SELECT signal_type, final_score, return_5d, hit_5d
        FROM signal_performance
        WHERE signal_date BETWEEN $1 AND $2
          AND return_5d IS NOT NULL
        """,
        week_start, week_end,
    )

    total = len(performances)
    if total == 0:
        return {"status": "no_data", "message": "No completed signals this week"}

    buy_signals = [p for p in performances if p["signal_type"] == "BUY"]
    sell_signals = [p for p in performances if p["signal_type"] == "SELL"]

    # 적중률
    hits = [p for p in performances if p["hit_5d"] is True]
    rule_accuracy = round(len(hits) / total, 4) if total > 0 else 0

    buy_hits = [p for p in buy_signals if p["hit_5d"] is True]
    rule_precision_buy = round(len(buy_hits) / len(buy_signals), 4) if buy_signals else None

    sell_hits = [p for p in sell_signals if p["hit_5d"] is True]
    rule_precision_sell = round(len(sell_hits) / len(sell_signals), 4) if sell_signals else None

    # 평균 수익률
    returns = [float(p["return_5d"]) for p in performances if p["return_5d"] is not None]
    avg_return = round(np.mean(returns), 4) if returns else 0

    # 포트폴리오 주간 수익률
    snapshots = await fetch_all(
        """
        SELECT snapshot_date, total_value, spy_price
        FROM daily_snapshot
        WHERE snapshot_date BETWEEN $1 AND $2
        ORDER BY snapshot_date
        """,
        week_start, week_end,
    )

    portfolio_return = None
    spy_return = None
    alpha = None
    max_drawdown = None

    if len(snapshots) >= 2:
        first_val = float(snapshots[0]["total_value"])
        last_val = float(snapshots[-1]["total_value"])
        portfolio_return = round(((last_val - first_val) / first_val) * 100, 4) if first_val > 0 else 0

        first_spy = float(snapshots[0]["spy_price"]) if snapshots[0]["spy_price"] else None
        last_spy = float(snapshots[-1]["spy_price"]) if snapshots[-1]["spy_price"] else None
        if first_spy and last_spy and first_spy > 0:
            spy_return = round(((last_spy - first_spy) / first_spy) * 100, 4)
            alpha = round(portfolio_return - spy_return, 4)

        # 주간 최대 낙폭
        values = [float(s["total_value"]) for s in snapshots]
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak:
                peak = v
            dd = ((v - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd
        max_drawdown = round(max_dd, 4)

    # 승률 (거래 기준)
    trades = await fetch_all(
        """
        SELECT pnl FROM trades
        WHERE created_at::date BETWEEN $1 AND $2
          AND pnl IS NOT NULL
        """,
        week_start, week_end,
    )
    win_trades = [t for t in trades if float(t["pnl"]) > 0]
    win_rate = round(len(win_trades) / len(trades), 4) if trades else None

    # 샤프 비율 (일별 수익률 기준)
    sharpe = None
    if len(snapshots) >= 3:
        daily_returns = []
        for i in range(1, len(snapshots)):
            prev = float(snapshots[i - 1]["total_value"])
            curr = float(snapshots[i]["total_value"])
            if prev > 0:
                daily_returns.append((curr - prev) / prev)
        if daily_returns and np.std(daily_returns) > 0:
            sharpe = round((np.mean(daily_returns) / np.std(daily_returns)) * (252 ** 0.5), 4)

    # 시그널 통계
    all_signals = await fetch_all(
        """
        SELECT signal_type, COUNT(*) as cnt FROM signals
        WHERE created_at::date BETWEEN $1 AND $2
        GROUP BY signal_type
        """,
        week_start, week_end,
    )
    signal_counts = {r["signal_type"]: r["cnt"] for r in all_signals}

    import json
    report_data = {
        "buy_details": [
            {"symbol": p["stock_symbol"], "score": float(p["final_score"]), "return_5d": float(p["return_5d"])}
            for p in buy_signals if p["return_5d"] is not None
        ] if buy_signals else [],
        "sell_details": [
            {"symbol": p["stock_symbol"], "score": float(p["final_score"]), "return_5d": float(p["return_5d"])}
            for p in sell_signals if p["return_5d"] is not None
        ] if sell_signals else [],
    }

    await execute(
        """
        INSERT INTO weekly_report
            (week_start, week_end,
             total_signals, buy_signals, sell_signals, hold_signals,
             rule_accuracy_5d, rule_precision_buy, rule_precision_sell, rule_avg_return_5d,
             portfolio_return, spy_return, alpha,
             max_drawdown, sharpe_ratio, win_rate,
             report_data)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
        """,
        week_start, week_end,
        sum(signal_counts.values()),
        signal_counts.get("BUY", 0),
        signal_counts.get("SELL", 0),
        signal_counts.get("HOLD", 0),
        rule_accuracy, rule_precision_buy, rule_precision_sell, avg_return,
        portfolio_return, spy_return, alpha,
        max_drawdown, sharpe, win_rate,
        json.dumps(report_data),
    )

    logger.info(
        "Weekly report: acc=%.2f%% alpha=%.2f%% sharpe=%s",
        rule_accuracy * 100 if rule_accuracy else 0,
        alpha or 0,
        sharpe,
    )

    return {
        "status": "ok",
        "week": f"{week_start} ~ {week_end}",
        "rule_accuracy_5d": rule_accuracy,
        "rule_precision_buy": rule_precision_buy,
        "rule_precision_sell": rule_precision_sell,
        "avg_return_5d": avg_return,
        "portfolio_return": portfolio_return,
        "spy_return": spy_return,
        "alpha": alpha,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "total_signals": total,
    }


# ================================================================
# 4. 조회 헬퍼
# ================================================================

async def get_signal_performance_summary(days: int = 30) -> dict:
    """최근 N일 시그널 성과 요약."""
    rows = await fetch_all(
        """
        SELECT signal_type,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE hit_5d = TRUE) as hits_5d,
               ROUND(AVG(return_1d)::numeric, 4) as avg_return_1d,
               ROUND(AVG(return_5d)::numeric, 4) as avg_return_5d,
               ROUND(AVG(return_10d)::numeric, 4) as avg_return_10d,
               ROUND(AVG(max_favorable)::numeric, 4) as avg_max_favorable,
               ROUND(AVG(max_adverse)::numeric, 4) as avg_max_adverse
        FROM signal_performance
        WHERE signal_date > CURRENT_DATE - $1
          AND status IN ('partial', 'completed')
        GROUP BY signal_type
        """,
        days,
    )
    return {
        "period_days": days,
        "by_signal_type": rows,
    }


async def get_daily_snapshots(limit: int = 30) -> list[dict]:
    """일별 스냅샷 이력을 반환한다."""
    return await fetch_all(
        """
        SELECT snapshot_date, total_value, daily_pnl, daily_return_pct,
               cumulative_return, spy_daily_return, spy_cumulative,
               position_count, signals_generated, macro_regime
        FROM daily_snapshot
        ORDER BY snapshot_date DESC
        LIMIT $1
        """,
        limit,
    )


async def get_weekly_reports(limit: int = 12) -> list[dict]:
    """주간 리포트 이력을 반환한다."""
    return await fetch_all(
        """
        SELECT week_start, week_end,
               total_signals, buy_signals, sell_signals,
               rule_accuracy_5d, rule_precision_buy, rule_avg_return_5d,
               portfolio_return, spy_return, alpha,
               sharpe_ratio, win_rate, report_data
        FROM weekly_report
        ORDER BY week_start DESC
        LIMIT $1
        """,
        limit,
    )


async def get_score_vs_return(days: int = 30) -> list[dict]:
    """final_score vs 실제 수익률 산점도 데이터."""
    return await fetch_all(
        """
        SELECT stock_symbol, signal_type, final_score,
               return_1d, return_5d, return_10d, hit_5d,
               signal_date
        FROM signal_performance
        WHERE signal_date > CURRENT_DATE - $1
          AND return_5d IS NOT NULL
        ORDER BY signal_date DESC
        """,
        days,
    )
