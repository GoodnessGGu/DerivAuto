from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import asyncio
from app.core.logging import log

@dataclass
class CandleState:
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    epoch: int  # Start of candle epoch

class CandleAggregator:
    def __init__(self, timeframes: List[str] = ["1m", "5m", "15m"]):
        self.timeframes = timeframes
        self.tf_seconds = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600
        }
        # (symbol, timeframe) -> CandleState
        self._current_candles: Dict[tuple, CandleState] = {}

    def process_tick(self, symbol: str, price: float, epoch: int) -> List[CandleState]:
        """Update candles and return completed ones."""
        completed_candles = []
        
        for tf in self.timeframes:
            sec = self.tf_seconds.get(tf, 60)
            candle_start = (epoch // sec) * sec
            
            key = (symbol, tf)
            current = self._current_candles.get(key)
            
            if not current:
                # First tick for this candle
                self._current_candles[key] = CandleState(
                    symbol=symbol, timeframe=tf,
                    open=price, high=price, low=price, close=price,
                    epoch=candle_start
                )
            elif candle_start > current.epoch:
                # This tick belongs to a new candle. Complete the previous one.
                completed_candles.append(current)
                # Initialize new candle
                self._current_candles[key] = CandleState(
                    symbol=symbol, timeframe=tf,
                    open=price, high=price, low=price, close=price,
                    epoch=candle_start
                )
            else:
                # Update existing candle
                current.close = price
                current.high = max(current.high, price)
                current.low = min(current.low, price)
                
        return completed_candles
