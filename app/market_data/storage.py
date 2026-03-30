from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import Tick, Candle
from app.core.logging import log
from datetime import datetime

class MarketDataStorage:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def save_tick(self, symbol: str, ask: float, bid: float, quote: float, epoch: int):
        """Save a new tick to the database."""
        async with self.session_factory() as session:
            try:
                tick = Tick(
                    symbol=symbol,
                    ask=ask,
                    bid=bid,
                    quote=quote,
                    epoch=epoch,
                    timestamp=datetime.utcfromtimestamp(epoch)
                )
                session.add(tick)
                await session.commit()
            except Exception as e:
                log.error(f"Error saving tick for {symbol}: {e}")
                await session.rollback()

    async def save_candle(self, symbol: str, timeframe: str, o: float, h: float, l: float, c: float, epoch: int):
        """Save an OHLC candle to the database."""
        async with self.session_factory() as session:
            try:
                candle = Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    epoch=epoch,
                    timestamp=datetime.utcfromtimestamp(epoch)
                )
                session.add(candle)
                await session.commit()
            except Exception as e:
                log.error(f"Error saving candle for {symbol} {timeframe}: {e}")
                await session.rollback()
