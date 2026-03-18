import logging
from datetime import date
from typing import Optional
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel

from api.core.database import fetch_all
from api.services.numeric_analyzer import (
    _score_52w_position,
    _score_atr,
    _score_bollinger,
    _score_macd,
    _score_rsi,
    _score_sma,
    _score_volume,
)

logger = logging.getLogger(__name__)


class BacktestConfig(BaseModel):
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    max_order_amount: float = 1_000.0
    max_positions: int = 20
    stop_loss_pct: float = -8.0
    take_profit_pct: float = 15.0
    screening_upper: float = 60.0
    screening_lower: float = 35.0
    buy_threshold: float = 70.0
    sell_threshold: float = 30.0
    w_numeric: float = 0.50
    w_text: float = 0.35
    w_macro: float = 0.15
    commission_pct: float = 0.0
    slippage_bps: float = 5.0
    text_score_default: float = 50.0
    macro_score_default: float = 50.0
    exit_strategy: str = "fixed"
    hard_stop_atr_mult: float = 2.5
    trailing_stop_atr_mult: float = 2.0
    max_holding_days: int = 20
    partial_exit_atr_mult: float = 3.0
    use_atr_sizing: bool = False
    risk_per_trade_pct: float = 1.0
    max_single_order_pct: float = 5.0
    sector_cap_pct: float = 30.0


class BacktestResult(BaseModel):
    daily_equity: list[tuple[date, float]]
    trades: list[dict]
    signals: list[dict]


# NOTE: Phase 1 임시 저장소(프로세스 메모리). 재시작 시 결과는 유지되지 않는다.
_BACKTEST_RESULTS: dict[str, dict] = {}


def _calc_numeric_score(row: dict) -> float:
    price = float(row["close"]) if row.get("close") is not None else None
    rsi = float(row["rsi_14"]) if row.get("rsi_14") is not None else None
    sma_20 = float(row["sma_20"]) if row.get("sma_20") is not None else None
    sma_60 = float(row["sma_60"]) if row.get("sma_60") is not None else None
    macd_val = float(row["macd"]) if row.get("macd") is not None else None
    macd_sig = float(row["macd_signal"]) if row.get("macd_signal") is not None else None
    macd_hist = float(row["macd_histogram"]) if row.get("macd_histogram") is not None else None
    b_pct = float(row["bollinger_pct_b"]) if row.get("bollinger_pct_b") is not None else None
    vol_ratio = float(row["volume_ratio"]) if row.get("volume_ratio") is not None else None
    high_52w = float(row["high_52w"]) if row.get("high_52w") is not None else None
    low_52w = float(row["low_52w"]) if row.get("low_52w") is not None else None
    atr = float(row["atr_14"]) if row.get("atr_14") is not None else None

    rsi_score = _score_rsi(rsi)
    macd_score = _score_macd(macd_val, macd_sig, macd_hist)
    sma_score = _score_sma(price, sma_20, sma_60)
    bollinger_score = _score_bollinger(b_pct)
    volume_score = _score_volume(vol_ratio)
    week52_score = _score_52w_position(price, high_52w, low_52w)
    atr_score = _score_atr(atr, price)

    return round(
        rsi_score * 0.25
        + macd_score * 0.20
        + sma_score * 0.15
        + bollinger_score * 0.15
        + volume_score * 0.10
        + week52_score * 0.10
        + atr_score * 0.05,
        4,
    )


def _apply_adjustments(score: float, rsi_14: Optional[float]) -> tuple[float, list[dict]]:
    adjusted = score
    adjustments: list[dict] = []

    if rsi_14 is not None and rsi_14 >= 75:
        adjusted -= 10
        adjustments.append({"type": "overbought_rsi", "delta": -10, "rsi": round(rsi_14, 4)})
    elif rsi_14 is not None and rsi_14 <= 25:
        adjusted += 10
        adjustments.append({"type": "oversold_rsi", "delta": +10, "rsi": round(rsi_14, 4)})

    return round(max(0.0, min(100.0, adjusted)), 4), adjustments


def _apply_slippage(open_px: float, slippage_bps: float) -> float:
    return open_px * (1 + slippage_bps / 10000.0)


def _evaluate_dynamic_exit_inline(
    *,
    entry_price: float,
    current_price: float,
    highest_price_since_entry: float,
    days_held: int,
    entry_atr: float,
    quantity: float,
    hard_stop_mult: float,
    trail_mult: float,
    max_holding_days: int,
    partial_mult: float,
) -> dict:
    """백테스트 전용 동적 청산 규칙(동기/순수 함수)을 평가한다."""
    safe_atr = entry_atr if entry_atr > 0 else entry_price * 0.02
    full_exit_qty = max(1, int(quantity))
    partial_exit_qty = max(1, int(quantity * 0.5))

    hard_stop_price = entry_price - (safe_atr * hard_stop_mult)
    if current_price <= hard_stop_price:
        return {"should_exit": True, "exit_reason": "atr_hard_stop", "exit_quantity": full_exit_qty}

    if highest_price_since_entry > (entry_price * 1.01):
        trailing_stop_price = highest_price_since_entry - (safe_atr * trail_mult)
        if current_price <= trailing_stop_price:
            return {"should_exit": True, "exit_reason": "trailing_stop", "exit_quantity": full_exit_qty}

    if days_held >= max_holding_days:
        return {"should_exit": True, "exit_reason": "time_limit", "exit_quantity": full_exit_qty}

    atr_multiple = (current_price - entry_price) / safe_atr if safe_atr > 0 else 0.0
    if atr_multiple >= partial_mult and quantity > 1:
        return {"should_exit": True, "exit_reason": "partial_take_profit", "exit_quantity": partial_exit_qty}

    return {"should_exit": False, "exit_reason": "hold", "exit_quantity": 0}


def _calculate_atr_position_size(
    *,
    final_score: float,
    atr_14: float,
    price: float,
    account_equity: float,
    positions: dict,
    config: BacktestConfig,
) -> float:
    """백테스트 전용 ATR 기반 포지션 사이징 계산."""
    # ATR이 없으면 가격의 2%로 추정
    if not atr_14 or atr_14 <= 0:
        atr_14 = price * 0.02

    # 기본 포지션 사이징 계산
    risk_amount = account_equity * (config.risk_per_trade_pct / 100.0)
    dollar_risk = atr_14 * config.hard_stop_atr_mult
    base_shares = risk_amount / dollar_risk if dollar_risk > 0 else 0
    base_order_amount = base_shares * price

    # signal_score 스케일링
    if final_score < 55:
        score_multiplier = 0.0
    elif 55 <= final_score < 65:
        score_multiplier = 0.7
    elif 65 <= final_score < 80:
        score_multiplier = 1.0
    elif 80 <= final_score < 90:
        score_multiplier = 1.2
    else:  # final_score >= 90
        score_multiplier = 1.5

    scaled_order_amount = base_order_amount * score_multiplier

    # 최대 단일 주문 제약
    max_single_order = account_equity * (config.max_single_order_pct / 100.0)
    scaled_order_amount = min(scaled_order_amount, max_single_order)

    # 최소 주문 금액 ($200)
    min_order_amount = 200.0
    if scaled_order_amount < min_order_amount:
        return 0.0

    return scaled_order_amount


def _apply_sector_cap_in_backtest(
    *,
    symbol: str,
    symbol_sector_id,
    positions: dict,
    close_prices: dict[str, float],
    account_equity: float,
    requested_notional: float,
    config: BacktestConfig,
) -> float:
    """백테스트 섹터 상한(옵션)을 적용한다. 섹터 정보가 없으면 원금액을 반환한다."""
    if symbol_sector_id is None or pd.isna(symbol_sector_id):
        return requested_notional

    sector_cap = account_equity * (config.sector_cap_pct / 100.0)
    sector_exposure = 0.0
    for held_symbol, held_pos in positions.items():
        held_sector = held_pos.get("sector_id")
        if held_sector is None or pd.isna(held_sector) or held_sector != symbol_sector_id:
            continue
        held_close = close_prices.get(held_symbol, 0.0)
        if held_close <= 0:
            continue
        sector_exposure += float(held_pos["qty"]) * held_close

    remaining = sector_cap - sector_exposure
    if remaining <= 0:
        return 0.0
    return min(requested_notional, remaining)



async def run_backtest(config: BacktestConfig) -> dict:
    if config.start_date > config.end_date:
        raise ValueError("start_date must be <= end_date")

    rows = await fetch_all(
        """
        SELECT
            symbol, trade_date, open, high, low, close, rsi_14, sma_20, sma_60,
            macd, macd_signal, macd_histogram, bollinger_pct_b, volume_ratio, atr_14
        FROM stock_daily
        WHERE trade_date BETWEEN $1 AND $2
        ORDER BY trade_date, symbol
        """,
        config.start_date,
        config.end_date,
    )
    if not rows:
        result = BacktestResult(daily_equity=[], trades=[], signals=[])
        backtest_id = str(uuid4())
        payload = {"backtest_id": backtest_id, "config": config.model_dump(), "result": result.model_dump()}
        _BACKTEST_RESULTS[backtest_id] = payload
        return payload

    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["high_52w"] = df.groupby("symbol")["high"].transform(
        lambda s: pd.to_numeric(s, errors="coerce").rolling(window=252, min_periods=1).max()
    )
    df["low_52w"] = df.groupby("symbol")["low"].transform(
        lambda s: pd.to_numeric(s, errors="coerce").rolling(window=252, min_periods=1).min()
    )
    numeric_scores = [_calc_numeric_score(row) for row in df.to_dict("records")]
    df["numeric_score"] = numeric_scores

    trade_days = sorted(df["trade_date"].dt.date.unique())
    next_day_map = dict(zip(trade_days[:-1], trade_days[1:]))
    by_day = {day: group.copy() for day, group in df.groupby(df["trade_date"].dt.date)}

    cash = config.initial_capital
    positions: dict[str, dict] = {}
    pending_orders: dict[date, list[dict]] = {}

    daily_equity: list[tuple[date, float]] = []
    trades: list[dict] = []
    signals: list[dict] = []

    for idx, day in enumerate(trade_days, start=1):
        day_df = by_day[day].set_index("symbol")

        day_orders = pending_orders.pop(day, [])
        for order in day_orders:
            symbol = order["symbol"]
            if symbol not in day_df.index:
                continue
            open_px = float(day_df.at[symbol, "open"])
            if open_px <= 0:
                continue
            fill_px = _apply_slippage(open_px, config.slippage_bps)

            if order["side"] == "BUY":
                if symbol in positions:
                    continue
                qty = float(order["qty"])
                cost = qty * fill_px
                if cost > cash:
                    continue
                cash -= cost
                entry_atr_raw = day_df.at[symbol, "atr_14"] if "atr_14" in day_df.columns else None
                entry_atr = (
                    float(entry_atr_raw)
                    if entry_atr_raw is not None and pd.notna(entry_atr_raw)
                    else float(fill_px) * 0.02
                )
                positions[symbol] = {
                    "qty": qty,
                    "entry_price": fill_px,
                    "entry_date": day,
                    "highest_price": float(day_df.at[symbol, "high"]),
                    "entry_atr": entry_atr,
                    "sector_id": day_df.at[symbol, "sector_id"] if "sector_id" in day_df.columns else None,
                }
            elif order["side"] == "SELL" and symbol in positions:
                pos = positions.pop(symbol)
                qty = float(pos["qty"])
                proceeds = qty * fill_px
                cash += proceeds
                pnl = proceeds - (qty * float(pos["entry_price"]))
                ret = (pnl / (qty * float(pos["entry_price"]))) * 100 if pos["entry_price"] else 0.0
                trades.append(
                    {
                        "entry_date": pos["entry_date"],
                        "exit_date": day,
                        "symbol": symbol,
                        "side": "LONG",
                        "pnl": round(pnl, 4),
                        "return_pct": round(ret, 4),
                        "exit_reason": order.get("exit_reason", "signal_sell"),
                    }
                )

        for symbol in list(positions.keys()):
            if symbol not in day_df.index:
                continue
            pos = positions[symbol]
            qty = float(pos["qty"])
            entry_px = float(pos["entry_price"])
            low_px = float(day_df.at[symbol, "low"])
            high_px = float(day_df.at[symbol, "high"])
            close_px = float(day_df.at[symbol, "close"])
            pos["highest_price"] = max(float(pos.get("highest_price", entry_px)), high_px)

            exit_px = None
            exit_qty = qty
            exit_reason = "hold"

            if config.exit_strategy == "dynamic":
                days_held = max(0, (day - pos["entry_date"]).days)
                dynamic_result = _evaluate_dynamic_exit_inline(
                    entry_price=entry_px,
                    current_price=close_px,
                    highest_price_since_entry=float(pos.get("highest_price", high_px)),
                    days_held=days_held,
                    entry_atr=float(pos.get("entry_atr", entry_px * 0.02)),
                    quantity=qty,
                    hard_stop_mult=config.hard_stop_atr_mult,
                    trail_mult=config.trailing_stop_atr_mult,
                    max_holding_days=config.max_holding_days,
                    partial_mult=config.partial_exit_atr_mult,
                )
                if dynamic_result["should_exit"]:
                    exit_px = close_px
                    exit_qty = min(qty, float(dynamic_result["exit_quantity"]))
                    exit_reason = dynamic_result["exit_reason"]
            else:
                stop_px = entry_px * (1 + config.stop_loss_pct / 100.0)
                tp_px = entry_px * (1 + config.take_profit_pct / 100.0)
                if low_px <= stop_px:
                    exit_px = stop_px
                    exit_reason = "stop_loss"
                elif high_px >= tp_px:
                    exit_px = tp_px
                    exit_reason = "take_profit"

            if exit_px is not None and exit_qty > 0:
                proceeds = exit_qty * exit_px
                cash += proceeds
                pnl = proceeds - (exit_qty * entry_px)
                ret = (pnl / (exit_qty * entry_px)) * 100 if entry_px else 0.0
                trades.append(
                    {
                        "entry_date": pos["entry_date"],
                        "exit_date": day,
                        "symbol": symbol,
                        "side": "LONG",
                        "pnl": round(pnl, 4),
                        "return_pct": round(ret, 4),
                        "exit_reason": exit_reason,
                    }
                )
                remaining_qty = qty - exit_qty
                if remaining_qty <= 0:
                    positions.pop(symbol, None)
                else:
                    pos["qty"] = remaining_qty

        for symbol, row in day_df.iterrows():
            numeric_score = float(row["numeric_score"])
            in_middle_band = config.screening_lower < numeric_score < config.screening_upper
            if in_middle_band:
                continue

            base_score = (
                numeric_score * config.w_numeric
                + config.text_score_default * config.w_text
                + config.macro_score_default * config.w_macro
            )
            rsi_14 = float(row["rsi_14"]) if pd.notna(row["rsi_14"]) else None
            final_score, adjustments = _apply_adjustments(base_score, rsi_14)

            if final_score >= config.buy_threshold:
                signal_type = "BUY"
            elif final_score <= config.sell_threshold:
                signal_type = "SELL"
            else:
                signal_type = "HOLD"

            signals.append(
                {
                    "trade_date": day,
                    "symbol": symbol,
                    "signal_type": signal_type,
                    "numeric_score": round(numeric_score, 4),
                    "text_score": round(config.text_score_default, 4),
                    "macro_score": round(config.macro_score_default, 4),
                    "final_score": final_score,
                    "adjustments": adjustments,
                }
            )

            next_day = next_day_map.get(day)
            if not next_day:
                continue

            if signal_type == "BUY":
                if symbol in positions:
                    logger.debug("Skip BUY %s on %s: already holding", symbol, day)
                    continue
                if len(positions) >= config.max_positions:
                    logger.debug("Skip BUY %s on %s: max positions reached", symbol, day)
                    continue
                if cash <= 0:
                    logger.debug("Skip BUY %s on %s: no cash", symbol, day)
                    continue

                close_px = float(row["close"])
                if close_px <= 0:
                    continue

                # ATR 기반 포지션 사이징 또는 고정 금액
                if config.use_atr_sizing:
                    atr_14 = float(row["atr_14"]) if pd.notna(row.get("atr_14")) else None
                    close_prices = day_df["close"].astype(float).to_dict()
                    current_equity = cash + sum(
                        float(p["qty"]) * close_prices.get(s, 0.0)
                        for s, p in positions.items()
                    )
                    notional = _calculate_atr_position_size(
                        final_score=final_score,
                        atr_14=atr_14,
                        price=close_px,
                        account_equity=current_equity,
                        positions=positions,
                        config=config,
                    )
                    if notional <= 0:
                        logger.debug("Skip BUY %s on %s: ATR sizing returned 0", symbol, day)
                        continue

                    symbol_sector_id = row["sector_id"] if "sector_id" in row.index else None
                    notional = _apply_sector_cap_in_backtest(
                        symbol=symbol,
                        symbol_sector_id=symbol_sector_id,
                        positions=positions,
                        close_prices=close_prices,
                        account_equity=current_equity,
                        requested_notional=notional,
                        config=config,
                    )
                    if notional <= 0:
                        logger.debug("Skip BUY %s on %s: sector cap reached", symbol, day)
                        continue
                    notional = min(notional, cash)
                else:
                    notional = min(config.max_order_amount, cash)

                if notional <= 0:
                    continue

                pending_orders.setdefault(next_day, []).append(
                    {"side": "BUY", "symbol": symbol, "qty": notional / close_px}
                )
            elif signal_type == "SELL" and symbol in positions:
                pending_orders.setdefault(next_day, []).append(
                    {
                        "side": "SELL",
                        "symbol": symbol,
                        "qty": float(positions[symbol]["qty"]),
                        "exit_reason": "signal_sell",
                    }
                )

        close_prices = day_df["close"].astype(float).to_dict()
        holdings_value = 0.0
        for symbol, pos in positions.items():
            close_px = close_prices.get(symbol)
            if close_px is None:
                continue
            holdings_value += float(pos["qty"]) * float(close_px)
        daily_equity.append((day, round(cash + holdings_value, 4)))

        if idx % 100 == 0:
            logger.info("Backtest progress: %d/%d trading days", idx, len(trade_days))

    result = BacktestResult(daily_equity=daily_equity, trades=trades, signals=signals)
    backtest_id = str(uuid4())
    payload = {"backtest_id": backtest_id, "config": config.model_dump(), "result": result.model_dump()}
    _BACKTEST_RESULTS[backtest_id] = payload
    return payload


async def get_backtest_result(backtest_id: str) -> Optional[dict]:
    return _BACKTEST_RESULTS.get(backtest_id)
