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
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.command_queue = command_queue
        
        self.enabled = bool(self.token and self.chat_id)
        self.running = False
        
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
            
        self.running = True
        self.thread = threading.Thread(
            target=self._run_async_loop,
            name="TelegramManager"
        )
        self.thread.daemon = True
        self.thread.start()
        Logger.info("📡 [TG] Manager Started (Command Listener + Dashboard)")

    def stop(self):
        """Clean shutdown of the bot."""
        if not self.enabled:
            return
            
        Logger.info("📡 [TG] Manager Stopping...")
        self.running = False
        
        try:
            if self.loop and self.loop.is_running() and self.application:
                # Schedule stop within the loop
                future_stop = asyncio.run_coroutine_threadsafe(self.application.stop(), self.loop)
                future_shutdown = asyncio.run_coroutine_threadsafe(self.application.shutdown(), self.loop)
                
                # Wait for them to complete or timeout
                try:
                    future_stop.result(timeout=2)
                    future_shutdown.result(timeout=2)
                except:
                    pass
            
            if self.thread and self.thread.is_alive():
                # Don't join forever, but give it a moment
                self.thread.join(timeout=2)
                
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
        
        # Suppress httpx logs
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        backoff = 5
        
        while self.running:
            try:
                # Initialize bot only if needed
                if not self.application.initialized:
                    self.loop.run_until_complete(self.application.initialize())
                
                print(f"   ✅ Telegram Manager READY (Polling...)")
                self.application.run_polling(
                    stop_signals=None, 
                    drop_pending_updates=True,
                    close_loop=False
                )
            except Exception as e:
                if not self.running:
                    break
                    
                # Specific handling for NetworkError to avoid excessive noise
                Logger.error(f"❌ [TG] Connection Error: {e}")
                print(f"   ⚠️ [TG] Connection lost. Retrying in {backoff}s...")
                import time
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
            finally:
                pass

        # Final cleanup for the loop
        try:
            if self.application:
                self.loop.run_until_complete(self.application.shutdown())
            
            # Cancel all pending tasks
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
            self.loop.close()
        except Exception as e:
            Logger.debug(f"[TG] Cleanup error: {e}")

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
