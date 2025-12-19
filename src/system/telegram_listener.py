"""
V14.0: Telegram Command Listener Daemon
=======================================
Async daemon that listens for Telegram commands (/status, /stop)
and pipes them to the main TradingCore loop via a shared queue.

Architecture:
- Runs in a separate thread (asyncio event loop)
- Uses python-telegram-bot ApplicationBuilder
- Non-blocking (Polling)
"""

import os
import asyncio
import threading
import queue
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from src.system.logging import Logger

# Command constants
CMD_STATUS_REPORT = "STATUS_REPORT"
CMD_STOP_ENGINE = "STOP_ENGINE"
CMD_SET_MODE = "SET_MODE"     # Args: "live" or "monitor"
CMD_SET_SIZE = "SET_SIZE"     # Args: float amount
CMD_SET_BUDGET = "SET_BUDGET" # Args: float amount
CMD_TEST_CEX = "CMD_TEST_CEX" # V44.0: CEX tunnel test
CMD_TEST_DRIFT = "CMD_TEST_DRIFT"  # Drift Protocol tunnel test
CMD_CHECK_DRIFT = "CMD_CHECK_DRIFT"  # Drift account health check
# V45.0: Landlord Strategy Commands
CMD_START_LANDLORD = "CMD_START_LANDLORD"
CMD_CLOSE_LANDLORD = "CMD_CLOSE_LANDLORD"
CMD_LANDLORD_STATUS = "CMD_LANDLORD_STATUS"
# JLP Monitoring Commands
CMD_SET_JLP = "CMD_SET_JLP"
CMD_JLP_STATUS = "CMD_JLP_STATUS"
# V47.0: ML Retraining
CMD_RETRAIN_ML = "CMD_RETRAIN_ML"
# V48.0: Performance Reporting
CMD_PERFORMANCE = "CMD_PERFORMANCE"
# V67.7: Swarm Status
CMD_SWARM_STATUS = "CMD_SWARM_STATUS"

class TelegramListenerDaemon:
    """
    Async daemon for receiving Telegram commands.
    """
    
    def __init__(self, command_queue: queue.Queue):
        self.command_queue = command_queue
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.running = False
        self.thread = None
        
        if not self.token or self.token == "YOUR_BOT_TOKEN_HERE":
            Logger.warning("⚠️ TG Listener: No Token. Remote control disabled.")
            self.enabled = False
        else:
            self.enabled = True

    def start(self):
        """Start the async listener in a background thread."""
        if not self.enabled or self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True,
            name="TelegramListener"
        )
        self.thread.start()
        Logger.info("📡 [LISTENER] Telegram Command Listener Started")

    def _run_async_loop(self):
        """Entry point for the async event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Build Application
        application = ApplicationBuilder().token(self.token).build()
        
        # Register Handlers
        application.add_handler(CommandHandler("status", self._cmd_status))
        application.add_handler(CommandHandler("stop", self._cmd_stop))
        
        # V14.1/14.2 Remote Controls
        application.add_handler(CommandHandler("mode", self._cmd_mode))
        application.add_handler(CommandHandler("size", self._cmd_size))
        application.add_handler(CommandHandler("risk", self._cmd_risk))
        application.add_handler(CommandHandler("budget", self._cmd_budget))
        
        # V44.0: CEX Test Command
        application.add_handler(CommandHandler("test_cex", self._cmd_test_cex))
        
        # Drift Protocol Commands (Solana Derivatives)
        application.add_handler(CommandHandler("test_drift", self._cmd_test_drift))
        application.add_handler(CommandHandler("check_drift", self._cmd_check_drift))
        
        # V45.0: Landlord Strategy Commands
        application.add_handler(CommandHandler("start_landlord", self._cmd_start_landlord))
        application.add_handler(CommandHandler("close_landlord", self._cmd_close_landlord))
        application.add_handler(CommandHandler("landlord", self._cmd_landlord_status))
        
        # JLP Monitoring Commands
        application.add_handler(CommandHandler("set_jlp", self._cmd_set_jlp))
        application.add_handler(CommandHandler("jlp", self._cmd_jlp_status))
        
        # V47.0: ML Retraining
        application.add_handler(CommandHandler("retrain_ml", self._cmd_retrain))
        
        # V48.0: Performance Reporting
        application.add_handler(CommandHandler("performance", self._cmd_performance))
        
        # V67.7: Swarm & Ping Commands
        application.add_handler(CommandHandler("ping", self._cmd_ping))
        application.add_handler(CommandHandler("swarm", self._cmd_swarm))
        
        # V74.0: Help Command
        application.add_handler(CommandHandler("help", self._cmd_help))
        
        # Run Polling
        # Note: run_polling is blocking, so this thread stays alive
        # To stop cleanly, we'd need more complex logic, but daemon=True handles exit.
        # We suppress httpx logging which is verbose by default
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        # V74.0: Print confirmation that listener is ready
        print("   ✅ Telegram Listener READY - Accepting Commands")
        
        try:
            application.run_polling(stop_signals=None, drop_pending_updates=True)  # V38.3: Skip old queued commands
        except Exception as e:
            Logger.error(f"❌ [LISTENER] Error: {e}")

    # ==========================
    # V38.3: User Authentication
    # ==========================
    
    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to send commands."""
        allowed_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
        if not allowed_id:
            # No restriction set - allow all (development mode)
            return True
        try:
            return str(user_id) == allowed_id
        except:
            return False
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            user = update.effective_user
            # V74.1: Higher Priority Visibility
            Logger.success(f"📡 [TG CMD] /status received from {user.first_name}")
            
            # Ack to user immediately
            await update.message.reply_text("🚨 Priority Command Received: Fetching status...")
        except Exception as e:
            Logger.warning(f"⚠️ [LISTENER] Ack failed: {e}")
            
        # Push to queue for Core execution (Unconditional)
        self.command_queue.put(CMD_STATUS_REPORT)
        Logger.info(f"📨 [TG CMD] STATUS_REPORT pushed to queue (High Priority)")

    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command. V38.3: Requires authorization."""
        user = update.effective_user
        
        # V38.3: Authorization check
        if not self._is_authorized(user.id):
            Logger.warning(f"🚫 [LISTENER] UNAUTHORIZED /stop from {user.first_name} (ID: {user.id})")
            await update.message.reply_text("🚫 Unauthorized. Your user ID is not allowed.")
            return
        
        try:
            Logger.warning(f"🛑 [LISTENER] Command /stop from {user.first_name} (ID: {user.id})")
            await update.message.reply_text("🛑 STOP CMD RECEIVED. Shutting down engine...")
        except Exception: pass
        
        self.command_queue.put(CMD_STOP_ENGINE)
        
    async def _cmd_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mode [live|monitor]"""
        try:
            if not context.args:
                await update.message.reply_text("Usage: /mode [live|monitor]")
                return
                
            mode = context.args[0].lower()
            if mode not in ["live", "monitor"]:
                await update.message.reply_text("Invalid mode. Use 'live' or 'monitor'.")
                return
                
            await update.message.reply_text(f"⚙️ Switching mode to: {mode.upper()}...")
        except Exception: pass
        
        self.command_queue.put(f"{CMD_SET_MODE}:{mode}")

    async def _cmd_size(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /size [amount]"""
        if not context.args:
            await update.message.reply_text("Usage: /size [amount_usd]")
            return
            
        try:
            amount = float(context.args[0])
            await update.message.reply_text(f"📉 Setting Position Size to ${amount}...")
            self.command_queue.put(f"{CMD_SET_SIZE}:{amount}")
        except ValueError:
            await update.message.reply_text("Invalid amount.")

    async def _cmd_budget(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /budget [amount]"""
        if not context.args:
            await update.message.reply_text("Usage: /budget [total_exposure_usd]")
            return
            
        try:
            amount = float(context.args[0])
            await update.message.reply_text(f"💰 Setting Risk Budget to ${amount}...")
            self.command_queue.put(f"{CMD_SET_BUDGET}:{amount}")
        except ValueError:
            await update.message.reply_text("Invalid amount.")

    async def _cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk [off] -> Sets size to 0"""
        if context.args and context.args[0].lower() == "off":
            await update.message.reply_text("🛡️ RISK OFF: Setting Position Size to $0")
            self.command_queue.put(f"{CMD_SET_SIZE}:0")
        else:
            await update.message.reply_text("Usage: /risk off")
    
    async def _cmd_test_cex(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test_cex - V44.0: Execute tiny CEX trade to verify tunnel."""
        user = update.effective_user
        
        # Authorization check
        if not self._is_authorized(user.id):
            Logger.warning(f"🚫 [LISTENER] UNAUTHORIZED /test_cex from {user.first_name} (ID: {user.id})")
            await update.message.reply_text("🚫 Unauthorized. This command requires authorization.")
            return
        
        Logger.warning(f"🧪 [LISTENER] Command /test_cex from {user.first_name} (ID: {user.id})")
        await update.message.reply_text("🧪 CEX Tunnel Test initiated...")
        
        self.command_queue.put(CMD_TEST_CEX)
    
    async def _cmd_test_drift(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test_drift - Execute tiny Drift trade to verify Solana derivatives tunnel."""
        user = update.effective_user
        
        # Authorization check
        if not self._is_authorized(user.id):
            Logger.warning(f"🚫 [LISTENER] UNAUTHORIZED /test_drift from {user.first_name} (ID: {user.id})")
            await update.message.reply_text("🚫 Unauthorized. This command requires authorization.")
            return
        
        Logger.warning(f"🧪 [LISTENER] Command /test_drift from {user.first_name} (ID: {user.id})")
        await update.message.reply_text("🧪 Drift Tunnel Test initiated (Solana Derivatives)...")
        
        self.command_queue.put(CMD_TEST_DRIFT)
    
    async def _cmd_check_drift(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check_drift - Non-destructive Drift account health check."""
        user = update.effective_user
        Logger.info(f"🔍 [LISTENER] Command /check_drift from {user.first_name}")
        await update.message.reply_text("🔍 Checking Drift account health...")
        
        self.command_queue.put(CMD_CHECK_DRIFT)
    
    async def _cmd_start_landlord(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start_landlord [size_usd] - Open delta-neutral hedge."""
        user = update.effective_user
        
        # Authorization check
        if not self._is_authorized(user.id):
            Logger.warning(f"🚫 [LISTENER] UNAUTHORIZED /start_landlord from {user.first_name}")
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        # Get size argument
        size = 100.0
        if context.args:
            try:
                size = float(context.args[0])
            except ValueError:
                await update.message.reply_text("Usage: /start_landlord [size_usd]")
                return
        
        Logger.info(f"🏠 [LISTENER] Command /start_landlord ${size} from {user.first_name}")
        await update.message.reply_text(f"🏠 Starting Landlord: ${size} hedge...")
        
        self.command_queue.put(f"{CMD_START_LANDLORD}:{size}")
    
    async def _cmd_close_landlord(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close_landlord - Close all hedge positions."""
        user = update.effective_user
        
        # Authorization check
        if not self._is_authorized(user.id):
            Logger.warning(f"🚫 [LISTENER] UNAUTHORIZED /close_landlord from {user.first_name}")
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        Logger.info(f"🏠 [LISTENER] Command /close_landlord from {user.first_name}")
        await update.message.reply_text("🏠 Closing Landlord hedge...")
        
        self.command_queue.put(CMD_CLOSE_LANDLORD)
    
    async def _cmd_landlord_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /landlord - Get current Landlord status."""
        user = update.effective_user
        Logger.info(f"🏠 [LISTENER] Command /landlord from {user.first_name}")
        await update.message.reply_text("🏠 Fetching Landlord status...")
        
        self.command_queue.put(CMD_LANDLORD_STATUS)
    
    async def _cmd_set_jlp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_jlp [price] [quantity] - Set JLP entry for monitoring."""
        user = update.effective_user
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /set_jlp [entry_price] [quantity]\nExample: /set_jlp 2.85 3.5")
            return
        
        try:
            price = float(context.args[0])
            quantity = float(context.args[1])
            Logger.info(f"🏠 [LISTENER] Command /set_jlp ${price} x {quantity} from {user.first_name}")
            await update.message.reply_text(f"🏠 Setting JLP: {quantity:.4f} @ ${price:.4f}...")
            
            self.command_queue.put(f"{CMD_SET_JLP}:{price}:{quantity}")
        except ValueError:
            await update.message.reply_text("Invalid numbers. Usage: /set_jlp [price] [quantity]")
    
    async def _cmd_jlp_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /jlp - Get current JLP status and P/L."""
        user = update.effective_user
        Logger.info(f"🏠 [LISTENER] Command /jlp from {user.first_name}")
        await update.message.reply_text("🏠 Fetching JLP status...")
        
        self.command_queue.put(CMD_JLP_STATUS)
        
    async def _cmd_retrain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /retrain_ml - Trigger manual ML model retraining."""
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        await update.message.reply_text("🧠 Triggering ML retraining... (Check logs/notifications for result)")
        self.command_queue.put(CMD_RETRAIN_ML)

    async def _cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance - Generate on-demand performance report."""
        if not self._is_authorized(update.effective_user.id): 
            await update.message.reply_text("🚫 Unauthorized.")
            return
        
        await update.message.reply_text("📊 Generating performance report...")
        self.command_queue.put(CMD_PERFORMANCE)
    
    async def _cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """V67.7: Handle /ping - Verify bot is responsive."""
        import time
        uptime = "Unknown"
        await update.message.reply_text(f"🏓 Pong! Bot is alive. ⏰ {time.strftime('%H:%M:%S')}")
        Logger.info(f"🏓 [LISTENER] /ping from {update.effective_user.first_name}")
    
    async def _cmd_swarm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """V67.7: Handle /swarm - Get all agent statuses."""
        user = update.effective_user
        print(f"   📡 [TG CMD] /swarm received from {user.first_name}")
        Logger.info(f"🐝 [LISTENER] Command /swarm from {user.first_name}")
        await update.message.reply_text("🐝 Fetching Swarm status...")
        
        self.command_queue.put(CMD_SWARM_STATUS)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """V74.0: Handle /help - List all available commands."""
        user = update.effective_user
        print(f"   📡 [TG CMD] /help received from {user.first_name}")
        Logger.info(f"❓ [LISTENER] Command /help from {user.first_name}")
        
        help_text = """
📖 *PHANTOM TRADER - AVAILABLE COMMANDS*

*System Status*
/status - Get full system status
/ping - Verify bot is responsive
/swarm - Get all agent statuses
/performance - Generate performance report

*Trading Controls*
/mode [live|monitor] - Set trading mode
/size [amount] - Set position size (USD)
/budget [amount] - Set daily budget
/risk [1-10] - Set risk level

*Landlord Strategy*
/start_landlord - Start Landlord position
/close_landlord - Close Landlord position
/landlord - Get Landlord status

*JLP Monitoring*
/set_jlp [amount] - Set JLP position
/jlp - Get JLP status

*ML & Advanced*
/retrain_ml - Trigger ML retraining

*System*
/stop - ⚠️ Shutdown engine (authorized)
/help - Show this help message

_V74.0 Phantom Trader_
"""
        await update.message.reply_text(help_text, parse_mode="Markdown")
