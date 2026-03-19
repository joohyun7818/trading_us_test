import asyncio
import logging
from typing import Any, Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

logger = logging.getLogger(__name__)


class FinBERTAnalyzer:
    _instance: Optional["FinBERTAnalyzer"] = None
    _model = None
    _tokenizer = None
    _pipeline = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        """모델과 토크나이저를 로드한다 (최초 1회)."""
        if self._pipeline is None:
            model_name = "ProsusAI/finbert"
            logger.info("Loading FinBERT model: %s", model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self._model,
                tokenizer=self._tokenizer,
                device=-1,  # CPU 강제 (로컬 환경 메모리 안정성)
            )
            logger.info("FinBERT model loaded successfully.")

    def _analyze_sync(self, text: str) -> dict[str, Any]:
        """동기식으로 단일 텍스트를 분석한다."""
        self._load_model()
        if not text or not text.strip():
            return {
                "sentiment": "neutral",
                "confidence": 0.0,
                "scores": {"positive": 0.0, "negative": 0.0, "neutral": 1.0},
                "sentiment_score": 0.0,
            }

        # 파이프라인은 기본적으로 가장 높은 점수 하나만 반환하므로 
        # 세부 점수를 얻기 위해 모델 직접 추론 또는 top_k 사용 가능
        # 여기서는 단순화를 위해 파이프라인 결과 사용 후 score 매핑
        results = self._pipeline(text[:512], top_k=None)  # BERT 512 토큰 제한
        
        scores = {res["label"]: res["score"] for res in results}
        sentiment = max(scores, key=scores.get)
        confidence = scores[sentiment]
        
        # sentiment_score = positive - negative (-1 ~ +1)
        sentiment_score = scores.get("positive", 0.0) - scores.get("negative", 0.0)

        return {
            "sentiment": sentiment,
            "confidence": round(float(confidence), 4),
            "scores": {k: round(float(v), 4) for k, v in scores.items()},
            "sentiment_score": round(float(sentiment_score), 4),
        }

    async def analyze(self, text: str) -> dict[str, Any]:
        """비동기 방식으로 단일 텍스트를 분석한다."""
        return await asyncio.to_thread(self._analyze_sync, text)

    async def analyze_batch(self, texts: list[str], batch_size: int = 16) -> list[dict[str, Any]]:
        """텍스트 리스트를 배치 단위로 분석한다."""
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = await asyncio.gather(*[self.analyze(t) for t in batch])
            results.extend(batch_results)
        return results


# 글로벌 인스턴스
finbert_analyzer = FinBERTAnalyzer()
