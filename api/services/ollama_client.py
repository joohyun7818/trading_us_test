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

# ── 변경: generate() 함수 ──
async def generate(
    prompt: str,
    model: str = None,
    system: str = None,
    temperature: float = 0.3,
    num_predict: int = 2048,
    max_retries: int = 2,
) -> str:
    """Ollama /api/chat 엔드포인트로 텍스트 생성 (think=false)"""
    model = model or settings.OLLAMA_DEEP_MODEL
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"

    # messages 구성
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,  # ← thinking 모드 비활성화
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT_GENERATE, connect=10.0)

    async with _ollama_lock:
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    # /api/chat 응답 구조: data.message.content
                    content = data.get("message", {}).get("content", "")

                    if content:
                        logger.info(
                            f"Ollama chat response: {len(content)} chars "
                            f"(model={model}, attempt={attempt+1})"
                        )
                        return content
                    else:
                        logger.warning(
                            f"Ollama chat empty response (model={model}, attempt={attempt+1})"
                        )

            except Exception as e:
                logger.error(
                    f"Ollama chat error (model={model}, attempt={attempt+1}/{max_retries+1}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

    logger.error(f"Ollama chat failed after {max_retries+1} attempts (model={model})")
    return ""


async def generate_fast(
    prompt: str,
    system: str = None,
    temperature: float = 0.3,
    num_predict: int = 1024,
) -> str:
    """빠른 분류용 - FAST_MODEL + think=false"""
    return await generate(
        prompt=prompt,
        model=settings.OLLAMA_FAST_MODEL,
        system=system,
        temperature=temperature,
        num_predict=num_predict,
    )


# ── 변경: generate_with_image() - deprecated 표시 ──

async def generate_with_image(
    prompt: str,
    image_bytes: bytes,
    model: str = None,
    system: str = None,
    temperature: float = 0.3,
    num_predict: int = 2048,
    max_retries: int = 2,
) -> str:
    """
    [DEPRECATED] 비전 분석은 Gemini API로 전환됨.
    gemini_client.gemini_generate_with_image() 를 사용하세요.
    이 함수는 하위 호환성을 위해 유지됩니다.
    """
    logger.warning(
        "generate_with_image() is deprecated. "
        "Use gemini_client.gemini_generate_with_image() instead."
    )
    # 폴백: Gemini API로 위임
    from api.services.gemini_client import gemini_generate_with_image
    return await gemini_generate_with_image(
        image_bytes=image_bytes,
        prompt=prompt,
        system_prompt=system,
        temperature=temperature,
        max_tokens=num_predict,
    )


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
