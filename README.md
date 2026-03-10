# AlphaFlow US

AI-powered swing trading automation system for S&P 500 stocks. Analyzes news sentiment (text), technical indicators (numeric), and candlestick chart patterns (visual) using a 3-axis pipeline with Ollama local LLMs. Executes trades via Alpaca API with macro regime-aware leveraged ETF strategy (TQQQ/SQQQ).

## Architecture

```
[S&P 500 Loader] --> [Price Crawler] --> [PostgreSQL]
        |
[News Crawler] --> [Sentiment] --> [News DB] --> [Indexer] --> [ChromaDB]
        |                                                         |
[Batch Processor]                                          [RAG Engine]
                                                                |
Step 0: Load & Crawl                                            |
        |                                                       |
Step 1: Screen                                                  |
        |                                                       |
Step 2: News + 1st Sentiment (qwen3:4b)                        |
        |                                                       |
Step 3: 2nd RAG + Visual (qwen3-vl:8b) <-----------------------+
        |
Step 4: 3-Axis Composite --> Orders
        |
[RAG Analyzer (qwen3:8b)]    [Chart Analyzer (qwen3-vl:8b)]
                                       ^
                                  [mplfinance]
        |
[Trading Engine]
  Text 0.35 + Numeric 0.50 + Macro 0.15
  (full: Text 0.25 + Numeric 0.35 + Visual 0.25 + Macro 0.15)
        |
[Alpaca API] --> Paper/Live Trading

[Macro Engine] --> Regime Score --> TQQQ/SQQQ Strategy
```

## Tech Stack

| Area | Technology |
|------|-----------|
| Backend | Python 3.11+, FastAPI (fully async/await) |
| Database | PostgreSQL 15+ (asyncpg driver) |
| Vector DB | ChromaDB (local persistent) |
| LLM Runtime | Ollama (http://localhost:11434) |
| LLM - 1st Classification | qwen3:4b (2.6GB, fast batch) |
| LLM - 2nd Deep Analysis | qwen3:8b (5.2GB, RAG response) |
| LLM - Chart Analysis | qwen3-vl:8b (~5.5GB, optional) |
| LLM - Embedding | bge-m3 (1.2GB, news vectorization) |
| Broker API | Alpaca (Paper Trading / Live) |
| News Sources | Finnhub API, Yahoo Finance RSS, Google News RSS |
| Price Data | yfinance |
| Chart Generation | mplfinance (candlestick PNG) |
| Frontend | React 18 + Vite + Tailwind CSS v3 (dark theme) |
| Scheduler | APScheduler (AsyncIOScheduler) |

## Prerequisites

- **PostgreSQL 15+** - Database server
- **Python 3.11+** - Backend runtime
- **Node.js 18+** - Frontend build
- **Ollama** - Local LLM runtime ([ollama.ai](https://ollama.ai))
- **Alpaca Account** - Trading API ([app.alpaca.markets/signup](https://app.alpaca.markets/signup))
- **Finnhub Account** - News API ([finnhub.io/register](https://finnhub.io/register))

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-repo/alphaflow-us.git
cd alphaflow-us

# 2. Environment
cp .env.example .env
# Edit .env to add your API keys

# 3. Database
docker-compose up -d db
pip install psycopg2-binary
python scripts/init_db.py

# 4. Ollama Models
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull qwen3-vl:8b
ollama pull bge-m3

# 5. Backend
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 6. Frontend
cd frontend
npm install
npm run dev
```

## Ollama Models

| Model | Purpose | Size | Memory |
|-------|---------|------|--------|
| qwen3:4b | 1st Sentiment Classification | 2.6GB | ~3-4GB |
| qwen3:8b | 2nd RAG Deep Analysis | 5.2GB | ~7-8GB |
| qwen3-vl:8b | Chart Pattern Analysis | ~5.5GB | ~8-9GB |
| bge-m3 | News Embedding | 1.2GB | ~1.5-2GB |

> **Note:** Models are loaded sequentially using asyncio.Lock to prevent concurrent loading, which is critical for 16GB RAM systems.

## 3-Axis Analysis Pipeline

### text_numeric Mode (Default)
Uses Text + Numeric analysis only. No vision model required.

| Axis | Weight | Source |
|------|--------|--------|
| Text | 0.35 | News sentiment via qwen3:4b + qwen3:8b RAG |
| Numeric | 0.50 | Technical indicators (RSI, MACD, SMA, Bollinger, Volume, 52W, ATR) |
| Macro | 0.15 | 7-indicator macro regime score |

### full Mode
Adds Visual analysis using chart pattern recognition.

| Axis | Weight | Source |
|------|--------|--------|
| Text | 0.25 | News sentiment via qwen3:4b + qwen3:8b RAG |
| Numeric | 0.35 | Technical indicators |
| Visual | 0.25 | Candlestick chart analysis via qwen3-vl:8b |
| Macro | 0.15 | 7-indicator macro regime score |

### Signal Generation
- **final_score >= 70** → BUY signal
- **final_score <= 30** → SELL signal
- **else** → HOLD

### Adjustments
- Priced-in news → -15 points
- RSI >= 75 (overbought) → -10 points
- RSI <= 25 (oversold) → +10 points
- Double bottom / Hammer pattern → +8 points
- Double top / Shooting star → -8 points

## Macro Regime + TQQQ/SQQQ Strategy

### 7 Macro Indicators
| Indicator | Weight |
|-----------|--------|
| S&P 500 Trend | 20% |
| VIX Level | 20% |
| Yield Curve Spread | 15% |
| Market RSI | 15% |
| Market Breadth | 10% |
| Put/Call Ratio | 10% |
| Macro News Sentiment | 10% |

### Regime Classification
| Score Range | Regime |
|-------------|--------|
| >= 0.8 | EXTREME_GREED → Consider TQQQ |
| 0.6 - 0.8 | GREED |
| 0.4 - 0.6 | NEUTRAL |
| 0.2 - 0.4 | FEAR |
| <= 0.2 | EXTREME_FEAR → Consider SQQQ |

### Leveraged Entry Conditions (Ultra-Conservative)
- EXTREME regime for **3 consecutive days**
- **No existing** leveraged position
- Maximum **3% of total capital**
- Stop-loss: **-8%**, Take-profit: **+15%**
- Maximum hold: **5 days**

## API Endpoints

### Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/summary` | Dashboard summary (KPIs) |
| GET | `/api/dashboard/sectors` | Sector statistics |
| GET | `/api/dashboard/signals` | Recent signals |
| GET | `/api/dashboard/stocks` | Stock list with indicators |

### News
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/news/{symbol}` | News by symbol |
| GET | `/api/news/sentiment/overview` | Sentiment overview |
| POST | `/api/news/trigger` | Manual news crawl |
| GET | `/api/news/status/collection` | Collection logs |
| POST | `/api/news/backfill/start` | Start backfill |
| GET | `/api/news/backfill/status` | Backfill progress |

### Alpaca
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/alpaca/connect` | Check connection |
| GET | `/api/alpaca/status` | Connection status |
| GET | `/api/alpaca/account` | Account info |
| GET | `/api/alpaca/holdings` | Current positions |
| POST | `/api/alpaca/order/buy` | Place buy order |
| POST | `/api/alpaca/order/sell` | Place sell order |
| GET | `/api/alpaca/orders` | List orders |
| POST | `/api/alpaca/cancel/{id}` | Cancel order |

### RAG
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/rag/index` | Trigger indexing |
| GET | `/api/rag/status` | Index status |
| POST | `/api/rag/analysis/{symbol}` | Run RAG analysis |
| GET | `/api/rag/history/{symbol}` | Analysis history |

### Macro
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/macro/regime` | Current regime |
| POST | `/api/macro/regime/calculate` | Trigger calculation |
| GET | `/api/macro/regime/history` | Regime history |
| GET | `/api/macro/leveraged/status` | Leveraged positions |
| GET | `/api/macro/leveraged/config` | Leveraged config |
| GET | `/api/macro/settings` | All settings |
| GET | `/api/macro/settings/{key}` | Get setting |
| PUT | `/api/macro/settings/{key}` | Update setting |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/ollama/status` | Ollama status |
| POST | `/api/batch/run` | Run full batch |

## Frontend Screens

### Dashboard (`/`)
- **KPI Cards**: Total Assets, Daily P&L, Active Positions, Today's Signals, Macro Regime, Ollama Status
- **Signal List**: Recent signals with score bars and type badges
- **Macro Gauge**: Semi-circular gauge from FEAR to GREED
- **News Panel**: Filterable news with sentiment indicators
- **Analysis Pipeline**: Radar chart showing 3-axis scores
- **Ollama Status**: Model availability and status
- **Backfill Progress**: News backfill progress tracker

### Macro View (`/macro`)
- **Large Macro Gauge**: Detailed regime visualization
- **Trend Charts**: 7 macro indicators over 30 days (recharts)
- **Leveraged Panel**: TQQQ/SQQQ positions with ON/OFF toggle

## Settings Management

Update settings via the API:

```bash
# Change analysis mode
curl -X PUT http://localhost:8000/api/macro/settings/analysis_mode \
  -H "Content-Type: application/json" \
  -d '{"value": "full"}'

# Enable leveraged trading
curl -X PUT http://localhost:8000/api/macro/settings/leveraged_enabled \
  -H "Content-Type: application/json" \
  -d '{"value": "true"}'

# Change max order amount
curl -X PUT http://localhost:8000/api/macro/settings/max_order_amount \
  -H "Content-Type: application/json" \
  -d '{"value": "2000"}'
```

## Development Guide

### Directory Structure
```
alphaflow-us/
├── api/
│   ├── core/          # Config, database pool
│   ├── models/        # SQL schema
│   ├── routers/       # FastAPI route handlers
│   ├── services/      # Business logic
│   └── main.py        # App entry point
├── frontend/
│   ├── src/
│   │   ├── pages/     # Dashboard, MacroView
│   │   └── components/# Reusable UI components
│   └── package.json
├── scripts/           # DB init script
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

### Coding Rules
1. All I/O operations must be `async def`
2. Database access via `asyncpg` only (no SQLAlchemy)
3. Type hints required for all functions
4. Docstrings in Korean, code/variable names in English
5. External APIs: `try-except` + `logging.error` + graceful degradation
6. Ollama: `asyncio.Lock` for sequential execution, no concurrent model loading
7. External APIs: 30s timeout, 3 retries with exponential backoff
8. Runtime settings from `settings` table (no hardcoding)
9. Logging via `logging.getLogger(__name__)`
10. Import order: standard library → third-party → local

## License

MIT
