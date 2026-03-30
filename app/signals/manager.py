import asyncio
from datetime import datetime
from loguru import logger as log
from sqlalchemy import select
from app.models.db_models import Signal
from app.signals.schemas import SignalInput

class LimitOrderManager:
    def __init__(self, executor, session_factory, data_collector, tg_bot=None):
        self.executor = executor
        self.session_factory = session_factory
        self.data_collector = data_collector
        self.tg_bot = tg_bot
        self.is_running = False
        self._task = None

    async def start(self):
        if self.is_running: return
        self.is_running = True
        self._task = asyncio.create_all_tasks = asyncio.create_task(self._monitor_loop())
        log.info("LimitOrderManager started.")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        log.info("LimitOrderManager stopped.")

    async def _monitor_loop(self):
        while self.is_running:
            try:
                await self._check_pending_orders()
            except Exception as e:
                log.error(f"Error in LimitOrderManager loop: {e}")
            await asyncio.sleep(1) # Check every second

    async def _check_pending_orders(self):
        async with self.session_factory() as session:
            q = select(Signal).where(Signal.status == "pending_limit")
            result = await session.execute(q)
            pending_signals = result.scalars().all()

            for sig in pending_signals:
                if not sig.entry_price:
                    continue

                # Get latest price from data collector
                current_price = self.data_collector.get_last_tick(sig.symbol)
                if not current_price:
                    # log.debug(f"No price data yet for {sig.symbol}")
                    continue

                # Trigger Logic
                should_trigger = False
                if sig.action.upper() in ["MULTUP", "BUY", "CALL", "LONG"]:
                    # Limit Buy: Trigger when price drops to or below entry
                    if current_price <= sig.entry_price:
                        should_trigger = True
                elif sig.action.upper() in ["MULTDOWN", "SELL", "PUT", "SHORT"]:
                    # Limit Sell: Trigger when price rises to or above entry
                    if current_price >= sig.entry_price:
                        should_trigger = True

                if should_trigger:
                    log.info(f"Triggering Limit Order for {sig.symbol} at {current_price} (Target: {sig.entry_price})")
                    
                    # 1. Immediate Lock: Change status to 'triggering' to prevent loop spam
                    await self.executor._update_signal_status(sig.id, "triggering")

                    # 2. Notify user if bot is available
                    if self.tg_bot:
                        asyncio.create_task(self.tg_bot.notify_trigger(sig.symbol, sig.action, current_price))

                    # 3. Convert DB model back to SignalInput for execution
                    signal_in = SignalInput(
                        symbol=sig.symbol,
                        action=sig.action,
                        stake=sig.stake,
                        take_profit=sig.take_profit,
                        stop_loss=sig.stop_loss,
                        entry_price=sig.entry_price,
                        multiplier=sig.multiplier,
                        source=sig.source or "limit_order_manager",
                        metadata=sig.metadata_json
                    )
                    # 4. Execute: Skip duplicate check because this is a re-trigger of a saved signal
                    await self.executor.process_signal(signal_in, skip_duplicate_check=True, force_execute=True)
                    # Note: Signal status will be updated inside process_signal
