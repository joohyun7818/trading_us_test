"""
Tests for LSTM predictor service.
"""
import numpy as np
import pytest
import torch
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from api.services.lstm_predictor import LSTMPredictor, StockLSTM, StockDataset


class TestStockLSTM:
    """Test StockLSTM model."""

    def test_model_forward_pass(self):
        """Test model forward pass with correct input shape."""
        model = StockLSTM(input_size=10, hidden_size=64, num_layers=2, dropout=0.3)
        batch_size = 32
        seq_len = 60
        input_size = 10

        x = torch.randn(batch_size, seq_len, input_size)
        output = model(x)

        assert output.shape == (batch_size, 1)
        assert torch.all((output >= 0) & (output <= 1))  # Sigmoid output

    def test_model_initialization(self):
        """Test model initializes with correct architecture."""
        model = StockLSTM(input_size=10, hidden_size=64, num_layers=2, dropout=0.3)

        assert model.lstm.input_size == 10
        assert model.lstm.hidden_size == 64
        assert model.lstm.num_layers == 2
        assert model.fc1.in_features == 64
        assert model.fc1.out_features == 32
        assert model.fc2.in_features == 32
        assert model.fc2.out_features == 1


class TestStockDataset:
    """Test StockDataset."""

    def test_dataset_creation(self):
        """Test dataset creation."""
        sequences = np.random.randn(100, 60, 10)
        labels = np.random.randint(0, 2, (100, 1))

        dataset = StockDataset(sequences, labels)

        assert len(dataset) == 100
        seq, label = dataset[0]
        assert seq.shape == (60, 10)
        assert label.shape == (1,)


class TestLSTMPredictor:
    """Test LSTMPredictor."""

    @pytest.fixture
    def predictor(self):
        """Create predictor instance."""
        return LSTMPredictor()

    @pytest.fixture
    def sample_stock_daily_rows(self):
        """Generate sample stock_daily rows."""
        rows = []
        base_date = datetime(2024, 1, 1).date()
        for i in range(100):
            rows.append({
                "symbol": "AAPL",
                "trade_date": base_date + timedelta(days=i),
                "close": 150.0 + i * 0.1,
                "volume": 1000000,
                "rsi_14": 50.0,
                "macd": 0.5,
                "macd_signal": 0.4,
                "bollinger_pct_b": 0.5,
                "sma_20": 149.0,
                "sma_60": 148.0,
                "atr_14": 2.0,
            })
        return rows

    @pytest.mark.asyncio
    async def test_load_vix_data(self, predictor):
        """Test VIX data loading."""
        with patch("api.services.lstm_predictor.run_sync") as mock_run_sync:
            # Mock yfinance download
            import pandas as pd
            mock_vix_data = pd.DataFrame({
                "Close": [20.0, 21.0, 22.0],
            }, index=pd.date_range("2024-01-01", periods=3))
            mock_run_sync.return_value = mock_vix_data

            vix_df = await predictor._load_vix_data()

            assert len(vix_df) == 3
            assert "vix_close" in vix_df.columns
            assert "trade_date" in vix_df.columns

    @pytest.mark.asyncio
    async def test_prepare_data(self, predictor, sample_stock_daily_rows):
        """Test data preparation."""
        with patch("api.services.lstm_predictor.fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_stock_daily_rows

            with patch.object(predictor, "_load_vix_data", new_callable=AsyncMock) as mock_vix:
                import pandas as pd
                mock_vix.return_value = pd.DataFrame({
                    "trade_date": [row["trade_date"] for row in sample_stock_daily_rows[:10]],
                    "vix_close": [20.0] * 10,
                })

                train_dataset, val_dataset = await predictor.prepare_data("2024-03-01")

                assert len(train_dataset) > 0
                assert len(val_dataset) > 0
                assert train_dataset[0][0].shape == (60, 10)  # 60 days, 10 features
                assert train_dataset[0][1].shape == (1,)  # label

    @pytest.mark.asyncio
    async def test_train_basic(self, predictor):
        """Test basic training flow (mocked)."""
        # Create small mock datasets
        sequences = np.random.randn(100, 60, 10)
        labels = np.random.randint(0, 2, (100, 1)).astype(float)
        train_dataset = StockDataset(sequences, labels)
        val_dataset = StockDataset(sequences[:20], labels[:20])

        with patch.object(predictor, "prepare_data", new_callable=AsyncMock) as mock_prepare:
            mock_prepare.return_value = (train_dataset, val_dataset)

            result = await predictor.train(epochs=2, batch_size=32)

            assert "train_acc" in result
            assert "train_auc" in result
            assert "val_acc" in result
            assert "val_auc" in result
            assert "overfit_gap" in result
            assert "epochs_trained" in result
            assert result["epochs_trained"] <= 2

    @pytest.mark.asyncio
    async def test_predict_insufficient_data(self, predictor):
        """Test predict with insufficient data."""
        with patch("api.services.lstm_predictor.fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []  # No data

            with pytest.raises(ValueError, match="Insufficient data"):
                await predictor.predict("AAPL")

    @pytest.mark.asyncio
    async def test_predict_no_model(self, predictor):
        """Test predict without trained model."""
        with patch("api.services.lstm_predictor.fetch_all", new_callable=AsyncMock) as mock_fetch:
            # Return enough data
            rows = []
            base_date = datetime(2024, 1, 1).date()
            for i in range(70):
                rows.append({
                    "trade_date": base_date + timedelta(days=i),
                    "close": 150.0 + i * 0.1,
                    "volume": 1000000,
                    "rsi_14": 50.0,
                    "macd": 0.5,
                    "macd_signal": 0.4,
                    "bollinger_pct_b": 0.5,
                    "sma_20": 149.0,
                    "sma_60": 148.0,
                    "atr_14": 2.0,
                    "volume_ratio": 1.0,
                })
            mock_fetch.return_value = rows

            with patch.object(predictor, "_load_vix_data", new_callable=AsyncMock) as mock_vix:
                import pandas as pd
                mock_vix.return_value = pd.DataFrame({
                    "trade_date": [row["trade_date"] for row in rows],
                    "vix_close": [20.0] * len(rows),
                })

                with pytest.raises(ValueError, match="Model not found"):
                    await predictor.predict("AAPL")

    @pytest.mark.asyncio
    async def test_predict_batch(self, predictor):
        """Test batch prediction."""
        with patch.object(predictor, "predict", new_callable=AsyncMock) as mock_predict:
            mock_predict.side_effect = [
                {"symbol": "AAPL", "lstm_score": 65.0, "direction": "UP", "confidence": 0.3},
                {"symbol": "MSFT", "lstm_score": 45.0, "direction": "DOWN", "confidence": 0.1},
            ]

            results = await predictor.predict_batch(["AAPL", "MSFT"])

            assert len(results) == 2
            assert results[0]["symbol"] == "AAPL"
            assert results[1]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_predict_batch_with_errors(self, predictor):
        """Test batch prediction handles errors gracefully."""
        async def side_effect(symbol):
            if symbol == "INVALID":
                raise ValueError("Invalid symbol")
            return {"symbol": symbol, "lstm_score": 50.0, "direction": "UP", "confidence": 0.0}

        with patch.object(predictor, "predict", side_effect=side_effect):
            results = await predictor.predict_batch(["AAPL", "INVALID"])

            assert len(results) == 2
            assert results[0]["symbol"] == "AAPL"
            assert results[1]["symbol"] == "INVALID"
            assert "error" in results[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
