import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Load env vars for convenience if running from project root
load_dotenv()

async def generate_session():
    print("--- Telegram Session String Generator ---")
    print("This script will help you authorize your Userbot locally.")
    print("The resulting string can be used as TELEGRAM_STRING_SESSION on Railway.\n")

    api_id = input("Enter your API ID (from my.telegram.org): ").strip()
    api_hash = input("Enter your API HASH: ").strip()
    phone = input("Enter your Phone Number (with +country code): ").strip()

    if not api_id or not api_hash or not phone:
        print("Error: API ID, Hash, and Phone are required.")
        return

    # Use StringSession('') to start a fresh authorization
    client = TelegramClient(StringSession(''), int(api_id), api_hash)
    
    try:
        await client.start(phone=phone)
        session_str = client.session.save()
        
        print("\n" + "="*50)
        print("SUCCESS! COPY THE STRING BELOW:")
        print("="*50 + "\n")
        print(session_str)
        print("\n" + "="*50)
        print("Add this string to your Railway Environment Variables as:")
        print("TELEGRAM_STRING_SESSION")
        print("="*50)
        
    except Exception as e:
        print(f"\nFailed to generate session: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(generate_session())
