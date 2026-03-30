import re
from loguru import logger as log
from app.signals.schemas import SignalInput

def parse_signal(text: str) -> SignalInput or None:
    """
    Parses a Telegram message into a SignalInput for:
    - TFXC SIGNALS UK (e.g. SELL XAUUSD 4455.7 TP1: 4453.7 SL: 4470.7)
    - Gold Pips Hunter (e.g. Gold Buy Now @ 4430 TP1: 4433 SL: 4421)
    """
    text_clean = text.upper().replace("🔴", "").replace("🤑", "").replace("🟢", "").strip()
    
    # 1. Determine Action (MULTUP/MULTDOWN for Margin Style)
    if any(keyword in text_clean for keyword in ["BUY", "LONG"]):
        action = "MULTUP"
    elif any(keyword in text_clean for keyword in ["SELL", "SHORT"]):
        action = "MULTDOWN"
    else:
        return None
        
    # 2. Determine Symbol (Map XAUUSD/Gold to frxXAUUSD)
    symbol = "frxXAUUSD" # Default for these channels
    if "XAUUSD" not in text_clean and "GOLD" not in text_clean:
        # If it's another pair, try to extract it
        match = re.search(r"([A-Z]{3}/?[A-Z]{3}|[A-Z]{2,}\d+)", text_clean)
        if match:
            symbol = match.group(1).replace("/", "")
            # Map common symbols to Deriv format
            if not symbol.startswith("frx") and any(m in symbol for m in ["EUR", "GBP", "USD", "JPY", "AUD"]):
                symbol = f"frx{symbol}"
    
    # 3. Extract Entry Price
    entry_price = None
    # Match price after XAUUSD or GOLD or ACTION
    entry_match = re.search(r"(?:XAUUSD|GOLD|BUY|SELL|LONG|SHORT|NOW|@)\s*(\d+\.?\d*)", text_clean)
    if entry_match:
        try: entry_price = float(entry_match.group(1))
        except: pass

    # 4. Extract TP/SL (Advanced Strategy)
    try:
        # TP Matches
        tp1_match = re.search(r"TP1:?\s*([\d\.]+)", text_clean)
        tp2_match = re.search(r"TP2:?\s*([\d\.]+)", text_clean)
        tp3_match = re.search(r"TP3:?\s*([\d\.]+)", text_clean)
        sl_match = re.search(r"SL:?\s*([\d\.]+)", text_clean)
        
        # Calculate Average TP if TP2 and TP3 exist
        tp_val = None
        if tp2_match and tp3_match:
            try:
                tp2 = float(tp2_match.group(1))
                tp3 = float(tp3_match.group(1))
                tp_val = round((tp2 + tp3) / 2, 2)
                log.info(f"Using Average TP Strategy: (TP2:{tp2} + TP3:{tp3}) / 2 = {tp_val}")
            except: pass
        
        # Fallback to TP1 if average not possible
        if tp_val is None and tp1_match:
            try: tp_val = float(tp1_match.group(1))
            except: pass
            
        sl_val = None
        if sl_match:
            try: sl_val = float(sl_match.group(1))
            except: pass
            
        return SignalInput(
            symbol=symbol,
            action=action,
            stake=10.0, # Default stake
            take_profit=tp_val,
            stop_loss=sl_val,
            entry_price=entry_price,
            source="telegram_channel",
            metadata={"tp1": tp1_match.group(1) if tp1_match else None, 
                      "tp2": tp2_match.group(1) if tp2_match else None,
                      "tp3": tp3_match.group(1) if tp3_match else None}
        )
    except Exception as e:
        log.error(f"Failed to parse signal: {e}")
        return None
