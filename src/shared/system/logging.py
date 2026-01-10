"""
V60.0: High-Fidelity Logger (Loguru + Rich)
===========================================
Advanced logging with beautiful terminal output and real-time SignalBus streaming.

Usage:
    from src.shared.system.logging import Logger
    Logger.info("[SYSTEM] Initializing")
"""

import sys
import os
from datetime import datetime
from loguru import logger
from rich.logging import RichHandler
from rich.console import Console

# --- Setup Constants ---
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs"
)
os.makedirs(LOG_DIR, exist_ok=True)

_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(LOG_DIR, f"phantom_{_run_id}.log")
ENGINE_LOG_PATH = os.path.join(LOG_DIR, "engine_runtime.log")

# --- Source Icons ---
SOURCE_ICONS = {
    "SYSTEM": "🛸", "BROKER": "📊", "ORCA": "🐋", "DISCOVERY": "🔍",
    "TRADE": "💰", "ML": "🧠", "SCOUT": "🏹", "PRIMARY": "Ⓜ️",
    "SCALPER": "⚡", "LANDLORD": "🏠", "CAPITAL": "💵", "WSS": "📡",
    "DSM": "📈", "REPORT": "📋", "LIQUIDITY": "💧", "COMMS": "📣",
}

# --- SignalBus Sink ---
def signal_bus_sink(message):
    """Loguru sink that forwards logs to the SignalBus."""
    try:
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        
        record = message.record
        level = record["level"].name
        text = record["message"]
        
        # Extract source if present: "[SOURCE] Message"
        source = "SYSTEM"
        if text.startswith("[") and "]" in text:
            source = text[1:text.index("]")].upper()
            text = text[text.index("]") + 1:].strip()
            
        signal_bus.emit(Signal(
            type=SignalType.LOG_UPDATE,
            source=source,
            data={"level": level, "message": text}
        ))
        
        # Also feed AppState for TUI legacy
        from src.shared.state.app_state import state
        if level in ["INFO", "WARNING", "ERROR", "SUCCESS", "CRITICAL"]:
            state.log(f"[{source}] {text}")
        if level in ["ERROR", "CRITICAL"]:
            state.flash_error(f"[{source}] {text}")
            
    except Exception:
        pass

# --- Initialize Loguru ---
config = {
    "handlers": [
        # 1. Rich Console Sink (High-Fidelity)
        {
            "sink": RichHandler(
                console=Console(width=120),
                rich_tracebacks=True,
                markup=True,
                show_time=True,
                show_level=True,
                show_path=False
            ),
            "format": "{message}",
            "level": "INFO",
        },
        # 2. File Sink (Rotation/Cleanup)
        {
            "sink": log_file,
            "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            "level": "INFO",
            "rotation": "10 MB",
            "retention": "3 days",
            "compression": "zip",
        },
        # 3. Reactive SignalBus Sink
        {
            "sink": signal_bus_sink,
            "level": "INFO",
        }
    ]
}

logger.configure(**config)

class Logger:
    """Backward-compatible wrapper for Loguru."""
    
    _silent = False

    @staticmethod
    def _parse(message: str):
        """Standardize level-based icons and formatting."""
        if message.startswith("[") and "]" in message:
            source = message[1:message.index("]")].upper()
            icon = SOURCE_ICONS.get(source, "")
            if icon:
                return f"[dim]{icon}[/] {message}"
        return message

    @staticmethod
    def info(message: str, icon: str = ""):
        if Logger._silent: return
        msg = f"{icon} {message}" if icon else Logger._parse(message)
        logger.info(msg)

    @staticmethod
    def success(message: str):
        if Logger._silent: return
        logger.success(f"✅ {Logger._parse(message)}")

    @staticmethod
    def warning(message: str):
        if Logger._silent: return
        logger.warning(Logger._parse(message))

    @staticmethod
    def error(message: str):
        if Logger._silent: return
        logger.error(Logger._parse(message))

    @staticmethod
    def critical(message: str):
        if Logger._silent: return
        logger.critical(f"🛑 {Logger._parse(message)}")

    @staticmethod
    def debug(message: str):
        if Logger._silent: return
        logger.debug(message)

    @staticmethod
    def section(title: str):
        if Logger._silent: return
        print("\n")
        logger.opt(raw=True).info(f"<magenta bold>=== {title} ===</magenta bold>\n")

    @staticmethod
    def set_silent(silent: bool):
        Logger._silent = silent
        if silent:
            logger.remove()
        else:
            logger.configure(**config)

    @staticmethod
    def add_file_sink(path: str):
        """Add a specific file sink (e.g. for unified engine logging)."""
        logger.add(
            path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            level="INFO",
            rotation="10 MB",
            retention="7 days",
            compression="zip"
        )

    @staticmethod
    def add_memory_sink(maxlen: int = 10):
        """Add a deque sink for TUI display."""
        from collections import deque
        memory_buffer = deque(maxlen=maxlen)
        
        def memory_sink(message):
            # Strip coloring? Maybe keep it for Rich
            # Loguru message is an object, convert to string
            memory_buffer.append(message.record["message"])
            
        logger.add(memory_sink, level="INFO", format="{message}")
        return memory_buffer

# --- Test ---
if __name__ == "__main__":
    Logger.section("LOGURU + RICH INTEGRATION")
    Logger.info("[SYSTEM] Initializing Node...")
    Logger.success("[TRADE] Arbitrage profitable!")
    Logger.warning("[ORCA] Liquidity low on SOL/USDC")
    Logger.error("[ML] Model failed to predict delta")
