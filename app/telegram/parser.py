import re
from loguru import logger as log
from app.signals.schemas import SignalInput

def parse_signal(text: str) -> SignalInput or None:
    """
    Parses a Telegram message into a SignalInput for:
    - TFXC SIGNALS UK (e.g. SELL XAUUSD 4455.7 TP1: 4453.7 SL: 4470.7)
    - Gold Pips Hunter (e.g. Gold Buy Now @ 4430 TP1: 4433 SL: 4421)
    """
    # --- EMOJI & SPECIAL CHARACTER CLEANING ---
    # Convert to upper and strip everything that isn't a letter, number, or standard punctuation
    # This effectively makes the bot "Emoji-Proof"
    text_clean = re.sub(r'[^\x00-\x7F]+', ' ', text).upper().strip()
    # Replace multiple spaces with single space
    text_clean = re.sub(r'\s+', ' ', text_clean)
    
    # 1. Determine Action (MULTUP/MULTDOWN for Margin Style)
    if any(keyword in text_clean for keyword in ["BUY", "LONG"]):
        action = "MULTUP"
    elif any(keyword in text_clean for keyword in ["SELL", "SHORT"]):
        action = "MULTDOWN"
    else:
        return None
        
    # 2. Determine Symbol
    # Blacklist of common header/alert words to ignore
    BLACKLIST = ["SIGNAL", "ALERT", "TRADE", "ENTRY", "MARKET", "LIMIT", "URGENT", "VIP"]
    
    symbol = None
    if "XAUUSD" in text_clean or "GOLD" in text_clean:
        symbol = "frxXAUUSD"
    else:
        # Look for 6-letter currency pairs (e.g. EURUSD) or slashed pairs (EUR/USD)
        # We also look for indices like R_100 or 1HZ100V
        # Prioritize Volatility and specialized indices
        if "VOLATILITY" in text_clean:
            # Check for (1S) variant first (e.g. Volatility 25 (1s) Index)
            v1s_match = re.search(r"VOLATILITY\s*(\d+)\s*\(?1S\)?", text_clean)
            if v1s_match:
                symbol = f"1HZ{v1s_match.group(1)}V"
            else:
                v_match = re.search(r"VOLATILITY\s*(\d+)", text_clean)
                if v_match:
                    num = v_match.group(1)
                    # For Volatility 90, Deriv often only supports Multipliers on the 1s version (1HZ90V)
                    if num == "90":
                        symbol = "1HZ90V"
                    else:
                        symbol = f"R_{num}"
        
        elif "STEP" in text_clean:
            symbol = "STPRNG"
        
        if not symbol:
            # Look for 6-letter currency pairs (e.g. EURUSD) or slashed pairs (EUR/USD)
            # We also look for indices like R_100 or 1HZ100V
            matches = re.finditer(r"([A-Z]{3}/?[A-Z]{3}|[A-Z]{1,2}_\d+|1HZ\d+V)", text_clean)
            for m in matches:
                found = m.group(1).replace("/", "").replace(" ", "")
                # Skip if it's in the blacklist
                if found in BLACKLIST:
                    continue
                
                symbol = found
                break

    # If no symbol found, default to Gold if appropriate or return None
    if not symbol:
        return None
        
    # Map common currency symbols to Deriv 'frx' format
    if not symbol.startswith("frx") and any(m in symbol for m in ["EUR", "GBP", "USD", "JPY", "AUD", "CAD", "NZD", "CHF"]):
        if len(symbol) == 6:
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
        # Extract TPs
        tp1_val = tp2_val = tp3_val = None
        
        # Support for "TP1: 4453.7" format
        tp1_match = re.search(r"TP1:?\s*([\d\.]+)", text_clean)
        tp2_match = re.search(r"TP2:?\s*([\d\.]+)", text_clean)
        tp3_match = re.search(r"TP3:?\s*([\d\.]+)", text_clean)
        
        if tp1_match:
            try: tp1_val = float(tp1_match.group(1))
            except: pass
        if tp2_match:
            try: tp2_val = float(tp2_match.group(1))
            except: pass
        if tp3_match:
            try: tp3_val = float(tp3_match.group(1))
            except: pass

        # Support for "TP 4724 / 4703" or "TP 34157" format
        if not tp1_val:
            tp_match = re.search(r"TP:?\s*([\d\.\s/]+)", text_clean)
            if tp_match:
                tps = re.findall(r"[\d\.]+", tp_match.group(1))
                if len(tps) > 0:
                    try: tp1_val = float(tps[0])
                    except: pass
                if len(tps) > 1:
                    try: tp2_val = float(tps[1])
                    except: pass
                if len(tps) > 2:
                    try: tp3_val = float(tps[2])
                    except: pass

        sl_match = re.search(r"SL:?\s*([\d\.]+)", text_clean)
        
        # We no longer average TPs. We extract them exactly as they are.
        # The executor will select the requested TP level based on settings.
            
        sl_val = None
        if sl_match:
            try: sl_val = float(sl_match.group(1))
            except: pass
            
        # Determine if it's a market or limit order
        # Limit keywords usually include LIMIT, PENDING, STOP, etc.
        order_type = "limit" if any(k in text_clean for k in ["LIMIT", "PENDING", "STOP"]) else "market"
            
        return SignalInput(
            symbol=symbol,
            action=action,
            stake=10.0, # Default stake
            take_profit=None, # Executor will set this based on config
            stop_loss=sl_val,
            entry_price=entry_price,
            source="telegram_channel",
            metadata={
                "order_type": order_type,
                "tp1": tp1_val, 
                "tp2": tp2_val,
                "tp3": tp3_val
            }
        )
    except Exception as e:
        log.error(f"Failed to parse signal: {e}")
        return None
