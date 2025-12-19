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

    def _run_async_loop(self):
        """Main async loop running in background thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Build Application
        self.application = ApplicationBuilder().token(self.token).build()
        
        # Register Command Handlers
        self._register_commands()
        
        # Run Polling (Blocking for this thread)
        # Suppress httpx logs
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        print("   ✅ Telegram Manager READY")
        
        try:
            self.application.run_polling(stop_signals=None, drop_pending_updates=True)
        except Exception as e:
            Logger.error(f"❌ [TG] Loop Error: {e}")

    def _register_commands(self):
        """Register command handlers."""
        app = self.application
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("stop", self._cmd_stop))
        app.add_handler(CommandHandler("help", self._cmd_help))
        # Add others as needed...

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
            "/stop - Shutdown\n",
            parse_mode='Markdown'
        )
