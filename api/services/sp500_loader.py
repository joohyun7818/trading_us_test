# Wikipedia/yfinance에서 S&P 500 목록을 가져와 stocks 테이블에 UPSERT
import logging
from typing import Optional

import aiohttp
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

from api.core.database import execute, execute_many, fetch_all, fetch_one

logger = logging.getLogger(__name__)

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


async def _fetch_wikipedia_sp500() -> list[dict]:
    """Wikipedia에서 S&P 500 종목 목록을 스크래핑한다."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(WIKI_SP500_URL) as resp:
                if resp.status != 200:
                    logger.error("Wikipedia HTTP %d", resp.status)
                    return []
                html = await resp.text()
    except Exception as e:
        logger.error("Wikipedia fetch failed: %s", e)
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", {"id": "constituents"})
        if table is None:
            tables = soup.find_all("table", {"class": "wikitable"})
            table = tables[0] if tables else None
        if table is None:
            logger.error("S&P 500 table not found on Wikipedia")
            return []

        rows = table.find_all("tr")[1:]
        stocks = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            symbol = cols[0].get_text(strip=True).replace(".", "-")
            name = cols[1].get_text(strip=True)
            sector = cols[3].get_text(strip=True)
            stocks.append({"symbol": symbol, "name": name, "sector": sector})
        logger.info("Parsed %d S&P 500 stocks from Wikipedia", len(stocks))
        return stocks
    except Exception as e:
        logger.error("Wikipedia parse failed: %s", e)
        return []


async def _ensure_sector(sector_name: str) -> int:
    """섹터를 조회하거나 없으면 생성하고 id를 반환한다."""
    row = await fetch_one("SELECT id FROM sectors WHERE name = $1", sector_name)
    if row:
        return row["id"]
    await execute(
        "INSERT INTO sectors (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
        sector_name,
    )
    row = await fetch_one("SELECT id FROM sectors WHERE name = $1", sector_name)
    return row["id"]


async def _get_market_cap(symbol: str) -> Optional[int]:
    """yfinance로 시가총액을 조회한다."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        return info.get("marketCap")
    except Exception:
        return None


async def load_sp500() -> dict:
    """S&P 500 전 종목을 DB에 UPSERT하고 결과를 반환한다."""
    stocks = await _fetch_wikipedia_sp500()
    if not stocks:
        return {"status": "error", "message": "No stocks fetched", "count": 0}

    upserted = 0
    errors = 0
    for stock in stocks:
        try:
            sector_id = await _ensure_sector(stock["sector"])
            await execute(
                """
                INSERT INTO stocks (symbol, name, sector_id, is_sp500)
                VALUES ($1, $2, $3, TRUE)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector_id = EXCLUDED.sector_id,
                    is_sp500 = TRUE,
                    updated_at = NOW()
                """,
                stock["symbol"],
                stock["name"],
                sector_id,
            )
            upserted += 1
        except Exception as e:
            logger.error("UPSERT failed for %s: %s", stock["symbol"], e)
            errors += 1

    logger.info("S&P 500 load complete: %d upserted, %d errors", upserted, errors)
    return {"status": "ok", "upserted": upserted, "errors": errors, "total": len(stocks)}


async def get_sp500_symbols() -> list[str]:
    """DB에서 S&P 500 종목 심볼 목록을 조회한다."""
    rows = await fetch_all("SELECT symbol FROM stocks WHERE is_sp500 = TRUE ORDER BY symbol")
    return [r["symbol"] for r in rows]
