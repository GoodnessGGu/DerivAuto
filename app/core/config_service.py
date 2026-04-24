from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.db_models import DynamicConfig
from app.core.logging import log
import asyncio

class ConfigManager:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._cache = {
            "active_stake": 5.0,
            "active_multiplier": 100,
            "trailing_sl_enabled": False,
            "active_account_type": "real",
            "trading_enabled": True,
            "max_stake": 50.0,
            "max_daily_trades": 20,
            "max_daily_loss": 100.0,
            "target_tp_level": 1
        }
        self._initialized = False

    async def get_config(self):
        """Returns the current dynamic config from cache or DB."""
        if not self._initialized:
            await self._refresh_cache()
        return self._cache

    async def update_setting(self, key: str, value):
        """Updates a specific dynamic setting in DB and cache."""
        async with self.session_factory() as session:
            q = select(DynamicConfig).where(DynamicConfig.id == 1)
            res = await session.execute(q)
            config = res.scalar_one_or_none()

            if not config:
                config = DynamicConfig(id=1)
                session.add(config)

            if hasattr(config, key):
                setattr(config, key, value)
                await session.commit()
                self._cache[key] = value
                log.info(f"Setting updated: {key} = {value}")
                return True
            else:
                log.error(f"Invalid setting key: {key}")
                return False

    async def _refresh_cache(self):
        """Initializes/Syncs the local cache from database."""
        try:
            async with self.session_factory() as session:
                q = select(DynamicConfig).where(DynamicConfig.id == 1)
                res = await session.execute(q)
                config = res.scalar_one_or_none()

                if config:
                    self._cache = {
                        "active_stake": config.active_stake,
                        "active_multiplier": config.active_multiplier,
                        "trailing_sl_enabled": config.trailing_sl_enabled,
                        "active_account_type": config.active_account_type,
                        "trading_enabled": config.trading_enabled,
                        "max_stake": config.max_stake,
                        "max_daily_trades": config.max_daily_trades,
                        "max_daily_loss": config.max_daily_loss,
                        "target_tp_level": config.target_tp_level
                    }
                else:
                    # Seed initial config if missing
                    log.info("No DynamicConfig found, seeding defaults.")
                    new_cfg = DynamicConfig(id=1)
                    session.add(new_cfg)
                    await session.commit()
                
                self._initialized = True
        except Exception as e:
            log.error(f"Failed to refresh config cache: {e}")
