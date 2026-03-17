"""Pydantic models for validating LLM analysis responses.

These models ensure that LLM responses contain valid values within expected ranges,
preventing out-of-range values from propagating to downstream calculations.
"""
from typing import Literal

from pydantic import BaseModel, Field


class RAGAnalysisResult(BaseModel):
    """Validation model for stock analysis results from LLM.

    Ensures sentiment_score is in [-1.0, 1.0] range and confidence is in [0.0, 1.0].
    Invalid values are replaced with defaults to prevent anomalous signal generation.
    """
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_issues: list[str] = Field(default_factory=list, max_length=10)
    is_priced_in: bool = Field(default=False)
    outlook: Literal["bullish", "bearish", "neutral"] = Field(default="neutral")
    rationale: str = Field(default="", max_length=500)


class MacroAnalysisResult(BaseModel):
    """Validation model for macro analysis results from LLM.

    Ensures regime_score and confidence are in [0.0, 1.0] range.
    Invalid values are replaced with defaults.
    """
    regime: Literal["EXTREME_FEAR", "FEAR", "NEUTRAL", "GREED", "EXTREME_GREED"] = Field(
        default="NEUTRAL"
    )
    regime_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    key_factors: list[str] = Field(default_factory=list, max_length=10)
    outlook: Literal["bullish", "bearish", "neutral"] = Field(default="neutral")
    rationale: str = Field(default="", max_length=500)
