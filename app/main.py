import asyncio
import os
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import log
from app.core.database import async_session_factory, engine, Base
from app.deriv.client import DerivClient
from app.deriv.trader import DerivTrader
from app.market_data.collector import MarketDataCollector
from app.market_data.storage import MarketDataStorage
from app.signals.executor import SignalExecutor
from app.signals.manager import LimitOrderManager
from app.core.risk import RiskManager
from app.telegram.bot import TelegramBot
from app.telegram.listener import TelegramListener
from app.core.config_service import ConfigManager
from app.signals.monitor import TradeMonitor
from app.api.routes import router

# Dependency injection and service containers
config_mgr = ConfigManager(async_session_factory)
deriv_client = DerivClient(app_id=settings.DERIV_APP_ID, token=settings.DERIV_TOKEN)
deriv_trader = DerivTrader(deriv_client)
market_storage = MarketDataStorage(async_session_factory)
market_collector = MarketDataCollector(deriv_client, market_storage, settings.DERIV_SYMBOL_LIST)
risk_manager = RiskManager(async_session_factory, config_mgr)
signal_executor = SignalExecutor(deriv_trader, risk_manager, async_session_factory, config_mgr, market_collector)
limit_manager = LimitOrderManager(signal_executor, async_session_factory, market_collector)
trade_monitor = TradeMonitor(deriv_trader, async_session_factory, config_mgr)

# Initialize Telegram Bot if token provided
telegram_bot = None
tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
if tg_token and tg_token != "your_bot_token_here":
    telegram_bot = TelegramBot(tg_token, deriv_trader, signal_executor, config_mgr)
    limit_manager.tg_bot = telegram_bot # Link bot to manager for notifications
    signal_executor.tg_bot = telegram_bot # Link bot to executor for initial signal alerts

# Initialize Telegram Userbot Listener (Telethon)
telegram_listener = TelegramListener(signal_executor)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Initialize Database
    log.info("Starting up: Initializing database tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Clean up zombie signals
    await signal_executor.cleanup_on_startup()
    
    # 2. Connect to Deriv
    log.info("Starting up: Connecting to Deriv WebSocket")
    asyncio.create_task(deriv_client.connect())
    
    # Robust wait for connection and auth
    log.info("Waiting for Deriv connection to stabilize...")
    try:
        await asyncio.wait_for(deriv_client.connected_event.wait(), timeout=30.0)
        log.info("Deriv connection established and authorized!")
    except asyncio.TimeoutError:
        log.error("Failed to connect to Deriv within timeout. Startup continuing, but signal processing may be delayed.")

    # 3. Start Market Data Collection
    log.info("Starting up: Initializing Market Data Collector")
    try:
        await market_collector.start()
    except Exception as e:
        log.error(f"Market Data Collector failed to start: {e}")

    # 4. Start Limit Order Manager
    log.info("Starting up: Initializing Limit Order Manager")
    await limit_manager.start()

    # 5. Start Telegram Bot
    if telegram_bot:
        log.info("Starting up: Initializing Telegram Bot")
        asyncio.create_task(telegram_bot.start())

    # 6. Start Telegram Listener (Userbot)
    await telegram_listener.start()
    
    # 7. Start Trade Monitor (Trailing SL)
    asyncio.create_task(trade_monitor.start())
    
    # 5. Keep alive / ping loop
    async def ping_loop():
        while True:
            try:
                await asyncio.sleep(20) # Aggressive ping: 20s
                if deriv_client.connected_event.is_set():
                    await deriv_client.ping()
            except Exception as e:
                log.warning(f"Ping failed: {e}. Re-verifying connection...")
                # The client._listen task will handle reconnection, we just catch the error here
    
    asyncio.create_task(ping_loop())
    
    yield
    
    # 6. Shutdown Logic
    log.info("Shutting down: Stopping components")
    await trade_monitor.stop()
    await limit_manager.stop()
    await market_collector.stop()
    if telegram_bot:
        await telegram_bot.stop()
    await telegram_listener.stop()
    if deriv_client.ws:
        await deriv_client.ws.close()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Add routes
app.include_router(router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
