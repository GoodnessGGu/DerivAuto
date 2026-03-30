import pytest
from app.signals.schemas import SignalInput
from app.core.risk import RiskManager
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_signal_validation():
    # Valid signal
    signal_data = {
        "symbol": "R_100",
        "action": "CALL",
        "stake": 10.0,
        "duration": 5,
        "duration_unit": "m",
        "source": "unit_test"
    }
    signal = SignalInput(**signal_data)
    assert signal.symbol == "R_100"
    assert signal.action == "CALL"

@pytest.mark.asyncio
async def test_risk_manager_stake_limit():
    # Mock settings to have low max stake
    mock_session_factory = MagicMock()
    risk = RiskManager(mock_session_factory)
    
    # We need to monkeypatch settings or use a mock
    from app.config import settings
    original_max_stake = settings.MAX_STAKE
    settings.MAX_STAKE = 5.0
    
    passed, reason = await risk.validate_trade("R_100", 10.0)
    assert passed is False
    assert "exceeds MAX_STAKE" in reason
    
    # Reset
    settings.MAX_STAKE = original_max_stake
