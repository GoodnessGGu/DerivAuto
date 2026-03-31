from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import TimedOut
import os
import asyncio
from loguru import logger as log
from app.deriv.trader import DerivTrader
from app.signals.executor import SignalExecutor
from app.core.config_service import ConfigManager

class TelegramBot:
    def __init__(self, token: str, trader: DerivTrader, executor: SignalExecutor, config_mgr: ConfigManager):
        self.token = token
        self.trader = trader
        self.executor = executor
        self.config_mgr = config_mgr
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
        # Use custom request object with increased timeouts (30s)
        self.request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        self.app = ApplicationBuilder().token(token).request(self.request).build()
        self._setup_handlers()

    def _get_main_keyboard(self):
        keyboard = [
            [KeyboardButton("💰 Balance"), KeyboardButton("📡 Channels")],
            [KeyboardButton("📊 Status"), KeyboardButton("📜 History")],
            [KeyboardButton("⚙️ Settings"), KeyboardButton("❓ Help")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_handler))
        self.app.add_handler(MessageHandler(filters.Text("💰 Balance"), self.balance_handler))
        self.app.add_handler(MessageHandler(filters.Text("📡 Channels"), self.channel_menu_handler))
        self.app.add_handler(MessageHandler(filters.Text("📊 Status"), self.status_handler))
        self.app.add_handler(MessageHandler(filters.Text("⚙️ Settings"), self.settings_menu_handler))
        self.app.add_handler(MessageHandler(filters.Text("📜 History"), self.history_handler))
        self.app.add_handler(MessageHandler(filters.Text("❓ Help"), self.help_handler))
        self.app.add_handler(CommandHandler("shutdown", self.shutdown_handler))
        self.app.add_handler(CallbackQueryHandler(self.toggle_channel_handler, pattern="^toggle_"))
        self.app.add_handler(CallbackQueryHandler(self.close_trade_callback, pattern="^close_"))
        self.app.add_handler(CallbackQueryHandler(self.refresh_trade_callback, pattern="^refresh_"))
        self.app.add_handler(CallbackQueryHandler(self.adjust_setting_handler, pattern="^set_"))
        self.app.add_handler(CallbackQueryHandler(self.switch_account_handler, pattern="^switch_"))
        
        # Handle private command messages (Manual Signals)
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

    async def balance_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action("typing")
        
        # 1. Fetch config for current account type
        cfg = await self.config_mgr.get_config()
        acc_type = cfg.get("active_account_type", "real").upper()
        
        try:
            msg = await self._format_all_balances()
            
            # 2. Add Switch Button
            target_type = "DEMO" if acc_type == "REAL" else "REAL"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔄 Switch to {target_type}", callback_data=f"switch_{target_type.lower()}")]
            ])
            
            await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")
        except Exception as e:
            log.error(f"Balance check error: {e}")
            await update.message.reply_text("❌ *Error:* Could not fetch balance. The trading server might be reconnecting or busy. Please try again in 10s.", parse_mode="Markdown")

    async def settings_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays the dynamic settings menu."""
        user = update.effective_user
        if user.id != self.admin_id: return

        await update.message.reply_chat_action("typing")
        cfg = await self.config_mgr.get_config()
        
        stake = cfg.get("active_stake", 5.0)
        mult = cfg.get("active_multiplier", 100)
        tsl = "🟢 ON" if cfg.get("trailing_sl_enabled") else "🔴 OFF"
        
        msg = (
            "⚙️ *TRADING SETTINGS*\n\n"
            f"💰 *Default Stake:* `${stake}`\n"
            f"✖️ *Multiplier:* `x{mult}`\n"
            f"📈 *Trailing Stop-Loss:* `{tsl}`\n\n"
            "Use the buttons below to tune your risk:"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("-1", callback_data="set_stake_-1"),
                InlineKeyboardButton("💰 STAKE", callback_data="none"),
                InlineKeyboardButton("+1", callback_data="set_stake_1")
            ],
            [
                InlineKeyboardButton("-10", callback_data="set_mult_-10"),
                InlineKeyboardButton("✖️ MULT", callback_data="none"),
                InlineKeyboardButton("+10", callback_data="set_mult_10")
            ],
            [InlineKeyboardButton(f"TSL: {tsl}", callback_data="set_tsl_toggle")],
            [InlineKeyboardButton("✅ Done", callback_data="set_done")]
        ])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await update.message.reply_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    async def adjust_setting_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback for settings adjustments."""
        query = update.callback_query
        user = query.from_user
        if user.id != self.admin_id: return
        
        data = query.data
        if data == "set_done":
            await query.answer("Settings saved.")
            await query.edit_message_text("✅ *Settings Updated & Saved.*", parse_mode="Markdown")
            return

        cfg = await self.config_mgr.get_config()
        
        if "stake" in data:
            change = float(data.split("_")[-1])
            new_val = max(0.5, cfg.get("active_stake", 5.0) + change)
            await self.config_mgr.update_setting("active_stake", new_val)
        
        elif "mult" in data:
            change = int(data.split("_")[-1])
            new_val = max(10, cfg.get("active_multiplier", 100) + change)
            await self.config_mgr.update_setting("active_multiplier", new_val)
            
        elif "tsl_toggle" in data:
            new_val = not cfg.get("trailing_sl_enabled", False)
            await self.config_mgr.update_setting("trailing_sl_enabled", new_val)
            await query.answer(f"Trailing SL: {'Enabled' if new_val else 'Disabled'}")

        # Refresh the menu
        await self.settings_menu_handler(update, context)

    async def switch_account_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the account switch request."""
        query = update.callback_query
        user = query.from_user
        if user.id != self.admin_id: return
        
        target_type = query.data.replace("switch_", "") # "demo" or "real"
        await query.answer(f"Switching to {target_type.upper()}...")
        
        # 1. Get token from settings
        target_token = settings.DERIV_TOKEN_REAL if target_type == "real" else settings.DERIV_TOKEN_DEMO
        
        if not target_token:
            await query.edit_message_text(f"❌ *Switch Failed:* `DERIV_TOKEN_{target_type.upper()}` not found in .env.")
            return

        # 2. Perform switch in client
        success = await self.trader.client.switch_account(target_token)
        
        if success:
            await self.config_mgr.update_setting("active_account_type", target_type)
            await query.edit_message_text(f"✅ *Successfully switched to {target_type.upper()} account!*")
        else:
            await query.edit_message_text(f"❌ *Switch Failed:* Could not authorize with {target_type.upper()} token.")

    async def _format_all_balances(self) -> str:
        """Fetches and formats balances for all accounts using the authorize command."""
        # 'authorize' is the most reliable way to get both balance and the full account list
        res = await self.trader.client.send_request({"authorize": self.trader.client.token})
        
        if "authorize" not in res:
            return "❌ Failed to fetch balance. Trading server may be unreachable."
            
        auth = res["authorize"]
        accounts = auth.get("account_list", [])
        accounts = auth.get("account_list", [])
        
        # Current Account Balance
        balance = auth.get('balance', 'N/A')
        currency = auth.get('currency', '')
        
        msg = "💳 *Account Balances Summary*\n\n"
        msg += f"🔥 *ACTIVE:* `{auth.get('loginid', 'Unknown')}`\n💰 Balance: `{balance} {currency}`\n\n"
        
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
        
        try:
            # 1. Fetch active portfolio
            port_res = await self.trader.client.send_request({"portfolio": 1})
            contracts = port_res.get("portfolio", {}).get("contracts", [])
            
            if not contracts:
                await update.message.reply_text("📭 *No active trades found.*", parse_mode="Markdown")
                return
        except Exception as e:
            log.error(f"Status check error: {e}")
            await update.message.reply_text("❌ *Error:* Could not fetch active trades. The server might be busy.", parse_mode="Markdown")
            return

        for c in contracts:
            contract_id = c["contract_id"]
            # Fetch real-time status for full details
            details = await self.trader.check_contract_status(contract_id)
            if not details: continue
            
            text, keyboard = self._format_trade_status(details)
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
        
        return

    def _format_trade_status(self, details: dict):
        """Standardized formatter for an active trade status message."""
        import time
        from datetime import datetime
        
        symbol = details.get("display_name", details.get("symbol", "N/A"))
        action = details.get("contract_type", "N/A")
        contract_id = details["contract_id"]
        buy_price = float(details.get("buy_price", 0))
        entry_price = float(details.get("entry_tick", 0))
        current_profit = float(details.get("profit", 0))
        pnl_pct = (current_profit / buy_price * 100) if buy_price > 0 else 0
        pnl_emoji = "📈" if current_profit >= 0 else "📉"
        
        # Calculation for duration timer
        start_time = details.get("purchase_time", int(time.time()))
        duration_sec = int(time.time()) - int(start_time)
        duration_str = f"{duration_sec // 60:02d}m {duration_sec % 60:02d}s"
        
        # Target/Limit info
        limit_order = details.get("limit_order", {})
        tp_raw = limit_order.get("take_profit")
        
        # Handle cases where Deriv returns a dict for take_profit
        tp_amount = tp_raw.get("order_amount") if isinstance(tp_raw, dict) else tp_raw
        tp_price = tp_raw.get("value") if isinstance(tp_raw, dict) else None
        
        target_info = f"+${tp_amount}" if tp_amount else "None"
        if tp_price: target_info += f" (@{tp_price})"
        
        msg = (
            f"📊 *{symbol}* ({action})\n"
            f"────────────────────\n"
            f"💰 *Entry:* `${entry_price:.5f}` | 💵 *Stake:* `${buy_price}`\n"
            f"{pnl_emoji} *PnL:* `${current_profit:.2f}` (*{pnl_pct:+.1f}%*)\n"
            f"🎯 *Target:* `{target_info}`\n"
            f"⏱️ *Active:* `{duration_str}` | 🆔 `{contract_id}`"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{contract_id}"),
                InlineKeyboardButton("❌ Close Trade", callback_data=f"close_{contract_id}")
            ]
        ])
        
        return msg, keyboard

    async def refresh_trade_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes the 'Refresh' button click on an active trade."""
        query = update.callback_query
        contract_id = int(query.data.replace("refresh_", ""))
        
        # Fetch fresh details
        details = await self.trader.check_contract_status(contract_id)
        
        if not details or details.get("is_sold"):
            await query.answer("Trade is already closed.")
            await query.edit_message_text("✅ *Trade has closed.*", parse_mode="Markdown")
            return

        text, keyboard = self._format_trade_status(details)
        
        try:
            # Only edit if content actually changed to avoid flicker/errors
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            await query.answer("Updated.")
        except Exception:
            # If nothing changed, edit_message_text raises an error
            await query.answer("Already up to date.")

    async def history_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_chat_action("typing")
        stats = await self.executor.get_pnl_stats()
        
        d = stats["daily"]
        w = stats["weekly"]
        
        msg = "📊 *TRADE PERFORMANCE DASHBOARD* 📊\n\n"
        
        # Daily Section
        msg += "📅 *DAILY SUMMARY (24H)*\n"
        msg += f"💰 Profit: `{d['profit']} USD`\n"
        msg += f"📈 Win Rate: `{d['win_rate']}%` (`{d['wins']}W` - `{d['losses']}L`)\n"
        msg += f"🔢 Total Trades: `{d['total']}`\n\n"
        
        # Weekly Section
        msg += "📅 *WEEKLY SUMMARY (7D)*\n"
        msg += f"💰 Profit: `{w['profit']} USD`\n"
        msg += f"📈 Win Rate: `{w['win_rate']}%` (`{w['wins']}W` - `{w['losses']}L`)\n"
        msg += f"🔢 Total Trades: `{w['total']}`\n\n"
        
        # Recent Trades List
        msg += "🕒 *RECENT TRADE LOG:*\n"
        if not stats["recent_trades"]:
            msg += "_No recorded trades found._"
        else:
            for t in stats["recent_trades"]:
                status_emoji = "🟩" if t.status == "won" else "🟥" if t.status == "lost" else "⏳"
                pnl_val = t.profit or 0
                pnl_str = f"+{pnl_val}" if pnl_val > 0 else f"{pnl_val}"
                
                # Format time
                time_str = t.created_at.strftime('%H:%M')
                msg += f"{status_emoji} `{t.symbol}` | PnL: `{pnl_str}` | `{time_str}`\n"
        
        msg += "\n" + "_" * 20 + "\n"
        msg += "💡 *Tip:* Use /shutdown to stop the bot remotely."
        
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "❓ *Deriv Bot Help*\n\n"
            "This bot uses a **Hybrid System**:\n"
            "1. **Userbot (Telethon)**: Listens to *any* channel you are a member of.\n"
            "2. **Standard Bot**: Handles your menu/buttons and manual signals.\n\n"
            "🎮 *Commands:*\n"
            "• 💰 *Balance*: View summary of all linked accounts.\n"
            "• 📡 *Channels*: Toggle automated listening for specific sources.\n"
            "• 📊 *Status*: View currently open trades and live PnL.\n"
            "• 📜 *History*: View PnL stats and recent trade history.\n"
            "• 🛑 */shutdown*: Gracefully stop the bot process.\n\n"
            "📥 *Manual Signals:*\n"
            "Simply type or forward a signal here:\n"
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
        """Sends startup diagnostic to admin with fault tolerance."""
        if not self.admin_id: return
        try:
            log.info(f"Preparing startup message for Admin: {self.admin_id}")
            # Try to fetch balance, but don't fail if it takes too long
            try:
                # Increased timeout to 25s for startup handshake
                balance_msg = await asyncio.wait_for(self._format_all_balances(), timeout=25.0)
            except Exception as e:
                log.warning(f"Startup balance check timed out: {e}")
                balance_msg = "⚠️ Balance check pending (Connection establishing...)"
                
            startup_msg = (
                "🚀 *Deriv Trading Bot System Started!*\n\n"
                "✅ *Userbot (Listener):* Active\n"
                "✅ *Standard Bot (UI):* Active\n\n"
                f"{balance_msg}"
            )
            await self.app.bot.send_message(chat_id=self.admin_id, text=startup_msg, parse_mode="Markdown")
        except Exception as e:
            log.warning(f"Could not send startup message: {e}")

    async def start(self):
        """Initializes and starts the polling loop with retries for stability."""
        log.info("Starting Telegram Bot (Async)...")
        
        for attempt in range(3):
            try:
                await self.app.initialize()
                await self.app.updater.start_polling()
                await self.app.start()
                # Post-start tasks
                await self.send_startup_message()
                log.info("Telegram Bot active and polling.")
                break
            except TimedOut as e:
                if attempt == 2:
                    log.error(f"Final attempt failed: Telegram Connection Timed Out. {e}")
                    raise
                log.warning(f"Telegram Connection Timed Out (Attempt {attempt+1}/3). Retrying in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"Failed to start Telegram Bot: {e}")
                raise

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

    async def close_trade_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes the 'Close Trade' button click."""
        query = update.callback_query
        user = query.from_user
        
        # 1. Security Check
        if user.id != self.admin_id:
            await query.answer("⚠️ Action unauthorized.")
            return

        contract_id_str = query.data.replace("close_", "")
        contract_id = int(contract_id_str)
        
        await query.answer("Closing trade...")
        log.info(f"Manual Close Request: {contract_id}")

        # 2. Execute sell
        res = await self.trader.sell_contract(contract_id)
        
        if res.get("error"):
            await query.edit_message_text(
                f"❌ *Failed to close trade!*\n🆔 ID: `{contract_id}`\n⚠️ Reason: `{res['error'].get('message')}`",
                parse_mode="Markdown"
            )
            return

        # 3. Successful Sell
        sell_info = res.get("sell", {})
        profit = sell_info.get("sold_for", 0) - sell_info.get("buy_price", 0)
        pnl_emoji = "✅" if profit >= 0 else "🛑"
        
        await query.edit_message_text(
            f"{pnl_emoji} *TRADE CLOSED MANUALLY*\n\n"
            f"🆔 ID: `{contract_id}`\n"
            f"💰 Buy: `${sell_info.get('buy_price')}`\n"
            f"💰 Sell: `${sell_info.get('sold_for')}`\n"
            f"📈 Final PnL: *${round(profit, 2)}*",
            parse_mode="Markdown"
        )

    async def shutdown_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processes the /shutdown command."""
        user = update.effective_user
        
        # 1. Security Check
        if user.id != self.admin_id:
            log.warning(f"Unauthorized shutdown attempt by {user.id}")
            return

        log.info("Shutdown command received from Admin.")
        await update.message.reply_text(
            "🛑 *SHUTDOWN INITIATED*\n\nStopping all components and terminating process...",
            parse_mode="Markdown"
        )
        
        # Trigger graceful exit via SIGINT (allows FastAPI lifespan to clean up)
        import signal
        os.kill(os.getpid(), signal.SIGINT)
