from app.config import settings
from app.core.logging import log
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.db_models import ExecutedTrade, Signal
from datetime import datetime, time

class RiskManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def validate_trade(self, symbol: str, stake: float) -> (bool, str):
        """Check if a trade follows risk rules."""
        # 1. Stake check
        if stake > settings.MAX_STAKE:
            return False, f"Stake {stake} exceeds MAX_STAKE {settings.MAX_STAKE}"
        
        # 2. Daily limits check
        async with self.session_factory() as session:
            today_start = datetime.combine(datetime.utcnow().date(), time.min)
            
            # Count today's trades
            q_count = select(func.count(ExecutedTrade.id)).where(ExecutedTrade.created_at >= today_start)
            count_result = await session.execute(q_count)
            daily_trades = count_result.scalar() or 0
            
            if daily_trades >= settings.MAX_DAILY_TRADES:
                return False, f"Daily trade limit {settings.MAX_DAILY_TRADES} reached"
            
            # Count today's loss
            q_loss = select(func.sum(ExecutedTrade.profit)).where(
                ExecutedTrade.created_at >= today_start,
                ExecutedTrade.profit < 0
            )
            loss_result = await session.execute(q_loss)
            daily_loss = abs(loss_result.scalar() or 0.0)
            
            if daily_loss >= settings.MAX_DAILY_LOSS:
                return False, f"Daily loss limit {settings.MAX_DAILY_LOSS} reached"

        return True, "Success"

    async def is_duplicate_signal(self, symbol: str, action: str, window_seconds: int = 60) -> bool:
        """Check if a similar signal was received within a short window."""
        async with self.session_factory() as session:
            cutoff = datetime.utcnow().timestamp() - window_seconds
            cutoff_dt = datetime.utcfromtimestamp(cutoff)
            
            q = select(Signal).where(
                Signal.symbol == symbol,
                Signal.action == action,
                Signal.created_at >= cutoff_dt
            )
            result = await session.execute(q)
            return result.first() is not None
