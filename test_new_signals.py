import asyncio
from app.telegram.parser import parse_signal

async def test():
    signals = [
        """Volatility 25 (1s) Index 📊
Buy now 🔼🔼
Use safe management✅✅""",
        """VOLATILITY 75 INDEX SELL 
TP 34157
SL 34629
SPIKES SIGNAL 
PROPER RISK MANAGEMENT"""
    ]
    
    for i, sig in enumerate(signals):
        print(f"\n--- Testing Signal {i+1} ---")
        result = parse_signal(sig)
        if result:
            print(f"Symbol: {result.symbol}")
            print(f"Action: {result.action}")
            print(f"TP: {result.take_profit}")
            print(f"SL: {result.stop_loss}")
        else:
            print("Failed to parse")

if __name__ == "__main__":
    asyncio.run(test())
