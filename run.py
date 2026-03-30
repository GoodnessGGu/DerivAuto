import asyncio
import os
import subprocess
from dotenv import load_dotenv
import uvicorn
from loguru import logger as log

# Force UTF-8 encoding for Windows terminal emojis
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

PORT = int(os.environ.get("PORT", 8000))

def free_port(port: int):
    """Kill any process listening on the given port (Windows only)."""
    if os.name != 'nt':
        return # Skip on Linux/Railway
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True)
                    log.info(f"Freed port {port} (killed PID {pid})")
    except Exception as e:
        log.warning(f"Could not free port {port}: {e}")

def setup_env():
    load_dotenv()
    # Check for critical variables
    if not os.getenv("DERIV_TOKEN"):
        log.error("DERIV_TOKEN is missing in .env!")
        return False
    if not os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") == "your_bot_token_here":
        log.warning("TELEGRAM_BOT_TOKEN is missing or NOT updated! Telegram bot will not start.")
    return True

if __name__ == "__main__":
    if setup_env():
        log.info("🚀 Starting Deriv Trading Bot System...")
        free_port(PORT)
        # Run FastAPI app (which starts Telegram Bot in lifespan)
        uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False)
