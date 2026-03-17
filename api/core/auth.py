# FastAPI 인증 미들웨어
from fastapi import HTTPException, Header
from typing import Optional

from api.core.config import settings


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """
    X-API-Key 헤더를 검증하는 FastAPI 의존성 함수.

    API_KEY가 빈 문자열이면 인증을 비활성화한다 (개발 편의).
    API_KEY가 설정되어 있으면 헤더와 비교하여 불일치 시 401을 반환한다.

    Args:
        x_api_key: X-API-Key 헤더 값

    Raises:
        HTTPException: 인증 실패 시 401 에러
    """
    # API_KEY가 설정되지 않았거나 빈 문자열이면 인증 비활성화
    if not settings.API_KEY:
        return

    # API_KEY가 설정되어 있으면 헤더 검증
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing X-API-Key header"
        )
