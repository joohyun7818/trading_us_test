# 파일: api/services/gemini_client.py
"""Gemini API 비동기 클라이언트 - 임베딩 + 텍스트 생성."""
import asyncio
import logging
from typing import Optional

import httpx

from api.core.database import fetch_one

logger = logging.getLogger(__name__)

_gemini_lock = asyncio.Lock()

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


async def _get_api_key() -> str:
    """settings에서 Gemini API Key를 로드한다."""
    row = await fetch_one("SELECT value FROM settings WHERE key = 'gemini_api_key'")
    if not row or not row["value"]:
        raise ValueError("Gemini API key not configured in settings")
    return row["value"]


async def _get_embed_config() -> dict:
    """임베딩 설정을 로드한다."""
    model_row = await fetch_one("SELECT value FROM settings WHERE key = 'gemini_embed_model'")
    dim_row = await fetch_one("SELECT value FROM settings WHERE key = 'gemini_embed_dim'")
    return {
        "model": model_row["value"] if model_row else "gemini-embedding-001",
        "dim": int(dim_row["value"]) if dim_row else 768,
    }


async def gemini_embed(
    text: str,
    task_type: str = "RETRIEVAL_DOCUMENT",
    max_retries: int = 5,
) -> list[float]:
    """Gemini Embedding API로 텍스트 임베딩을 생성한다."""
    api_key = await _get_api_key()
    config = await _get_embed_config()
    model = config["model"]
    dim = config["dim"]

    url = f"{GEMINI_BASE_URL}/models/{model}:embedContent"

    payload = {
        "model": f"models/{model}",
        "content": {
            "parts": [{"text": text[:8000]}]  # 토큰 제한 대비 문자열 제한
        },
        "taskType": task_type,
        "output_dimensionality": dim,
    }

    async with _gemini_lock:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": api_key,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        embedding = data.get("embedding", {}).get("values", [])
                        return embedding
                    elif resp.status_code == 429:
                        # 429 발생 시 더 긴 대기 시간 (5, 10, 20, 40, 60초)
                        wait = min(2 ** attempt * 5, 60)
                        logger.warning(
                            "Gemini embed rate limited (attempt %d/%d), "
                            "waiting %ds",
                            attempt, max_retries, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "Gemini embed HTTP %d: %s",
                            resp.status_code, resp.text[:300],
                        )
            except Exception as e:
                logger.error(
                    "Gemini embed attempt %d/%d failed: %s",
                    attempt, max_retries, e,
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)

    return []


async def gemini_embed_batch(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """여러 텍스트를 한 번에 임베딩한다 (API 1회 호출)."""
    api_key = await _get_api_key()
    config = await _get_embed_config()
    model = config["model"]
    dim = config["dim"]

    url = f"{GEMINI_BASE_URL}/models/{model}:embedContent"

    parts = [{"text": t[:8000]} for t in texts]

    payload = {
        "model": f"models/{model}",
        "content": {"parts": parts},
        "taskType": task_type,
        "output_dimensionality": dim,
    }

    async with _gemini_lock:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": api_key,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # 단일 content의 parts → 단일 임베딩 반환
                    # 여러 content가 필요하면 개별 호출
                    embedding = data.get("embedding", {}).get("values", [])
                    if embedding:
                        return [embedding]
                    # embeddings 배열이 올 수도 있음
                    embeddings = data.get("embeddings", [])
                    return [e.get("values", []) for e in embeddings]
                else:
                    logger.error("Gemini batch embed HTTP %d", resp.status_code)
        except Exception as e:
            logger.error("Gemini batch embed failed: %s", e)

    return []


async def gemini_generate(
    prompt: str,
    system: Optional[str] = None,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.3,
    max_tokens: int = 2048,
    max_retries: int = 3,
) -> str:
    """Gemini Generate API를 호출한다 (2차 분석 fallback 등)."""
    api_key = await _get_api_key()
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"

    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    if system:
        contents.insert(
            0, {"role": "user", "parts": [{"text": f"System: {system}"}]}
        )

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    async with _gemini_lock:
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": api_key,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            return parts[0].get("text", "") if parts else ""
                        return ""
                    elif resp.status_code == 429:
                        wait = min(2 ** attempt * 5, 60)
                        logger.warning("Gemini generate rate limited, waiting %ds", wait)
                        await asyncio.sleep(wait)
                    else:
                        logger.error("Gemini generate HTTP %d", resp.status_code)
            except Exception as e:
                logger.error("Gemini generate attempt %d/%d: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    await asyncio.sleep(2)

    return ""


# ============================================================
# 추가: 이미지 분석 (비전) - Gemini API
# ============================================================
async def gemini_generate_with_image(
    image_bytes: bytes,
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    mime_type: str = "image/png",
) -> str:
    """Gemini API로 이미지를 분석합니다 (차트 패턴 등)."""
    api_key = await _get_api_key()
    if not api_key:
        logger.error("Gemini API key not configured")
        return ""

    # gemini_client.py 기존 코드에서 사용하는 모델 설정 읽기
    config = await _get_embed_config()
    # flash 모델 사용 (기존 gemini_generate와 동일)
    model = config.get("gemini_flash_model", "gemini-2.5-flash")

    import base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"

    # 요청 본문 구성
    parts = [
        {
            "inline_data": {
                "mime_type": mime_type,
                "data": image_b64
            }
        },
        {"text": prompt}
    ]

    # system_prompt가 있으면 system_instruction으로 전달
    payload: dict = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
    }
    if system_prompt:
        payload["system_instruction"] = {
            "parts": [{"text": system_prompt}]
        }

    async with _gemini_lock:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=180.0) as client:
                    resp = await client.post(url, json=payload)

                    if resp.status_code == 429:
                        wait = 2 ** attempt * 5
                        logger.warning(f"Gemini vision rate limit, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts_resp = content.get("parts", [])
                        texts = [p["text"] for p in parts_resp if "text" in p]
                        result = "".join(texts)
                        logger.info(f"Gemini vision response: {len(result)} chars")
                        return result

                    logger.warning("Gemini vision: no candidates in response")
                    return ""

            except Exception as e:
                logger.error(f"Gemini vision attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

    return ""
