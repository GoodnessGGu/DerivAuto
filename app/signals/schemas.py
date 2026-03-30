from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime

class SignalInput(BaseModel):
    symbol: str
    action: str  # CALL/PUT, MATCH/DIFF, OVER/UNDER, etc.
    contract_type: Optional[str] = None
    stake: float = Field(..., gt=0)
    duration: Optional[int] = Field(None, gt=0)
    duration_unit: str = "m"  # t, s, m, h, d
    currency: str = "USD"
    entry_price: Optional[float] = None
    
    # Advanced Parameters
    barrier: Optional[str] = None      # For Digits, Touches, etc.
    barrier2: Optional[str] = None     # For Range contracts
    prediction: Optional[int] = None   # For Digits (0-9)
    multiplier: Optional[int] = None   # For Multipliers (10, 20, 100, etc.)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    source: str
    confidence: Optional[float] = None
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None

    @validator('action')
    def validate_action(cls, v):
        return v.upper()

    @validator('duration_unit')
    def validate_unit(cls, v):
        if v not in ["t", "s", "m", "h", "d"]:
            raise ValueError('Duration unit must be t, s, m, h, or d')
        return v
    
    @validator('prediction')
    def validate_prediction(cls, v):
        if v is not None and not (0 <= v <= 9):
            raise ValueError('Prediction must be between 0 and 9')
        return v
