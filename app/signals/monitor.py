import asyncio
from app.deriv.trader import DerivTrader
from app.models.db_models import ExecutedTrade
from app.core.config_service import ConfigManager
from app.core.logging import log
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

class TradeMonitor:
    def __init__(self, trader: DerivTrader, session_factory, config_mgr: ConfigManager):
        self.trader = trader
        self.session_factory = session_factory
        self.config_mgr = config_mgr
        self.is_running = False

    async def start(self):
        """Starts the background monitor loop."""
        self.is_running = True
        log.info("Starting Trade Monitor (Trailing SL) worker...")
        while self.is_running:
            try:
                cfg = await self.config_mgr.get_config()
                if cfg.get("trailing_sl_enabled"):
                    await self._check_open_trades()
            except Exception as e:
                log.error(f"Error in TradeMonitor loop: {e}")
            
            await asyncio.sleep(10) # Run every 10 seconds

    async def stop(self):
        self.is_running = False

    async def _check_open_trades(self):
        """Iterates through open trades and applies trailing SL logic."""
        async with self.session_factory() as session:
            q = select(ExecutedTrade).where(ExecutedTrade.status == "open")
            res = await session.execute(q)
            open_trades = res.scalars().all()

            for trade in open_trades:
                try:
                    # 1. Fetch current status from Deriv
                    status = await self.trader.check_contract_status(trade.contract_id)
                    if not status or status.get("is_sold"):
                        continue
                    
                    # 2. Calculate Profit Percentage
                    current_profit = float(status.get("profit", 0))
                    buy_price = float(status.get("buy_price", 1))
                    profit_pct = (current_profit / buy_price) * 100
                    
                    # 3. Trailing SL Logic
                    # Threshold: Move to break-even at 20% profit
                    # If profit > 20% and trade doesn't have an updated SL yet
                    if profit_pct > 20.0:
                        # Fetch current SL to see if we already updated it
                        # Deriv multiplier SL is a dollar amount
                        last_sl = status.get("limit_order", {}).get("stop_loss")
                        
                        # If SL is still negative (loss) or not set to break-even (0 or small positive)
                        if last_sl is None or float(last_sl) < 0:
                            log.info(f"Trailing SL: {trade.symbol} profit +{profit_pct:.1f}%. Moving SL to Break-Even.")
                            # Move SL to 0 (Break-even)
                            await self.trader.update_contract_limits(
                                trade.contract_id, 
                                stop_loss=0 # 0 means break-even on the Deriv Multiplier API for the sl amount
                            )
                except Exception as e:
                    log.error(f"Failed to process trailing SL for {trade.contract_id}: {e}")
            
            await session.commit()
