"""
V1.0: Unified Telegram Manager
==============================
Handles all Telegram interactions:
1. Command Listening (via Daemon)
2. Alert Sending (Async)
3. Live Dashboard Beaming (Message Editing)

Replaces:
- src/shared/system/telegram_listener.py
- src/utils/notifications.py
- src/arbiter/monitoring/telegram_alerts.py
"""

import os
import asyncio
import threading
import queue
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import BadRequest

from src.shared.system.logging import Logger

# Command Constants (Shared with system)
CMD_STATUS_REPORT = "STATUS_REPORT"
CMD_STOP_ENGINE = "STOP_ENGINE"
CMD_SET_MODE = "SET_MODE"
CMD_SET_SIZE = "SET_SIZE"
CMD_SET_BUDGET = "SET_BUDGET"

class TelegramManager:
    """
    Unified manager for Telegram interactions.
    """
    
    def __init__(self, command_queue: Optional[queue.Queue] = None):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.command_queue = command_queue
        
        self.enabled = bool(self.token and self.token != "YOUR_BOT_TOKEN_HERE")
        
        # Dashboard State
        self.dashboard_message_id: Optional[int] = None
        self.last_dashboard_content: str = ""
        
        # Async Loop for Bot
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.application = None
        self.thread: Optional[threading.Thread] = None
        
        if not self.enabled:
            Logger.warning("⚠️ TG Manager: No Token. Telegram disabled.")

    def start(self):
        """Start the async bot thread."""
        if not self.enabled or self.thread:
            return
            
        self.thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True,
            name="TelegramManager"
        )
        self.thread.start()
        Logger.info("📡 [TG] Manager Started (Command Listener + Dashboard)")

    def stop(self):
        """Clean shutdown of the bot."""
        if not self.enabled or not self.application:
            return
            
        Logger.info("📡 [TG] Manager Stopping...")
        try:
            if self.loop and self.application:
                # Stop polling first
                asyncio.run_coroutine_threadsafe(self.application.stop(), self.loop)
                asyncio.run_coroutine_threadsafe(self.application.shutdown(), self.loop)
                
                # Give it a moment to stop
                time.sleep(1)
                
            self.thread = None
            Logger.info("📡 [TG] Manager Stopped.")
        except Exception as e:
            Logger.debug(f"[TG] Stop Error: {e}")

    def _run_async_loop(self):
        """Main async loop running in background thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Build Application
        self.application = ApplicationBuilder().token(self.token).build()
        
        # Register Command Handlers
        self._register_commands()
        
        # Run Polling (Blocking for this thread) with self-healing loop
        # Suppress httpx logs
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        import time
        backoff = 5
        
        while self.running:
            try:
                print(f"   ✅ Telegram Manager READY (Polling...)")
                self.application.run_polling(
                    stop_signals=None, 
                    drop_pending_updates=True,
                    close_loop=False
                )
            except Exception as e:
                if not self.running:
                    break
                    
                Logger.error(f"❌ [TG] Loop Error: {e}")
                print(f"   ⚠️ [TG] Connection lost. Retrying in {backoff}s...")
                time.sleep(backoff)
                
                # Exponential backoff up to 60s
                backoff = min(backoff * 2, 60)
                
                # Re-initialize application if needed
                try:
                    # In some cases we might need to recreate the application
                    # but usually run_polling can just be restarted.
                    pass
                except:
                    pass

    def _register_commands(self):
        """Register command handlers."""
        app = self.application
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("stop", self._cmd_stop))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("clean", self._cmd_clean))

    # ═══════════════════════════════════════════════════════════════════
    # PUBLIC METHODS (Thread-Safe Bridge)
    # ═══════════════════════════════════════════════════════════════════

    def send_alert(self, message: str):
        """Send a new message (Thread-safe)."""
        if not self.enabled or not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self._async_send(message), self.loop)

    def update_dashboard(self, content: str):
        """Update the persistent dashboard message (Thread-safe)."""
        if not self.enabled or not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self._async_update_dashboard(content), self.loop)

    # ═══════════════════════════════════════════════════════════════════
    # ASYNC IMPLEMENTATION
    # ═══════════════════════════════════════════════════════════════════

    async def _async_send(self, message: str):
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id, 
                text=message, 
                parse_mode='HTML'
            )
        except Exception as e:
            Logger.debug(f"[TG] Send Error: {e}")

    async def _async_update_dashboard(self, content: str):
        """Edit existing message or send new one."""
        formatted = content  # Caller handles formatting now
        
        # Skip if identical (avoids API errors)
        if formatted == self.last_dashboard_content:
            return
            
        try:
            if self.dashboard_message_id:
                try:
                    await self.application.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.dashboard_message_id,
                        text=formatted,
                        parse_mode='MarkdownV2'
                    )
                    self.last_dashboard_content = formatted
                    return
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        return
                    # If message was deleted or too old, reset
                    self.dashboard_message_id = None
            
            # Send new if no ID or edit failed
            msg = await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=formatted,
                parse_mode='MarkdownV2'
            )
            self.dashboard_message_id = msg.message_id
            self.last_dashboard_content = formatted
            
        except Exception as e:
            Logger.debug(f"[TG] Dashboard Error: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # COMMAND HANDLERS
    # ═══════════════════════════════════════════════════════════════════

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📶 Status: ONLINE")
        if self.command_queue:
            self.command_queue.put(CMD_STATUS_REPORT)

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🛑 Stopping Engine...")
        if self.command_queue:
            self.command_queue.put(CMD_STOP_ENGINE)
            
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 *PHANTOM COMMANDS*\n"
            "/status - System check\n"
            "/stop - Shutdown\n"
            "/clean <TOKEN|all> - Dump tokens to USDC\n",
            parse_mode='Markdown'
        )

    async def _cmd_clean(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Clean wallet via Telegram.
        Usage: /clean BONK or /clean all
        """
        args = context.args
        
        if not args:
            await update.message.reply_text("❌ Usage: /clean <TOKEN> or /clean all")
            return
            
        target = args[0].upper()
        await update.message.reply_text(f"🧹 Starting cleanup: {target}...")
        
        try:
            from src.shared.execution.wallet import WalletManager
            from src.shared.execution.swapper import JupiterSwapper
            from config.settings import Settings
            
            Settings.ENABLE_TRADING = True
            wallet = WalletManager()
            
            if not wallet.keypair:
                await update.message.reply_text("❌ No wallet key loaded!")
                return
                
            swapper = JupiterSwapper(wallet)
            targets = []
            
            if target == "ALL":
                tokens = wallet.get_all_token_accounts()
                for mint, bal in tokens.items():
                    if mint != Settings.USDC_MINT and bal > 0:
                        targets.append(mint)
            else:
                # Resolve symbol
                if target in Settings.ASSETS:
                    targets.append(Settings.ASSETS[target])
                elif len(target) > 30:
                    targets.append(target)
                else:
                    await update.message.reply_text(f"❌ Unknown token: {target}")
                    return
            
            if not targets:
                await update.message.reply_text("✨ Nothing to clean!")
                return
                
            results = []
            for mint in targets:
                info = wallet.get_token_info(mint)
                if not info:
                    continue
                    
                symbol = "?"
                for k, v in Settings.ASSETS.items():
                    if v == mint:
                        symbol = k
                        break
                        
                tx = swapper.execute_swap(
                    direction="SELL",
                    amount_usd=0,
                    reason="TG Clean",
                    target_mint=mint,
                    priority_fee=100000
                )
                
                if tx:
                    results.append(f"✅ {symbol}")
                else:
                    results.append(f"❌ {symbol}")
                    
                await asyncio.sleep(1.0)
            
            await update.message.reply_text(
                f"🧹 Cleanup Complete!\n" + "\n".join(results)
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
