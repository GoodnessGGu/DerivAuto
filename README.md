# Deriv Trading Bot & Market Data Collector

A production-ready Python trading bot for Deriv that executes signals and collects real-time market data for AI analysis.

## Features
- **Signal Execution**: Automated CALL/PUT (BUY/SELL) execution via Deriv WebSocket.
- **Market Data Collection**: Real-time tick storage and candle aggregation in PostgreSQL.
- **Risk Management**: Daily trade limits, daily loss limits, and stake validation.
- **AI Readiness**: Feature engineering scaffold and data export to pandas DataFrames.
- **Modular Architecture**: Clean, async code with FastAPI for health checks and API endpoints.

## Tech Stack
- Python 3.11+
- FastAPI
- PostgreSQL + SQLAlchemy (Async)
- WebSockets (Deriv API)
- Docker

## Setup Instructions

### 1. Prerequisites
- Docker and Docker Compose (recommended)
- A Deriv account and API Token (with 'Trade' and 'Read' scopes)

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in your details:
```bash
DERIV_TOKEN=your_deriv_token
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/deriv_db
```

### 3. Local Run (Docker)
```bash
docker-compose up --build
```

### 4. Local Run (Manual)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the application:
   ```bash
   python app/main.py
   ```

## API Usage

### Send a Signal
```bash
curl -X POST http://localhost:8000/api/v1/signals/execute \
     -H "Content-Type: application/json" \
     -d '{
           "symbol": "R_100",
           "action": "CALL",
           "stake": 5,
           "duration": 5,
           "duration_unit": "m",
           "source": "webhook"
         }'
```

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Export Market Data
```bash
curl http://localhost:8000/api/v1/export/market-data?symbol=R_100&format=csv
```

## How the Market Data Pipeline Works
1. **Subscription**: On startup, the `MarketDataCollector` subscribes to ticks for configured symbols via WebSocket.
2. **Tick Storage**: Every incoming tick is saved to the `ticks` table.
3. **Candle Aggregation**: Ticks are processed by the `CandleAggregator`. When a timeframe window (e.g., 1m) closes, an OHLC candle is generated and saved to the `candles` table.

## AI Model Integration
To plug in an AI model:
1. Use the `DataExporter` in `app/analytics/exporter.py` to fetch historical data as a pandas DataFrame.
2. Run the data through `FeatureEngineer.prepare_features`.
3. Load your model in `app/analytics/features.py` inside `get_signal_score`.
4. Call `get_signal_score` during signal validation in `SignalExecutor` to filter or rank signals.

## Deployment Notes
- **Railway/Render**: Both support Dockerfiles. Point the deployment to the root directory.
- **Heroku**: Uses the included `Procfile`.
- Ensure PostgreSQL is provisioned and the `DATABASE_URL` is set in the environment.
