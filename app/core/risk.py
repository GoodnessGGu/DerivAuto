from app.config import settings
from app.core.logging import log
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.db_models import ExecutedTrade, Signal
from datetime import datetime, time

class RiskManager:
    def __init__(self, session_factory, config_mgr=None):
        self.session_factory = session_factory
        self.config_mgr = config_mgr

    async def validate_trade(self, symbol: str, stake: float) -> (bool, str):
        """Check if a trade follows dynamic risk rules."""
        # 1. Master Kill-Switch Check
        if self.config_mgr:
            cfg = await self.config_mgr.get_config()
            if not cfg.get("trading_enabled", True):
                return False, "Trading is currently PAUSED via Master Kill-Switch."
            
            # Use dynamic limits if available, fall back to settings
            max_stake = cfg.get("max_stake", settings.MAX_STAKE)
            max_trades = cfg.get("max_daily_trades", settings.MAX_DAILY_TRADES)
            max_loss = cfg.get("max_daily_loss", settings.MAX_DAILY_LOSS)
        else:
            max_stake = settings.MAX_STAKE
            max_trades = settings.MAX_DAILY_TRADES
            max_loss = settings.MAX_DAILY_LOSS

        # 2. Stake check
        if stake > max_stake:
            return False, f"Stake ${stake} exceeds current limit of ${max_stake}"
        
        # 3. Daily limits check
        async with self.session_factory() as session:
            today_start = datetime.combine(datetime.utcnow().date(), time.min)
            
            # Count today's trades
            q_count = select(func.count(ExecutedTrade.id)).where(ExecutedTrade.created_at >= today_start)
            count_result = await session.execute(q_count)
            daily_trades = count_result.scalar() or 0
            
            if daily_trades >= max_trades:
                return False, f"Daily trade limit {max_trades} reached"
            
            # Count today's loss
            q_loss = select(func.sum(ExecutedTrade.profit)).where(
                ExecutedTrade.created_at >= today_start,
                ExecutedTrade.profit < 0
            )
            loss_result = await session.execute(q_loss)
            daily_loss = abs(loss_result.scalar() or 0.0)
            
            if daily_loss >= max_loss:
                return False, f"Daily loss limit ${max_loss} reached"

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
