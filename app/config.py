import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    # Deriv Configuration
    DERIV_TOKEN: str
    DERIV_APP_ID: int = 1089  # Default app_id for testing
    DERIV_SYMBOL_LIST: List[str] = [
        "R_100", "R_50", "1HZ100V", "1HZ50V",  # Indices
        "frxEURUSD", "frxGBPUSD",              # Forex
        "frxXAUUSD"                            # Gold/Commodities
    ]

    # Database Configuration
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/deriv_db"

    # Risk Management
    MAX_DAILY_TRADES: int = 50
    MAX_DAILY_LOSS: float = 100.0
    DEFAULT_STAKE: float = 1.0
    MAX_STAKE: float = 100.0

    # API Configuration
    PROJECT_NAME: str = "Deriv Trading Bot"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-for-internal-auth"

    # Market Data
    COLLECT_TICKS: bool = True
    AGGREGATE_CANDLES: bool = True
    CANDLE_TIMEFRAMES: List[str] = ["1m", "5m", "15m"]

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_ID: Optional[int] = None
    TELEGRAM_CHANNEL_TFXC: Optional[str] = None
    TELEGRAM_CHANNEL_GOLD_PIPS: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
