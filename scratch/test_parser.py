import sys
import io

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.telegram.parser import parse_signal
from app.signals.schemas import SignalInput
import json

texts = [
    """Volatility 90 Index 📊

Sell now 🔽🔽

Use safe management✅✅✅""",
    """📊Step Index signal ready🔔


📈BUY now 📈🔼📈


Use risk management ✔️✔️"""
]

for text in texts:
    print(f"\nParsing text:\n{text}\n")
    signal = parse_signal(text)

    if signal:
        print("SUCCESS: Signal detected!")
        print(json.dumps(signal.dict(), indent=2, default=str))
    else:
        print("FAILURE: Signal NOT detected.")
