import pandas as pd
import pytest
from unittest.mock import AsyncMock

from api.core.utils import run_sync
from api.services import alpaca_client, news_crawler, price_crawler


@pytest.mark.asyncio
async def test_run_sync_executes_sync_callable():
    result = await run_sync(sum, [1, 2, 3])
    assert result == 6


@pytest.mark.asyncio
async def test_news_crawler_finnhub_uses_run_sync(monkeypatch):
    class DummyClient:
        def company_news(self, *args, **kwargs):
            return []

    run_sync_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(news_crawler, "run_sync", run_sync_mock)
    monkeypatch.setattr(news_crawler.finnhub, "Client", lambda api_key: DummyClient())
    monkeypatch.setattr(news_crawler.settings, "FINNHUB_API_KEY", "test-key", raising=False)

    count = await news_crawler._crawl_finnhub(["AAPL"], "batch-1")

    assert count == 0
    run_sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_alpaca_get_account_uses_run_sync(monkeypatch):
    class Account:
        buying_power = "1000"
        cash = "1000"
        portfolio_value = "1000"
        equity = "1000"
        long_market_value = "0"
        short_market_value = "0"
        account_blocked = False
        trading_blocked = False

    class DummyClient:
        def get_account(self):
            return Account()

    run_sync_mock = AsyncMock(return_value=Account())
    monkeypatch.setattr(alpaca_client, "_get_trading_client", lambda: DummyClient())
    monkeypatch.setattr(alpaca_client, "run_sync", run_sync_mock)

    result = await alpaca_client.get_account()

    assert result["status"] == "ok"
    run_sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_crawler_download_uses_bounded_executor_wrapper(monkeypatch):
    run_sync_download_mock = AsyncMock(return_value=pd.DataFrame())
    monkeypatch.setattr(price_crawler, "run_sync_yf_download", run_sync_download_mock)
    monkeypatch.setattr(price_crawler, "execute", AsyncMock())

    result = await price_crawler.crawl_prices(symbols=["AAPL"])

    assert result["status"] == "ok"
    run_sync_download_mock.assert_awaited_once()
