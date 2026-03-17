"""Utility functions for async operations."""
import asyncio
from functools import partial
from typing import TypeVar, Callable, Any

T = TypeVar("T")


async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """동기 함수를 이벤트 루프 블로킹 없이 실행한다."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))
