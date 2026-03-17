from datetime import date
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from api.routers import backtest
from api.services import historical_loader


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
