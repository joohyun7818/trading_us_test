# asyncpg 커넥션 풀 관리 및 DB 헬퍼 함수
import logging
from typing import Any, Optional

import asyncpg

from api.core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """전역 asyncpg 커넥션 풀을 반환한다."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("Database connection pool created")
    return _pool


async def fetch_all(query: str, *args: Any) -> list[dict]:
    """SELECT 쿼리를 실행하고 모든 행을 dict 리스트로 반환한다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def fetch_one(query: str, *args: Any) -> Optional[dict]:
    """SELECT 쿼리를 실행하고 단일 행을 dict로 반환한다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute(query: str, *args: Any) -> str:
    """INSERT/UPDATE/DELETE 쿼리를 실행하고 상태 문자열을 반환한다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(query, *args)
        return result


async def execute_many(query: str, args_list: list[tuple]) -> None:
    """여러 행에 대해 동일 쿼리를 배치 실행한다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(query, args_list)


async def init_db() -> None:
    """DB 커넥션 풀을 초기화하고 연결을 확인한다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        logger.info("Database connected: %s", version[:60])


async def close_pool() -> None:
    """커넥션 풀을 닫는다."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")
