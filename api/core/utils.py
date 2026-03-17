import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_YF_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=5)


async def run_sync(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """동기 함수를 이벤트 루프 블로킹 없이 실행한다."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def run_sync_yf_download(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """yfinance download 동기 호출을 제한된 스레드풀에서 실행한다."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_YF_DOWNLOAD_EXECUTOR, partial(func, *args, **kwargs))
