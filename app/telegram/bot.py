from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import os
import asyncio
from loguru import logger as log
from app.deriv.trader import DerivTrader
from app.signals.executor import SignalExecutor

class TelegramBot:
    def __init__(self, token: str, trader: DerivTrader, executor: SignalExecutor):
        self.token = token
        self.trader = trader
        self.executor = executor
        raw_admin_id = os.getenv("TELEGRAM_ADMIN_ID", "0").strip().replace('"', '').replace("'", "")
        self.admin_id = int(raw_admin_id) if raw_admin_id.isdigit() else 0
        # Channel Toggles: Enabled by default
        self.channel_states = {
            os.getenv("TELEGRAM_CHANNEL_TFXC"): True,
            os.getenv("TELEGRAM_CHANNEL_GOLD_PIPS"): True
        }
        self.channel_names = {
            os.getenv("TELEGRAM_CHANNEL_TFXC"): "TFXC SIGNALS UK",
            os.getenv("TELEGRAM_CHANNEL_GOLD_PIPS"): "Gold Pips Hunter"
        }
        self.app = ApplicationBuilder().token(token).build()
        self._setup_handlers()

    def _get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("💰 Balance"), KeyboardButton("📡 Channels")],
            [KeyboardButton("📊 Status"), KeyboardButton("📜 History")],
            [KeyboardButton("❓ Help")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_handler))
        self.app.add_handler(MessageHandler(filters.Text("💰 Balance"), self.balance_handler))
        self.app.add_handler(MessageHandler(filters.Text("📡 Channels"), self.channel_menu_handler))
        self.app.add_handler(MessageHandler(filters.Text("📊 Status"), self.status_handler))
        self.app.add_handler(MessageHandler(filters.Text("📜 History"), self.history_handler))
        self.app.add_handler(MessageHandler(filters.Text("❓ Help"), self.help_handler))
        self.app.add_handler(CallbackQueryHandler(self.toggle_channel_handler, pattern="^toggle_"))
        # Handle messages from channels (Signal Listening)
        self.app.add_handler(MessageHandler(filters.ChatType.CHANNEL | filters.ChatType.SUPERGROUP, self.signal_handler))
        # Handle private command messages
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.message_handler))

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        log.info(f"New Telegram User: {user.id} ({user.username})")
        await update.message.reply_text(
            f"🌟 *Welcome {user.first_name} to Deriv Trading Bot!* 🌟\n\n"
            "I am currently listening to your premium signal channels.\n\n"
            "Use the buttons below to monitor your account!",
            reply_markup=self._get_main_keyboard(),
            parse_mode="Markdown"
        )

    async def channel_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays the channel management menu."""
        buttons = []
        for cid, name in self.channel_names.items():
            if not cid: continue
            state = "🟢 ON" if self.channel_states.get(cid) else "🔴 OFF"
            buttons.append([InlineKeyboardButton(f"{name}: {state}", callback_data=f"toggle_{cid}")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "📡 *Channel Management*\n\nToggle automated trading per channel:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def toggle_channel_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes channel toggle button clicks."""
        query = update.callback_query
        await query.answer()
        cid = query.data.replace("toggle_", "")
        
        current_state = self.channel_states.get(cid, True)
        self.channel_states[cid] = not current_state
        
        # Refresh the menu
        await self.channel_menu_handler(update, context)
        # Note: Since channel_menu_handler sends a NEW message, we might want to edit instead
        # However, for simplicity using existing logic:
        # await query.edit_message_reply_markup(reply_markup=...)

    async def signal_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes incoming messages from channels."""
        chat = update.effective_chat
        cid = str(chat.id)
        
        # 1. Security Check
        if cid not in self.channel_names:
            log.debug(f"Ignoring message from unauthorized chat: {chat.id}")
            return

        # 2. Toggle Check
        if not self.channel_states.get(cid, True):
            log.info(f"Ignoring signal from {self.channel_names[cid]} (Toggled OFF)")
            return

        text = update.effective_message.text
        if not text: return
        
        log.info(f"Incoming Signal from {chat.title}: {text}")
        from app.telegram.parser import parse_signal
        signal_in = parse_signal(text)
        
        if signal_in:
            log.info(f"Parsed Signal Detected: {signal_in.symbol} {signal_in.action}")
            result = await self.executor.process_signal(signal_in)
            
            status_emoji = "✅" if result["status"] == "executed" else "❌"
            msg = (
                f"{status_emoji} *SIGNAL EXECUTED*\n\n"
                f"📡 *Source:* `{self.channel_names[cid]}`\n"
                f"📈 *Asset:* `{signal_in.symbol}`\n"
                f"⚡ *Action:* `{signal_in.action}`\n"
                f"🎯 *Status:* `{result['status']}`"
            )
            if "error" in result:
                msg += f"\n⚠️ *Error:* `{result['error']}`"
            
            # Send notification to admin if trade was attempted
            if self.admin_id:
                try: await self.app.bot.send_message(chat_id=self.admin_id, text=msg, parse_mode="Markdown")
                except Exception as e: log.warning(f"Failed to notify admin: {e}")
        else:
            log.debug("Message did not match signal format.")

    async def balance_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action("typing")
        msg = await self._format_all_balances()
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _format_all_balances(self) -> str:
        """Fetches and formats balances for all accounts."""
        res = await self.trader.client.send_request({"authorize": self.trader.client.token})
        if "authorize" not in res:
            return "❌ Failed to fetch balance. Check your Deriv token."
            
        auth = res["authorize"]
        accounts = auth.get("account_list", [])
        
        # Current Account Balance
        balance = auth.get('balance', 'N/A')
        currency = auth.get('currency', '')
        
        msg = "💳 *Account Balances Summary*\n\n"
        msg += f"🔥 *ACTIVE:* `{auth['loginid']}`\n💰 Balance: `{balance} {currency}`\n\n"
        
        # Other Accounts (List them, but balance might not be in auth details)
        if accounts:
            msg += "📝 *Linked Accounts:*\n"
            for acc in accounts:
                if acc['loginid'] == auth['loginid']: continue
                prefix = "🧪 DEMO" if acc.get('is_virtual') else "💵 REAL"
                # Some account types may have balance already in the list
                acc_bal = acc.get('balance', 'Click to switch')
                msg += f"• {prefix}: `{acc['loginid']}` ({acc_bal})\n"
            
        return msg

    async def status_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action("typing")
        
        # 1. Fetch active portfolio
        port_res = await self.trader.client.send_request({"portfolio": 1})
        contracts = port_res.get("portfolio", {}).get("contracts", [])
        
        if not contracts:
            await update.message.reply_text("📭 *No active trades found.*", parse_mode="Markdown")
            return

        msg = "📊 *Active Trades*\n\n"
        for c in contracts:
            symbol = c.get("symbol", "N/A")
            action = c.get("contract_type", "N/A")
            buy_price = c.get("buy_price", 0)
            # Fetch real-time status for current PnL
            details = await self.trader.check_contract_status(c["contract_id"])
            pnl = details.get("profit", 0) if details else 0
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            
            msg += (
                f"🔹 *{symbol}* ({action})\n"
                f"💰 Buy: `${buy_price}` | {pnl_emoji} PnL: `${pnl}`\n"
                f"🆔 ID: `{c['contract_id']}`\n\n"
            )
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def history_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action("typing")
        stats = await self.executor.get_pnl_stats()
        
        msg = "📜 *Trade History & PnL*\n\n"
        msg += f"🗓 *Last 24h:* `{stats['pnl_24h']} USD`\n"
        msg += f"🗓 *Last 7d:* `{stats['pnl_7d']} USD`\n\n"
        
        msg += "🕒 *Recent Trades:*\n"
        if not stats["recent_trades"]:
            msg += "_No recorded trades yet._"
        else:
            for t in stats["recent_trades"]:
                status_emoji = "✅" if t.status == "won" else "❌" if t.status == "lost" else "⏳"
                pnl_str = f"+{t.profit}" if (t.profit or 0) > 0 else f"{t.profit}"
                msg += f"{status_emoji} `{t.symbol}` | PnL: `{pnl_str}` | `{t.created_at.strftime('%m-%d %H:%M')}`\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "❓ *Deriv Bot Help*\n\n"
            "This bot automatically copies signals from authorized channels and allows manual execution.\n\n"
            "🎮 *Commands:*\n"
            "• 💰 *Balance*: View summary of all linked accounts.\n"
            "• 📡 *Channels*: Toggle signal sources ON/OFF.\n"
            "• 📊 *Status*: View currently open trades and live PnL.\n"
            "• 📜 *History*: View PnL stats and recent trade history.\n\n"
            "📥 *Manual Signals:*\n"
            "Simply forward a message or type a signal in this format:\n"
            "`SELL XAUUSD 4515.1 TP: 4453.7 SL: 4470.7`"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles direct messages to the bot (from Admin)."""
        user = update.effective_user
        text = update.message.text
        if not text: return
        
        # 1. Security Check: Only Admin can execute via DM
        if user.id != self.admin_id:
            log.debug(f"Ignoring DM from non-admin user: {user.id}")
            return

        log.info(f"Admin DM Signal Candidate: {text}")
        
        # 2. Try to parse as signal
        from app.telegram.parser import parse_signal
        signal_in = parse_signal(text)
        
        if signal_in:
            log.info(f"Manual Signal Parsing Success: {signal_in.symbol} {signal_in.action}")
            result = await self.executor.process_signal(signal_in, skip_duplicate_check=True)
            
            if result["status"] == "pending_limit":
                msg = (
                    f"⏳ *LIMIT ORDER PENDING*\n\n"
                    f"📈 *Asset:* `{signal_in.symbol}`\n"
                    f"⚡ *Action:* `{signal_in.action}`\n"
                    f"🎯 *Entry:* `{result['entry_price']}`\n"
                    f"🎯 *Target TP:* `{signal_in.take_profit}`\n\n"
                    f"The bot will execute this trade automatically when the price hits the target."
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
                return

            status_emoji = "✅" if result["status"] == "executed" else "❌"
            msg = (
                f"{status_emoji} *MANUAL SIGNAL EXECUTED*\n\n"
                f"📈 *Asset:* `{signal_in.symbol}`\n"
                f"⚡ *Action:* `{signal_in.action}`\n"
                f"🎯 *Status:* `{result['status']}`"
            )
            if result.get("error"):
                msg += f"\n⚠️ *Reason:* `{result['error']}`"
            elif result.get("reason") and result["status"] != "executed":
                msg += f"\n⚠️ *Reason:* `{result['reason']}`"
                
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            log.debug("DM did not match signal format.")

    async def send_startup_message(self):
        """Sends startup diagnostic to admin."""
        if not self.admin_id: return
        log.info(f"Sending startup message to Admin: {self.admin_id}")
        balance_msg = await self._format_all_balances()
        startup_msg = (
            "🚀 *Deriv Trading Bot Started!*\n\n"
            "Signal monitoring is active for authorized channels.\n\n"
            f"{balance_msg}"
        )
        try: await self.app.bot.send_message(chat_id=self.admin_id, text=startup_msg, parse_mode="Markdown")
        except Exception as e: log.warning(f"Could not send startup message: {e}")

    async def start(self):
        """Initializes and starts the polling loop (Async)."""
        log.info("Starting Telegram Bot (Async)...")
        await self.app.initialize()
        await self.app.updater.start_polling()
        await self.app.start()
        # Post-start tasks
        await self.send_startup_message()

    async def stop(self):
        """Stops the bot (Async)."""
        log.info("Stopping Telegram Bot...")
        try:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        except Exception as e:
            log.warning(f"Error during Telegram Bot shutdown: {e}")

    async def notify_trigger(self, symbol: str, action: str, price: float):
        """Notifies admin that a limit order was triggered."""
        if not self.admin_id: return
        msg = (
            f"🚀 *LIMIT ORDER TRIGGERED*\n\n"
            f"📈 *Asset:* `{symbol}`\n"
            f"⚡ *Action:* `{action}`\n"
            f"🎯 *Trigger Price:* `{price}`\n\n"
            f"The trade was sent to Deriv for execution."
        )
        try:
            # We use self.app.bot because we are outside a direct update context
            await self.app.bot.send_message(chat_id=self.admin_id, text=msg, parse_mode="Markdown")
        except Exception as e:
            log.error(f"Failed to send trigger notification: {e}")
