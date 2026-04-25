import asyncio
import os
import sys
import io

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import settings

async def read_last_messages():
    print("🔍 Starting Telegram Message Diagnostic...")
    
    api_id = settings.TELEGRAM_API_ID
    api_hash = settings.TELEGRAM_API_HASH
    string_session = settings.TELEGRAM_STRING_SESSION
    
    if not api_id or not api_hash:
        print("❌ Error: TELEGRAM_API_ID or TELEGRAM_API_HASH not found in .env")
        return

    # Initialize Client
    if string_session:
        client = TelegramClient(StringSession(string_session), int(api_id), api_hash)
    else:
        client = TelegramClient('deriv_user_session', int(api_id), api_hash)

    await client.start()
    
    # Channels to check
    channels_to_check = [
        "-1001761389530" # DERIV_SYNTHETIC SIGNALS 🔥🔥
    ]
    
    # Filter out empty ones
    channels_to_check = [c for c in channels_to_check if c]

    if not channels_to_check:
        print("❓ No channels configured in .env (TFXC, GOLD_PIPS, etc.)")
        return

    for channel_id in channels_to_check:
        try:
            # Clean channel ID (remove dashes, convert to int)
            cid = int(str(channel_id).replace('-', ''))
            # Note: Telethon sometimes needs the -100 prefix for channels
            if not str(channel_id).startswith('-'):
                cid = int(f"-100{cid}")
            else:
                cid = int(channel_id)

            entity = await client.get_entity(cid)
            print(f"\n--- 📡 Channel: {getattr(entity, 'title', cid)} ({cid}) ---")
            
            messages = await client.get_messages(entity, limit=10)
            
            for i, msg in enumerate(messages):
                if msg.text:
                    print(f"[{i+1}] {msg.date.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"Content: {msg.text.strip()}")
                    print("-" * 30)
                else:
                    print(f"[{i+1}] (Non-text message / Media)")
                    
        except Exception as e:
            print(f"❌ Could not read channel {channel_id}: {e}")

    await client.disconnect()
    print("\n✅ Diagnostic Complete.")

if __name__ == "__main__":
    asyncio.run(read_last_messages())
