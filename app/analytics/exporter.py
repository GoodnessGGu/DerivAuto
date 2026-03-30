from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pandas as pd
from app.models.db_models import Candle, Tick

class DataExporter:
    """Helper for exporting DB data for analysis."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def get_candles_df(self, symbol: str, timeframe: str = "1m", limit: int = 1000) -> pd.DataFrame:
        """Fetch candles and return as a pandas DataFrame."""
        async with self.session_factory() as session:
            query = select(Candle).where(
                Candle.symbol == symbol,
                Candle.timeframe == timeframe
            ).order_by(Candle.epoch.asc()).limit(limit)
            
            result = await session.execute(query)
            candles = result.scalars().all()
            
            if not candles:
                return pd.DataFrame()
                
            return pd.DataFrame([
                {
                    "timestamp": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "epoch": c.epoch
                } for c in candles
            ])

    async def get_ticks_df(self, symbol: str, limit: int = 5000) -> pd.DataFrame:
        """Fetch ticks and return as a pandas DataFrame."""
        async with self.session_factory() as session:
            query = select(Tick).where(Tick.symbol == symbol).order_by(Tick.epoch.asc()).limit(limit)
            result = await session.execute(query)
            ticks = result.scalars().all()
            
            if not ticks:
                return pd.DataFrame()
                
            return pd.DataFrame([
                {
                    "timestamp": t.timestamp,
                    "ask": t.ask,
                    "bid": t.bid,
                    "quote": t.quote,
                    "epoch": t.epoch
                } for t in ticks
            ])
