"""
System monitoring and configuration endpoints.
"""
import logging

from fastapi import APIRouter

from api.services.live_gate import evaluate_live_readiness

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/live-readiness")
async def get_live_readiness() -> dict:
    """
    Evaluate whether the system is ready for live trading.

    Returns a comprehensive assessment including:
    - ready: overall readiness status
    - score: percentage of criteria passed (0-100)
    - criteria: detailed breakdown of each criterion
    - blocking: list of failed criteria preventing live trading
    - staged_plan: phased rollout plan for gradual transition
    """
    return await evaluate_live_readiness()
