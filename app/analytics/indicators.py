import pandas as pd
import numpy as np
from typing import List, Dict

class TechnicalIndicators:
    """Scaffold for technical indicator calculations."""
    
    @staticmethod
    def add_sma(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.DataFrame:
        df[f"SMA_{period}"] = df[column].rolling(window=period).mean()
        return df

    @staticmethod
    def add_ema(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.DataFrame:
        df[f"EMA_{period}"] = df[column].ewm(span=period, adjust=False).mean()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.DataFrame:
        delta = df[column].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df[f"RSI_{period}"] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def add_bollinger_bands(df: pd.DataFrame, period: int = 20, num_std: int = 2, column: str = "close") -> pd.DataFrame:
        sma = df[column].rolling(window=period).mean()
        std = df[column].rolling(window=period).std()
        df[f"BB_Upper_{period}"] = sma + (std * num_std)
        df[f"BB_Lower_{period}"] = sma - (std * num_std)
        return df

    @staticmethod
    def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, column: str = "close") -> pd.DataFrame:
        exp1 = df[column].ewm(span=fast, adjust=False).mean()
        exp2 = df[column].ewm(span=slow, adjust=False).mean()
        df["MACD"] = exp1 - exp2
        df["MACD_Signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]
        return df
