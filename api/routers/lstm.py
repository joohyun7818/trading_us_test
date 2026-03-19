"""
LSTM predictor router endpoints.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.services.lstm_predictor import LSTMPredictor

router = APIRouter(prefix="/api/lstm", tags=["lstm"])


class TrainRequest(BaseModel):
    train_end_date: str = "2024-06-30"
    epochs: int = 50
    batch_size: int = 256
    lr: float = 0.001


class PredictRequest(BaseModel):
    symbol: str


class PredictBatchRequest(BaseModel):
    symbols: list[str]


@router.post("/train")
async def train_lstm(request: TrainRequest) -> dict:
    """
    Train the LSTM model for 5-day direction prediction.

    Args:
        train_end_date: Date to split train/val data
        epochs: Number of training epochs
        batch_size: Batch size
        lr: Learning rate

    Returns:
        Training metrics including train_acc, train_auc, val_acc, val_auc, overfit_gap, epochs_trained
    """
    try:
        predictor = LSTMPredictor()
        result = await predictor.train(
            train_end_date=request.train_end_date,
            epochs=request.epochs,
            batch_size=request.batch_size,
            lr=request.lr,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/predict")
async def predict_symbol(request: PredictRequest) -> dict:
    """
    Predict 5-day direction for a single symbol.

    Args:
        symbol: Stock symbol

    Returns:
        {symbol, lstm_score, direction, confidence}
    """
    try:
        predictor = LSTMPredictor()
        result = await predictor.predict(request.symbol)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/predict-batch")
async def predict_batch_symbols(request: PredictBatchRequest) -> dict:
    """
    Predict 5-day direction for multiple symbols.

    Args:
        symbols: List of stock symbols

    Returns:
        List of prediction dicts
    """
    try:
        predictor = LSTMPredictor()
        results = await predictor.predict_batch(request.symbols)
        return {"predictions": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
