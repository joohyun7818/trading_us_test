# Ollama REST 비동기 래퍼 - generate/embed/health_check, asyncio.Lock 순차 보장
import asyncio
import base64
import json
import logging
from typing import Any, Optional

import httpx

from api.core.config import settings

logger = logging.getLogger(__name__)

_ollama_lock = asyncio.Lock()


def _get_base_url() -> str:
    """Ollama 베이스 URL을 반환한다."""
    return settings.OLLAMA_BASE_URL.rstrip("/")


async def health_check() -> dict:
    """Ollama 서버 상태와 로드된 모델을 확인한다."""
    base = _get_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"status": "ok", "models": models}
            return {"status": "error", "code": resp.status_code}
    except Exception as e:
        logger.error("Ollama health check failed: %s", e)
        return {"status": "offline", "error": str(e)}


async def generate(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: float = 0.3,
    num_predict: int = 2048,
    max_retries: int = 2,
) -> str:
    """Ollama generate API를 호출한다. asyncio.Lock으로 순차 보장."""
    base = _get_base_url()
    model = model or settings.OLLAMA_DEEP_MODEL
    timeout = settings.OLLAMA_TIMEOUT_GENERATE

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt + " /no_think",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
        "keep_alive": "30m",
    }
    if system:
        payload["system"] = system

    async with _ollama_lock:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{base}/api/generate", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("response", "")
                    logger.error("Ollama generate HTTP %d: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                logger.error("Ollama generate attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2)

    return ""


async def generate_fast(
    prompt: str,
    system: Optional[str] = None,
    temperature: float = 0.1,
    num_predict: int = 2048,
) -> str:
    """빠른 1차 분류용 generate (qwen3:4b)."""
    return await generate(
        prompt=prompt,
        model=settings.OLLAMA_FAST_MODEL,
        system=system,
        temperature=temperature,
        num_predict=num_predict,
    )


async def generate_with_image(
    prompt: str,
    image_bytes: bytes,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: float = 0.3,
    num_predict: int = 2048,
    max_retries: int = 2,
) -> str:
    """이미지를 포함한 멀티모달 generate (qwen3-vl:8b)."""
    base = _get_base_url()
    model = model or settings.OLLAMA_VISION_MODEL
    timeout = settings.OLLAMA_TIMEOUT_VISION
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt + " /no_think",
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
        "keep_alive": "30m",
    }
    if system:
        payload["system"] = system

    async with _ollama_lock:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{base}/api/generate", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("response", "")
                    logger.error("Ollama vision HTTP %d", resp.status_code)
            except Exception as e:
                logger.error("Ollama vision attempt %d/%d: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2)

    return ""


async def embed(
    text: str,
    model: Optional[str] = None,
    max_retries: int = 2,
) -> list[float]:
    """Ollama embeddings API를 호출한다."""
    base = _get_base_url()
    model = model or settings.OLLAMA_EMBED_MODEL
    timeout = settings.OLLAMA_TIMEOUT_EMBED

    payload = {
        "model": model,
        "input": text,
        "keep_alive": "30m",
    }

    async with _ollama_lock:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(f"{base}/api/embed", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        embeddings = data.get("embeddings", [[]])
                        return embeddings[0] if embeddings else []
                    logger.error("Ollama embed HTTP %d", resp.status_code)
            except Exception as e:
                logger.error("Ollama embed attempt %d/%d: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2)

    return []


async def list_models() -> list[str]:
    """로드 가능한 모델 목록을 반환한다."""
    info = await health_check()
    return info.get("models", [])
