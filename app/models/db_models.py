from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Tick(Base):
    __tablename__ = "ticks"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    ask = Column(Float, nullable=False)
    bid = Column(Float, nullable=False)
    quote = Column(Float, nullable=False)
    epoch = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    source = Column(String, default="deriv")

class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    timeframe = Column(String, index=True, nullable=False)  # 1m, 5m, etc.
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    epoch = Column(BigInteger, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)
    contract_type = Column(String, nullable=False)
    stake = Column(Float, nullable=False)
    duration = Column(Integer)
    duration_unit = Column(String)
    currency = Column(String, default="USD")
    
    # Expanded Fields
    barrier = Column(String)
    barrier2 = Column(String)
    prediction = Column(Integer)
    multiplier = Column(Integer)
    entry_price = Column(Float)
    take_profit = Column(Float)
    stop_loss = Column(Float)
    
    confidence = Column(Float)
    source = Column(String, nullable=False)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")

    trade = relationship("ExecutedTrade", back_populates="signal", uselist=False)

class ExecutedTrade(Base):
    __tablename__ = "executed_trades"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=False)
    symbol = Column(String, nullable=False)
    contract_id = Column(BigInteger, unique=True)
    buy_price = Column(Float)
    sell_price = Column(Float)
    profit = Column(Float)
    status = Column(String)  # open, won, lost, cancelled
    entry_tick = Column(Float)
    exit_tick = Column(Float)
    entry_epoch = Column(BigInteger)
    exit_epoch = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow)

    signal = relationship("Signal", back_populates="trade")

class BotEvent(Base):
    __tablename__ = "bot_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String, index=True)  # auth, reconnect, error, info
    message = Column(String)
    metadata_json = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

class FailedSignal(Base):
    __tablename__ = "failed_signals"

    id = Column(Integer, primary_key=True)
    signal_data = Column(JSON, nullable=False)
    reason = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class DynamicConfig(Base):
    __tablename__ = "dynamic_config"

    id = Column(Integer, primary_key=True)
    active_stake = Column(Float, default=5.0)
    active_multiplier = Column(Integer, default=100)
    trailing_sl_enabled = Column(Boolean, default=False)
    active_account_type = Column(String, default="real") # "demo" or "real"
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
