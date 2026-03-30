import asyncio
from app.deriv.client import DerivClient
from app.market_data.storage import MarketDataStorage
from app.market_data.candles import CandleAggregator
from app.core.logging import log
from app.config import settings

class MarketDataCollector:
    def __init__(self, client: DerivClient, storage: MarketDataStorage, symbols: list):
        self.client = client
        self.storage = storage
        self.symbols = symbols
        self.aggregator = CandleAggregator(settings.CANDLE_TIMEFRAMES)
        self._running = False
        self._ticks = {} # Cache for latest tick per symbol

    async def start(self):
        """Start collecting ticks for configured symbols."""
        log.info(f"Starting Market Data Collector for symbols: {self.symbols}")
        self._running = True
        
        # Register tick handler
        self.client.register_handler("tick", self._handle_tick)
        
        # Subscribe to each symbol
        for symbol in self.symbols:
            await self.client.subscribe_ticks(symbol)
            log.info(f"Subscribed to {symbol} ticks")

    async def _handle_tick(self, data: dict):
        """Callback for incoming ticks."""
        try:
            tick_data = data.get("tick")
            if not tick_data:
                return
            
            symbol = tick_data.get("symbol")
            ask = float(tick_data.get("ask"))
            bid = float(tick_data.get("bid"))
            quote = float(tick_data.get("quote"))
            epoch = int(tick_data.get("epoch"))
            
            # 0. Cache latest price for LimitOrderManager
            self._ticks[symbol] = quote
            
            # 1. Save tick to DB
            if settings.COLLECT_TICKS:
                asyncio.create_task(self.storage.save_tick(symbol, ask, bid, quote, epoch))
            
            # 2. Process for candles
            if settings.AGGREGATE_CANDLES:
                completed = self.aggregator.process_tick(symbol, quote, epoch)
                for candle in completed:
                    asyncio.create_task(self.storage.save_candle(
                        candle.symbol, candle.timeframe,
                        candle.open, candle.high, candle.low, candle.close, candle.epoch
                    ))
                    log.debug(f"Candle completed: {candle.symbol} {candle.timeframe}")
                    
        except Exception as e:
            log.error(f"Error in tick handler: {e}")

    async def stop(self):
        self._running = False
        log.info("Market Data Collector stopped")

    def get_last_tick(self, symbol: str) -> float or None:
        """Returns the last cached price for a symbol."""
        return self._ticks.get(symbol)
