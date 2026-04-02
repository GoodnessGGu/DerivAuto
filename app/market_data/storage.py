import asyncio
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db_models import Tick, Candle
from app.core.logging import log

class MarketDataStorage:
    def __init__(self, session_factory, flush_interval: int = 5):
        self.session_factory = session_factory
        self.flush_interval = flush_interval
        self._tick_buffer: List[dict] = []
        self._candle_buffer: List[dict] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts the periodic background flush task."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        log.info(f"MarketDataStorage started (flush interval: {self.flush_interval}s)")

    async def stop(self):
        """Stops the periodic flush task and performs one final flush."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        log.info("MarketDataStorage stopped.")

    async def _periodic_flush(self):
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in periodic market data flush: {e}")

    def _convert_tick(self, data: dict) -> Tick:
        return Tick(
            symbol=data["symbol"],
            ask=data["ask"],
            bid=data["bid"],
            quote=data["quote"],
            epoch=data["epoch"],
            timestamp=datetime.utcfromtimestamp(data["epoch"])
        )

    def _convert_candle(self, data: dict) -> Candle:
        return Candle(
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            epoch=data["epoch"],
            timestamp=datetime.utcfromtimestamp(data["epoch"])
        )

    async def save_tick(self, symbol: str, ask: float, bid: float, quote: float, epoch: int):
        """Buffer a new tick for periodic saving."""
        async with self._lock:
            self._tick_buffer.append({
                "symbol": symbol, "ask": ask, "bid": bid, "quote": quote, "epoch": epoch
            })

    async def save_candle(self, symbol: str, timeframe: str, o: float, h: float, l: float, c: float, epoch: int):
        """Buffer a new candle for periodic saving."""
        async with self._lock:
            self._candle_buffer.append({
                "symbol": symbol, "timeframe": timeframe,
                "open": o, "high": h, "low": l, "close": c, "epoch": epoch
            })

    async def flush(self):
        """Writes all buffered items to the database in a single transaction."""
        async with self._lock:
            if not self._tick_buffer and not self._candle_buffer:
                return
            ticks_to_save = list(self._tick_buffer)
            candles_to_save = list(self._candle_buffer)
            self._tick_buffer.clear()
            self._candle_buffer.clear()

        async with self.session_factory() as session:
            try:
                # Convert dicts to models
                tick_models = [self._convert_tick(t) for t in ticks_to_save]
                candle_models = [self._convert_candle(c) for c in candles_to_save]
                
                if tick_models:
                    session.add_all(tick_models)
                if candle_models:
                    session.add_all(candle_models)
                
                await session.commit()
                log.debug(f"Flushed {len(tick_models)} ticks and {len(candle_models)} candles to DB.")
            except Exception as e:
                log.error(f"Error flushing market data to DB: {e}")
                await session.rollback()
