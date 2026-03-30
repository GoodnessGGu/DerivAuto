from app.signals.schemas import SignalInput
from app.core.risk import RiskManager
from app.deriv.trader import DerivTrader
from app.models.db_models import Signal, ExecutedTrade, FailedSignal
from app.core.logging import log
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta
import asyncio

from app.core.config_service import ConfigManager

class SignalExecutor:
    def __init__(self, trader: DerivTrader, risk: RiskManager, session_factory, config_mgr: ConfigManager):
        self.trader = trader
        self.risk = risk
        self.session_factory = session_factory
        self.config_mgr = config_mgr

    async def process_signal(self, signal_in: SignalInput, skip_duplicate_check: bool = False, force_execute: bool = False):
        """The main entry point for a new signal."""
        # --- DYNAMIC CONFIG OVERRIDES ---
        cfg = await self.config_mgr.get_config()
        
        # Override Stake and Multiplier with user-defined settings
        signal_in.stake = cfg.get("active_stake", signal_in.stake)
        if signal_in.contract_type in ["MULTUP", "MULTDOWN"]:
             signal_in.multiplier = cfg.get("active_multiplier", signal_in.multiplier)
             
        log.info(f"Processing signal: {signal_in.symbol} {signal_in.action} | Stake: {signal_in.stake} | Mult: {signal_in.multiplier}")
        
        # 1. Duplicate Protection (Check before saving, skippable for manual trades)
        if not skip_duplicate_check and await self.risk.is_duplicate_signal(signal_in.symbol, signal_in.action):
            log.warning(f"Duplicate signal rejected: {signal_in.symbol} {signal_in.action}")
            return {"status": "rejected", "reason": "duplicate signal within 60s window"}
            
        # 2. Store signal in DB
        signal_db = await self._save_signal(signal_in)
        
        # 3. Handle Limit Orders
        if not force_execute and signal_in.entry_price:
            log.info(f"Signal has entry price {signal_in.entry_price}. Saving as pending_limit.")
            await self._update_signal_status(signal_db.id, "pending_limit")
            return {"status": "pending_limit", "entry_price": signal_in.entry_price}

        # 4. Risk Check
        passed, reason = await self.risk.validate_trade(signal_in.symbol, signal_in.stake)

        # 4. Map Action to Contract Type
        from app.deriv.contracts import ACTION_TO_CONTRACT, ContractType
        contract_type = signal_in.contract_type or ACTION_TO_CONTRACT.get(signal_in.action.upper(), ContractType.CALL)

        # 5. Execute Trade with all parameters
        # Map 'stake' to 'amount' for the Deriv API
        params = signal_in.dict(exclude={"action", "contract_type", "metadata", "timestamp", "source", "confidence", "stake"}, exclude_none=True)
        params["contract_type"] = contract_type
        params["amount"] = signal_in.stake
        
        # Merge metadata into params
        if signal_in.metadata:
            params.update(signal_in.metadata)
            
        # If it's a multiplier and we need a spot price for conversion, fetch it if not provided
        if contract_type in ["MULTUP", "MULTDOWN"] and "spot_price" not in params:
            if signal_in.take_profit or signal_in.stop_loss:
                tick_res = await self.trader.client.send_request({"ticks": signal_in.symbol})
                if "tick" in tick_res:
                    params["spot_price"] = tick_res["tick"]["quote"]
                    # Forget tick subscription immediately
                    await self.trader.client.send_request({"forget_all": "ticks"})

        result = await self.trader.execute_contract(**params)

        if result["success"]:
            log.info(f"Trade executed SUCCESS: {result['contract_id']}")
            await self._update_signal_status(signal_db.id, "executed")
            await self._save_executed_trade(signal_db.id, signal_in.symbol, result)
            return {"status": "executed", "contract_id": result["contract_id"]}
        else:
            log.error(f"Trade execution FAILED: {result['error']}")
            await self._update_signal_status(signal_db.id, "failed")
            # Convert signal_data to dict and handle datetime for JSON serialization
            signal_data = signal_in.dict()
            if 'timestamp' in signal_data and signal_data['timestamp']:
                signal_data['timestamp'] = signal_data['timestamp'].isoformat()
            await self._save_failed_signal(signal_data, result["error"])
            return {"status": "failed", "error": result["error"]}

    def _map_action(self, action: str) -> str:
        action = action.upper()
        if action in ["BUY", "CALL"]: return "CALL"
        if action in ["SELL", "PUT"]: return "PUT"
        return "CALL"

    async def _save_signal(self, signal_in: SignalInput):
        async with self.session_factory() as session:
            db_signal = Signal(
                symbol=signal_in.symbol,
                action=signal_in.action,
                contract_type=signal_in.contract_type or self._map_action(signal_in.action),
                stake=signal_in.stake,
                duration=signal_in.duration,
                duration_unit=signal_in.duration_unit,
                currency=signal_in.currency,
                
                # Expanded Fields
                barrier=signal_in.barrier,
                barrier2=signal_in.barrier2,
                prediction=signal_in.prediction,
                multiplier=signal_in.multiplier,
                entry_price=signal_in.entry_price,
                take_profit=signal_in.take_profit,
                stop_loss=signal_in.stop_loss,
                
                confidence=signal_in.confidence,
                source=signal_in.source,
                metadata_json=signal_in.metadata
            )
            session.add(db_signal)
            await session.commit()
            await session.refresh(db_signal)
            return db_signal

    async def _update_signal_status(self, signal_id: int, status: str):
        async with self.session_factory() as session:
            signal = await session.get(Signal, signal_id)
            if signal:
                signal.status = status
                await session.commit()

    async def _save_executed_trade(self, signal_id: int, symbol: str, res: dict):
        async with self.session_factory() as session:
            trade = ExecutedTrade(
                signal_id=signal_id,
                symbol=symbol,
                contract_id=res["contract_id"],
                buy_price=res["buy_price"],
                status="open",
                entry_epoch=res["start_time"]
            )
            session.add(trade)
            await session.commit()

    async def _save_failed_signal(self, data: dict, reason: str):
        async with self.session_factory() as session:
            failed = FailedSignal(signal_data=data, reason=reason)
            session.add(failed)
            await session.commit()

    async def sync_open_trades(self):
        """Checks 'open' trades in DB against Deriv API and updates them."""
        async with self.session_factory() as session:
            q = select(ExecutedTrade).where(ExecutedTrade.status == "open")
            result = await session.execute(q)
            open_trades = result.scalars().all()
            
            for trade in open_trades:
                status_res = await self.trader.check_contract_status(trade.contract_id)
                if status_res and status_res.get("is_sold"):
                    trade.status = "won" if float(status_res.get("profit", 0)) > 0 else "lost"
                    trade.profit = float(status_res.get("profit", 0))
                    trade.sell_price = float(status_res.get("sell_price", 0))
                    trade.exit_epoch = status_res.get("sell_time")
                    trade.exit_tick = status_res.get("exit_tick")
                    log.info(f"Sync: Trade {trade.contract_id} closed as {trade.status} (Profit: {trade.profit})")
            
            await session.commit()

    async def get_pnl_stats(self):
        """Calculates detailed PnL and trade statistics."""
        await self.sync_open_trades() # Sync before calculating
        
        async with self.session_factory() as session:
            now = datetime.utcnow()
            day_ago = now - timedelta(days=1)
            week_ago = now - timedelta(days=7)
            
            # Helper for metrics
            async def get_metrics(start_date):
                # Total Profit
                profit_q = select(func.sum(ExecutedTrade.profit)).where(
                    ExecutedTrade.created_at >= start_date,
                    ExecutedTrade.status.in_(["won", "lost"])
                )
                profit = (await session.execute(profit_q)).scalar() or 0.0
                
                # Win Count
                win_q = select(func.count(ExecutedTrade.id)).where(
                    ExecutedTrade.created_at >= start_date,
                    ExecutedTrade.status == "won"
                )
                wins = (await session.execute(win_q)).scalar() or 0
                
                # Loss Count
                loss_q = select(func.count(ExecutedTrade.id)).where(
                    ExecutedTrade.created_at >= start_date,
                    ExecutedTrade.status == "lost"
                )
                losses = (await session.execute(loss_q)).scalar() or 0
                
                total = wins + losses
                win_rate = (wins / total * 100) if total > 0 else 0
                
                return {
                    "profit": round(profit, 2),
                    "wins": wins,
                    "losses": losses,
                    "total": total,
                    "win_rate": round(win_rate, 1)
                }
            
            stats_24h = await get_metrics(day_ago)
            stats_7d = await get_metrics(week_ago)
            
            # Get last 10 trades for history display
            recent_q = select(ExecutedTrade).order_by(desc(ExecutedTrade.created_at)).limit(10)
            recent_trades = (await session.execute(recent_q)).scalars().all()
            
            return {
                "daily": stats_24h,
                "weekly": stats_7d,
                "recent_trades": recent_trades
            }
