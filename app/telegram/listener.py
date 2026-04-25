from app.config import settings
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from loguru import logger as log
from app.signals.executor import SignalExecutor
from app.telegram.parser import parse_signal

class TelegramListener:
    def __init__(self, executor: SignalExecutor):
        self.executor = executor
        self.api_id = settings.TELEGRAM_API_ID
        self.api_hash = settings.TELEGRAM_API_HASH
        self.phone = settings.TELEGRAM_USER_PHONE
        
        # Authorized Channels
        self.channel_ids = [
            settings.TELEGRAM_CHANNEL_TFXC,
            settings.TELEGRAM_CHANNEL_GOLD_PIPS,
            settings.TELEGRAM_CHANNEL_ALBURQUERQUE,
            settings.TELEGRAM_CHANNEL_SYNTHETIC
        ]
        # Filter out None values and clean numeric strings
        self.channel_ids = [int(cid) for cid in self.channel_ids if cid and str(cid).replace('-', '').isdigit()]
        
        self.client = None
        self.is_running = False

    async def start(self):
        """Starts the Telethon client."""
        if not self.api_id or self.api_id == "your_api_id_here":
            log.warning("TELEGRAM_API_ID not set. Userbot listener will NOT start.")
            return

        log.info("Starting Telethon Userbot Listener...")
        
        # Check for String Session (Recommended for Railway/Server)
        if settings.TELEGRAM_STRING_SESSION:
            log.info("Using String Session for Userbot authentication.")
            self.client = TelegramClient(
                StringSession(settings.TELEGRAM_STRING_SESSION), 
                int(self.api_id), 
                self.api_hash
            )
        else:
            log.warning("No String Session found. Falling back to local file session.")
            self.client = TelegramClient('deriv_user_session', int(self.api_id), self.api_hash)
        
        # This will prompt in the terminal only if StringSession is invalid or file session missing
        await self.client.start(phone=self.phone)
        self.is_running = True
        
        # Register the message handler
        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=self.channel_ids))
        
        log.info(f"Userbot Listener active for channels: {self.channel_ids}")
        # Note: We don't run_until_disconnected here because we run in the FastAPI loop

    async def stop(self):
        """Stops the Telethon client."""
        if self.client:
            await self.client.disconnect()
        self.is_running = False
        log.info("Userbot Listener stopped.")

    async def _on_new_message(self, event):
        """Callback for new messages in authorized channels."""
        chat = await event.get_chat()
        chat_id = int(chat.id)
        text = event.raw_text
        
        log.info(f"Userbot detected message from {getattr(chat, 'title', chat.id)}: {text[:50]}...")
        
        chat_title = getattr(chat, 'title', str(chat_id))
        detected_source = chat_title
        
        # Source Detection Logic
        if str(chat_id) == str(settings.TELEGRAM_CHANNEL_ALBURQUERQUE):
            if "TFXC" in text.upper():
                detected_source = f"{chat_title} (TFXC Test)"
            elif any(k in text.upper() for k in ["GOLD PIPS", "HUNTER"]):
                detected_source = f"{chat_title} (Gold Pips Test)"
            else:
                detected_source = f"{chat_title} (Alburquerque Test)"
        else:
            # Direct channel
            if str(chat_id) == str(settings.TELEGRAM_CHANNEL_TFXC):
                detected_source = f"{chat_title} (TFXC Official)"
            elif str(chat_id) == str(settings.TELEGRAM_CHANNEL_GOLD_PIPS):
                detected_source = f"{chat_title} (Gold Pips Official)"

        # Pass to the standard parser
        signal_in = parse_signal(text)
        
        if signal_in:
            log.info(f"Found valid signal via Userbot (Source: {detected_source})")
            signal_in.source = detected_source
            
            # --- REPLY TO SOURCE ---
            status_msg = None
            try:
                status_msg = await event.reply(f"🚀 *Signal Received from {chat_title}:* ` {signal_in.symbol} {signal_in.action} `\nstatus: ` Processing... `")
            except Exception as e:
                log.warning(f"Could not reply to source channel: {e}")
            
            # Execute
            result = await self.executor.process_signal(signal_in)
            status = result.get('status', 'unknown')
            log.info(f"Userbot Trade Result: {status}")
            
            # --- LIVE STATUS EDIT ---
            if status_msg:
                try:
                    icon = "✅" if status in ["executed", "pending_limit"] else "🛑"
                    final_text = f"{icon} *Signal Status:* ` {signal_in.symbol} {signal_in.action} `\nstatus: ` {status.upper()} ` "
                    await status_msg.edit(final_text)
                except Exception as e:
                    log.warning(f"Could not edit source status message: {e}")
        else:
            log.debug("Userbot message did not match signal format.")
