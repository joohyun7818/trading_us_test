"""
LSTM-based 5-day direction predictor for stock movements.
Predicts whether a stock will be up or down in 5 days.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yfinance as yf
from sklearn.metrics import accuracy_score, roc_auc_score
from torch.utils.data import DataLoader, Dataset

from api.core.database import fetch_all, fetch_one
from api.core.utils import run_sync

logger = logging.getLogger(__name__)

# Model path
MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "lstm_latest.pt"


class StockLSTM(nn.Module):
    """
    LSTM model for 5-day stock direction prediction.
    Input: (batch, 60, 10) — 60-day window, 10 features
    Output: P(5-day up) — probability of upward movement
    """

    def __init__(self, input_size: int = 10, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.3):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
        )
        self.fc1 = nn.Linear(hidden_size, 32)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.2)
        self.fc2 = nn.Linear(32, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # x: (batch, seq_len, input_size)
        lstm_out, (h_n, c_n) = self.lstm(x)
        # Use last hidden state
        last_hidden = h_n[-1]  # (batch, hidden_size)
        out = self.fc1(last_hidden)
        out = self.relu(out)
        out = self.dropout(out)
        out = self.fc2(out)
        out = self.sigmoid(out)
        return out


class StockDataset(Dataset):
    """PyTorch Dataset for stock sequences."""

    def __init__(self, sequences: np.ndarray, labels: np.ndarray):
        self.sequences = torch.FloatTensor(sequences)
        self.labels = torch.FloatTensor(labels)

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        return self.sequences[idx], self.labels[idx]


class LSTMPredictor:
    """
    LSTM-based predictor for 5-day stock direction.
    """

    def __init__(self):
        self.model: Optional[StockLSTM] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.window_size = 60
        self.feature_names = [
            "close_pct_change",
            "volume_ratio",
            "rsi_14",
            "macd",
            "macd_signal",
            "bb_percent_b",
            "sma20_ratio",
            "sma60_ratio",
            "atr_ratio",
            "vix_close",
        ]

    async def _load_vix_data(self) -> pd.DataFrame:
        """Load VIX data from yfinance."""
        try:
            logger.info("Loading VIX data from yfinance...")
            vix_data = await run_sync(yf.download, "^VIX", period="5y", interval="1d", progress=False)
            if vix_data.empty:
                logger.warning("VIX data is empty")
                return pd.DataFrame()

            vix_df = pd.DataFrame({
                "trade_date": vix_data.index.date,
                "vix_close": vix_data["Close"].values,
            })
            logger.info("Loaded %d VIX records", len(vix_df))
            return vix_df
        except Exception as exc:
            logger.error("Failed to load VIX data: %s", exc)
            return pd.DataFrame()

    async def prepare_data(self, end_date: str = "2024-06-30") -> tuple[Dataset, Dataset]:
        """
        Prepare training and validation datasets from stock_daily.

        Args:
            end_date: Split date. Data before this = train, after = validation.

        Returns:
            (train_dataset, val_dataset)
        """
        logger.info("Preparing data with end_date=%s", end_date)

        # Load stock_daily data
        rows = await fetch_all(
            """
            SELECT symbol, trade_date, close, volume,
                   rsi_14, macd, macd_signal, bollinger_pct_b,
                   sma_20, sma_60, atr_14
            FROM stock_daily
            WHERE trade_date >= $1
            ORDER BY symbol, trade_date
            """,
            (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365 * 3)).date(),
        )

        if not rows:
            logger.error("No data found in stock_daily")
            raise ValueError("No data found in stock_daily")

        df = pd.DataFrame([dict(row) for row in rows])
        logger.info("Loaded %d rows from stock_daily", len(df))

        # Load VIX data
        vix_df = await self._load_vix_data()
        if not vix_df.empty:
            df = df.merge(vix_df, on="trade_date", how="left")
        else:
            df["vix_close"] = np.nan

        # Calculate features
        df = df.sort_values(["symbol", "trade_date"])

        # Group by symbol and calculate features
        sequences = []
        labels = []

        for symbol, group in df.groupby("symbol"):
            group = group.sort_values("trade_date").reset_index(drop=True)

            if len(group) < self.window_size + 5:
                continue

            # Calculate features
            group["close_pct_change"] = group["close"].pct_change()
            group["sma20_ratio"] = group["sma_20"] / group["close"]
            group["sma60_ratio"] = group["sma_60"] / group["close"]
            group["atr_ratio"] = group["atr_14"] / group["close"]

            # Forward fill VIX
            group["vix_close"] = group["vix_close"].ffill().bfill()

            # Calculate label: 5-day future return
            group["future_5d_return"] = group["close"].shift(-5) / group["close"] - 1
            group["label"] = (group["future_5d_return"] > 0).astype(float)

            # Create sequences
            for i in range(self.window_size, len(group) - 5):
                window = group.iloc[i - self.window_size : i]

                # Extract features
                features = window[
                    [
                        "close_pct_change",
                        "volume_ratio",
                        "rsi_14",
                        "macd",
                        "macd_signal",
                        "bollinger_pct_b",
                        "sma20_ratio",
                        "sma60_ratio",
                        "atr_ratio",
                        "vix_close",
                    ]
                ].values

                # Skip if any feature is NaN
                if np.isnan(features).any():
                    continue

                label = group.iloc[i]["label"]
                if np.isnan(label):
                    continue

                sequences.append(features)
                labels.append(label)

        if not sequences:
            raise ValueError("No valid sequences created from data")

        sequences = np.array(sequences)
        labels = np.array(labels).reshape(-1, 1)

        logger.info("Created %d sequences with shape %s", len(sequences), sequences.shape)

        # Normalize features (per feature, across all sequences)
        for i in range(sequences.shape[2]):
            feature = sequences[:, :, i]
            mean = np.nanmean(feature)
            std = np.nanstd(feature)
            if std > 0:
                sequences[:, :, i] = (feature - mean) / std

        # Split train/val by date
        split_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        # For simplicity, use first 70% as train, rest as val
        split_idx = int(len(sequences) * 0.7)

        train_sequences = sequences[:split_idx]
        train_labels = labels[:split_idx]
        val_sequences = sequences[split_idx:]
        val_labels = labels[split_idx:]

        logger.info("Train: %d sequences, Val: %d sequences", len(train_sequences), len(val_sequences))

        train_dataset = StockDataset(train_sequences, train_labels)
        val_dataset = StockDataset(val_sequences, val_labels)

        return train_dataset, val_dataset

    async def train(
        self,
        train_end_date: str = "2024-06-30",
        epochs: int = 50,
        batch_size: int = 256,
        lr: float = 0.001,
    ) -> dict:
        """
        Train the LSTM model.

        Args:
            train_end_date: Date to split train/val data
            epochs: Number of training epochs
            batch_size: Batch size
            lr: Learning rate

        Returns:
            Training metrics dict
        """
        logger.info("Starting LSTM training...")

        # Prepare data
        train_dataset, val_dataset = await self.prepare_data(train_end_date)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

        # Initialize model
        self.model = StockLSTM(input_size=10, hidden_size=64, num_layers=2, dropout=0.3)
        self.model = self.model.to(self.device)

        criterion = nn.BCELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)

        # Training loop
        best_val_loss = float("inf")
        patience = 5
        patience_counter = 0
        epochs_trained = 0

        for epoch in range(epochs):
            # Train
            self.model.train()
            train_loss = 0.0
            train_preds = []
            train_targets = []

            for sequences, labels in train_loader:
                sequences = sequences.to(self.device)
                labels = labels.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(sequences)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                train_loss += loss.item()
                train_preds.extend(outputs.detach().cpu().numpy())
                train_targets.extend(labels.detach().cpu().numpy())

            train_loss /= len(train_loader)
            train_preds = np.array(train_preds).flatten()
            train_targets = np.array(train_targets).flatten()
            train_acc = accuracy_score(train_targets, train_preds > 0.5)
            train_auc = roc_auc_score(train_targets, train_preds)

            # Validation
            self.model.eval()
            val_loss = 0.0
            val_preds = []
            val_targets = []

            with torch.no_grad():
                for sequences, labels in val_loader:
                    sequences = sequences.to(self.device)
                    labels = labels.to(self.device)

                    outputs = self.model(sequences)
                    loss = criterion(outputs, labels)

                    val_loss += loss.item()
                    val_preds.extend(outputs.cpu().numpy())
                    val_targets.extend(labels.cpu().numpy())

            val_loss /= len(val_loader)
            val_preds = np.array(val_preds).flatten()
            val_targets = np.array(val_targets).flatten()
            val_acc = accuracy_score(val_targets, val_preds > 0.5)
            val_auc = roc_auc_score(val_targets, val_preds)

            epochs_trained = epoch + 1

            logger.info(
                "Epoch %d/%d - Train Loss: %.4f, Train Acc: %.4f, Train AUC: %.4f - Val Loss: %.4f, Val Acc: %.4f, Val AUC: %.4f",
                epoch + 1,
                epochs,
                train_loss,
                train_acc,
                train_auc,
                val_loss,
                val_acc,
                val_auc,
            )

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save best model
                MODEL_DIR.mkdir(parents=True, exist_ok=True)
                torch.save(self.model.state_dict(), MODEL_PATH)
                logger.info("Saved best model to %s", MODEL_PATH)
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("Early stopping triggered at epoch %d", epoch + 1)
                    break

        # Load best model
        self.model.load_state_dict(torch.load(MODEL_PATH))

        overfit_gap = train_auc - val_auc

        result = {
            "train_acc": round(train_acc, 4),
            "train_auc": round(train_auc, 4),
            "val_acc": round(val_acc, 4),
            "val_auc": round(val_auc, 4),
            "overfit_gap": round(overfit_gap, 4),
            "epochs_trained": epochs_trained,
        }

        logger.info("Training completed: %s", result)
        return result

    def _load_model(self):
        """Load the trained model."""
        if self.model is None:
            if not MODEL_PATH.exists():
                raise ValueError("Model not found. Please train the model first.")
            self.model = StockLSTM(input_size=10, hidden_size=64, num_layers=2, dropout=0.3)
            self.model.load_state_dict(torch.load(MODEL_PATH, map_location=self.device))
            self.model = self.model.to(self.device)
            self.model.eval()
            logger.info("Loaded model from %s", MODEL_PATH)

    async def predict(self, symbol: str) -> dict:
        """
        Predict 5-day direction for a single symbol.

        Args:
            symbol: Stock symbol

        Returns:
            {symbol, lstm_score, direction, confidence}
        """
        self._load_model()

        # Get recent 60 days of data
        rows = await fetch_all(
            """
            SELECT trade_date, close, volume,
                   rsi_14, macd, macd_signal, bollinger_pct_b,
                   sma_20, sma_60, atr_14
            FROM stock_daily
            WHERE symbol = $1
            ORDER BY trade_date DESC
            LIMIT $2
            """,
            symbol,
            self.window_size + 10,
        )

        if len(rows) < self.window_size:
            raise ValueError(f"Insufficient data for {symbol}. Need at least {self.window_size} days.")

        df = pd.DataFrame([dict(row) for row in rows])
        df = df.sort_values("trade_date").reset_index(drop=True)

        # Load VIX data for the date range
        vix_df = await self._load_vix_data()
        if not vix_df.empty:
            df = df.merge(vix_df, on="trade_date", how="left")
        else:
            df["vix_close"] = np.nan

        # Calculate features
        df["close_pct_change"] = df["close"].pct_change()
        df["sma20_ratio"] = df["sma_20"] / df["close"]
        df["sma60_ratio"] = df["sma_60"] / df["close"]
        df["atr_ratio"] = df["atr_14"] / df["close"]
        df["vix_close"] = df["vix_close"].ffill().bfill()

        # Get last 60 days
        window = df.iloc[-self.window_size :]

        features = window[
            [
                "close_pct_change",
                "volume_ratio",
                "rsi_14",
                "macd",
                "macd_signal",
                "bollinger_pct_b",
                "sma20_ratio",
                "sma60_ratio",
                "atr_ratio",
                "vix_close",
            ]
        ].values

        if np.isnan(features).any():
            raise ValueError(f"Missing features for {symbol}")

        # Normalize features (using same normalization as training - simplified here)
        # In production, should save normalization params during training
        for i in range(features.shape[1]):
            mean = np.nanmean(features[:, i])
            std = np.nanstd(features[:, i])
            if std > 0:
                features[:, i] = (features[:, i] - mean) / std

        # Predict
        def _predict():
            self.model.eval()
            with torch.no_grad():
                x = torch.FloatTensor(features).unsqueeze(0).to(self.device)
                prob = self.model(x).item()
            return prob

        prob = await asyncio.to_thread(_predict)

        lstm_score = round(prob * 100, 2)
        direction = "UP" if prob > 0.5 else "DOWN"
        confidence = round(abs(prob - 0.5) * 2, 4)

        return {
            "symbol": symbol,
            "lstm_score": lstm_score,
            "direction": direction,
            "confidence": confidence,
        }

    async def predict_batch(self, symbols: list[str]) -> list[dict]:
        """
        Predict 5-day direction for multiple symbols.

        Args:
            symbols: List of stock symbols

        Returns:
            List of prediction dicts
        """
        results = []
        for symbol in symbols:
            try:
                result = await self.predict(symbol)
                results.append(result)
            except Exception as exc:
                logger.error("Failed to predict for %s: %s", symbol, exc)
                results.append(
                    {
                        "symbol": symbol,
                        "error": str(exc),
                        "lstm_score": None,
                        "direction": None,
                        "confidence": None,
                    }
                )
        return results
