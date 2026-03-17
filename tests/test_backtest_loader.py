from datetime import date
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi import HTTPException

from api.routers import backtest
from api.services.backtester import BacktestConfig
from api.services import historical_loader
from api.services import backtester


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


def _sample_df() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-06"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Adj Close": [100.5, 101.5, 102.5],
            "Volume": [1000000, 1100000, 900000],
        },
        index=idx,
    )


@pytest.mark.asyncio
async def test_load_history_uses_run_sync_and_executemany(monkeypatch):
    conn = type("Conn", (), {"executemany": AsyncMock()})()
    monkeypatch.setattr(historical_loader, "get_sp500_symbols", AsyncMock(return_value=["AAPL"]))
    monkeypatch.setattr(historical_loader, "fetch_all", AsyncMock(return_value=[]))
    monkeypatch.setattr(historical_loader, "get_pool", AsyncMock(return_value=_DummyPool(conn)))
    run_sync_mock = AsyncMock(return_value=_sample_df())
    monkeypatch.setattr(historical_loader, "run_sync", run_sync_mock)

    result = await historical_loader.load_history(incremental=True, years=1)

    assert result["status"] == "ok"
    assert result["processed"] == 1
    assert result["inserted"] == 3
    run_sync_mock.assert_awaited_once()
    conn.executemany.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_history_incremental_skips_existing_date(monkeypatch):
    conn = type("Conn", (), {"executemany": AsyncMock()})()
    monkeypatch.setattr(historical_loader, "get_sp500_symbols", AsyncMock(return_value=["AAPL"]))
    monkeypatch.setattr(
        historical_loader,
        "fetch_all",
        AsyncMock(return_value=[{"symbol": "AAPL", "max_date": date(2026, 1, 6)}]),
    )
    monkeypatch.setattr(historical_loader, "get_pool", AsyncMock(return_value=_DummyPool(conn)))
    monkeypatch.setattr(historical_loader, "run_sync", AsyncMock(return_value=_sample_df()))

    result = await historical_loader.load_history(incremental=True, years=1)

    assert result["inserted"] == 0
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_backtest_router_trigger_calls_loader(monkeypatch):
    loader_mock = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(backtest, "load_history", loader_mock)

    result = await backtest.trigger_load_history(incremental=False)

    assert result["status"] == "ok"
    loader_mock.assert_awaited_once_with(incremental=False)


@pytest.mark.asyncio
async def test_backtest_router_status_calls_service(monkeypatch):
    status_mock = AsyncMock(return_value={"total_symbols": 500, "missing_count": 0})
    monkeypatch.setattr(backtest, "get_history_status", status_mock)

    result = await backtest.history_status()

    assert result["total_symbols"] == 500
    status_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_backtester_runs_and_stores_result(monkeypatch):
    rows = [
        {
            "symbol": "AAPL",
            "trade_date": date(2026, 1, 2),
            "open": 100.0,
            "high": 103.0,
            "low": 99.0,
            "close": 102.0,
            "rsi_14": 20.0,
            "sma_20": 95.0,
            "sma_60": 90.0,
            "macd": 1.2,
            "macd_signal": 0.5,
            "macd_histogram": 0.7,
            "bollinger_pct_b": 0.1,
            "volume_ratio": 2.2,
            "atr_14": 2.0,
        },
        {
            "symbol": "AAPL",
            "trade_date": date(2026, 1, 3),
            "open": 101.0,
            "high": 102.0,
            "low": 90.0,
            "close": 92.0,
            "rsi_14": 35.0,
            "sma_20": 96.0,
            "sma_60": 91.0,
            "macd": 0.6,
            "macd_signal": 0.5,
            "macd_histogram": 0.1,
            "bollinger_pct_b": 0.4,
            "volume_ratio": 1.1,
            "atr_14": 2.5,
        },
    ]
    monkeypatch.setattr(backtester, "fetch_all", AsyncMock(return_value=rows))

    config = BacktestConfig(start_date=date(2026, 1, 1), end_date=date(2026, 1, 5), initial_capital=10_000)
    payload = await backtester.run_backtest(config)

    assert payload["backtest_id"]
    assert payload["result"]["daily_equity"]
    assert payload["result"]["signals"]
    assert payload["result"]["trades"]

    saved = await backtester.get_backtest_result(payload["backtest_id"])
    assert saved == payload


@pytest.mark.asyncio
async def test_backtest_router_run_and_get_results(monkeypatch):
    run_mock = AsyncMock(return_value={"backtest_id": "bt-1", "result": {"daily_equity": []}})
    get_mock = AsyncMock(return_value={"backtest_id": "bt-1", "result": {"daily_equity": []}})
    monkeypatch.setattr(backtest, "run_backtest", run_mock)
    monkeypatch.setattr(backtest, "get_backtest_result", get_mock)

    config = BacktestConfig(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    run_result = await backtest.run_backtest_api(config)
    get_result = await backtest.get_backtest_results("bt-1")

    assert run_result["backtest_id"] == "bt-1"
    assert get_result["backtest_id"] == "bt-1"
    run_mock.assert_awaited_once()
    get_mock.assert_awaited_once_with("bt-1")


@pytest.mark.asyncio
async def test_backtest_router_errors(monkeypatch):
    monkeypatch.setattr(backtest, "run_backtest", AsyncMock(side_effect=ValueError("bad date range")))
    monkeypatch.setattr(backtest, "get_backtest_result", AsyncMock(return_value=None))

    config = BacktestConfig(start_date=date(2026, 1, 2), end_date=date(2026, 1, 1))
    with pytest.raises(HTTPException) as run_exc:
        await backtest.run_backtest_api(config)
    with pytest.raises(HTTPException) as get_exc:
        await backtest.get_backtest_results("missing")

    assert run_exc.value.status_code == 400
    assert get_exc.value.status_code == 404
