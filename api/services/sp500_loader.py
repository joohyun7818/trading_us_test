# GitHub CSV에서 S&P 500 목록을 가져와 stocks 테이블에 UPSERT
import logging
from io import StringIO
from typing import Optional

import httpx
import pandas as pd
import yfinance as yf

from api.core.database import execute, execute_many, fetch_all, fetch_one
from api.core.utils import run_sync

logger = logging.getLogger(__name__)

GITHUB_SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


async def _fetch_sp500_list() -> list[dict]:
    """GitHub CSV에서 S&P 500 종목 목록을 가져온다."""
    headers = {
        "User-Agent": "AlphaFlow/1.0"
    }
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            resp = await client.get(GITHUB_SP500_CSV)
            if resp.status_code != 200:
                logger.error("GitHub CSV HTTP %d", resp.status_code)
                return []
            df = pd.read_csv(StringIO(resp.text))
    except Exception as e:
        logger.error("GitHub CSV fetch failed: %s", e)
        return []

    stocks = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().replace(".", "-")
        name = str(row.get("Security", "")).strip()
        sector = str(row.get("GICS Sector", "")).strip()
        if symbol and name:
            stocks.append({"symbol": symbol, "name": name, "sector": sector})

    logger.info("Parsed %d S&P 500 stocks from GitHub CSV", len(stocks))
    return stocks


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
        info = await run_sync(lambda: ticker.info)
        return info.get("marketCap")
    except Exception:
        return None


async def load_sp500() -> dict:
    """S&P 500 전 종목을 DB에 UPSERT하고 결과를 반환한다."""
    stocks = await _fetch_sp500_list()
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
