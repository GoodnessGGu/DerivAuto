from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.database import get_db
from app.models.db_models import Tick, Candle, Signal, ExecutedTrade
from app.signals.schemas import SignalInput
from app.core.logging import log
from app.config import settings
import pandas as pd
from io import StringIO
from fastapi.responses import StreamingResponse

router = APIRouter()

# Global SignalExecutor will be injected or accessed via app state
# For simplicity in this scaffold, we'll assume it's attached to app.state

@router.get("/health")
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}

@router.post("/signals/execute")
async def execute_signal(signal: SignalInput, db: AsyncSession = Depends(get_db)):
    """Manual signal execution endpoint."""
    from app.main import signal_executor
    result = await signal_executor.process_signal(signal)
    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result

@router.get("/signals")
async def get_signals(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(limit))
    return result.scalars().all()

@router.get("/trades")
async def get_trades(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExecutedTrade).order_by(ExecutedTrade.created_at.desc()).limit(limit))
    return result.scalars().all()

@router.get("/market-data/ticks/latest")
async def get_latest_ticks(symbol: str, limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Tick).where(Tick.symbol == symbol).order_by(Tick.timestamp.desc()).limit(limit)
    )
    return result.scalars().all()

@router.get("/market-data/candles")
async def get_candles(
    symbol: str, 
    timeframe: str = "1m", 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Candle).where(
            Candle.symbol == symbol, 
            Candle.timeframe == timeframe
        ).order_by(Candle.epoch.desc()).limit(limit)
    )
    return result.scalars().all()

@router.get("/export/market-data")
async def export_market_data(
    symbol: str, 
    format: str = "csv", 
    db: AsyncSession = Depends(get_db)
):
    """Export historical data (candles) for AI training."""
    result = await db.execute(
        select(Candle).where(Candle.symbol == symbol).order_by(Candle.epoch.asc())
    )
    candles = result.scalars().all()
    
    # Convert to DataFrame
    df = pd.DataFrame([
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "epoch": c.epoch
        } for c in candles
    ])
    
    if format == "csv":
        stream = StringIO()
        df.to_csv(stream, index=False)
        return StreamingResponse(
            iter([stream.getvalue()]), 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={symbol}_data.csv"}
        )
    
    return df.to_dict(orient="records")
