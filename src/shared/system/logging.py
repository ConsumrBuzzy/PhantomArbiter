"""
V51.0: Centralized Logger with Rich Console
============================================
Backward-compatible wrapper that routes to LogManager.

Usage (unchanged from before):
    from src.shared.system.logging import Logger
    
    Logger.info("[BROKER] Message")
    Logger.success("[ORCA] Position opened")
    Logger.warning("Something concerning")
    Logger.error("Something broke")
    Logger.section("Starting Module")
"""

import os
import logging
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

# V9.7: Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# V133: Per-run session log file (Session-Based Forensics)
# Each run creates a unique log file for easier debugging
_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = os.path.join(LOG_DIR, f"phantom_{_run_id}.log")

# Fallback file logger (uses per-run file instead of static phantom.log)
handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
handler.setFormatter(formatter)

file_logger = logging.getLogger("PhantomTrader")
file_logger.setLevel(logging.INFO)
file_logger.addHandler(handler)


# =============================================================================
# SOURCE ICONS (for visual scanning)
# =============================================================================

SOURCE_ICONS = {
    "SYSTEM": "🛸",
    "BROKER": "📊",
    "ORCA": "🐋",
    "DISCOVERY": "🔍",
    "TRADE": "💰",
    "ML": "🧠",
    "SCOUT": "🏹",
    "PRIMARY": "Ⓜ️",
    "SCALPER": "⚡",
    "LANDLORD": "🏠",
    "CAPITAL": "💵",
    "WSS": "📡",
    "DSM": "📈",
    "REPORT": "📋",
    "LIQUIDITY": "💧",
    "COMMS": "📣",
}


# =============================================================================
# RICH CONSOLE (optional enhancement)
# =============================================================================

try:
    from rich.console import Console
    from rich.text import Text
    HAS_RICH = True
    _console = Console()
except ImportError:
    HAS_RICH = False
    _console = None

# Level colors for Rich
LEVEL_STYLES = {
    "INFO": "cyan",
    "SUCCESS": "green bold",
    "WARNING": "yellow",
    "ERROR": "red bold",
    "DEBUG": "dim",
    "CRITICAL": "red bold reverse",
    "SECTION": "magenta bold",
}


# =============================================================================
# LOGGER CLASS
# =============================================================================

class Logger:
    """
    V51.0: Centralized logger with Rich console output.
    
    Features:
    - Color-coded output with Rich (if available)
    - Fallback to plain print if Rich not installed
    - File logging with rotation
    - Source-based icon prefixes
    """
    
    _silent_mode = False
    
    @staticmethod
    def _timestamp() -> str:
        """High-precision timestamp (HH:MM:SS.ms)."""
        now = datetime.now()
        ms = str(now.microsecond)[:3]
        return f"{now.strftime('%H:%M:%S')}.{ms:0<3}"
    
    @staticmethod
    def _parse_source(message: str) -> tuple:
        """Extract [SOURCE] tag from message if present."""
        if message.strip().startswith("[") and "]" in message:
            try:
                tag_end = message.index("]")
                source = message[1:tag_end].upper()
                clean_msg = message[tag_end+1:].strip()
                if len(source) < 15:
                    return source, clean_msg
            except:
                pass
        return "SYSTEM", message
    
    @staticmethod
    def _format_console(level: str, message: str, source: str) -> None:
        """Output to console with optional Rich formatting."""
        if Logger._silent_mode:
            return
        
        from config.settings import Settings
        if getattr(Settings, "SILENT_MODE", False):
            return
            
        ts = Logger._timestamp()
        icon = SOURCE_ICONS.get(source.upper(), "")
        msg_with_icon = f"{icon} {message}" if icon else message
        
        if HAS_RICH and _console:
            style = LEVEL_STYLES.get(level, "white")
            lvl_display = level[:8].ljust(8)
            src_display = source[:10].ljust(10)
            
            line = Text()
            line.append(f"{ts} ", style="dim")
            line.append(f"| {lvl_display} ", style=style)
            line.append(f"| {src_display} | ", style="dim")
            line.append(msg_with_icon)
            
            _console.print(line)
        else:
            # Plain fallback
            print(f"{ts} | {level:8} | {source:10} | {msg_with_icon}")
    
    @staticmethod
    def _log_to_file(level: str, message: str, source: str = "") -> None:
        """Write to file logger."""
        full_msg = f"[{source}] {message}" if source else message
        if level == "INFO":
            file_logger.info(full_msg)
        elif level == "WARNING":
            file_logger.warning(full_msg)
        elif level == "ERROR":
            file_logger.error(full_msg)
        elif level == "DEBUG":
            file_logger.debug(full_msg)
    
    # =========================================================================
    # PUBLIC API (Backward Compatible)
    # =========================================================================
    
    @staticmethod
    def info(message: str, icon: str = "") -> None:
        source, msg = Logger._parse_source(message)
        if icon:
            msg = f"{icon} {msg}"
        Logger._format_console("INFO", msg, source)
        Logger._log_to_file("INFO", msg, source)
    
    @staticmethod
    def success(message: str) -> None:
        source, msg = Logger._parse_source(message)
        Logger._format_console("SUCCESS", msg, source)
        Logger._log_to_file("INFO", f"✅ {msg}", source)
    
    @staticmethod
    def warning(message: str) -> None:
        source, msg = Logger._parse_source(message)
        Logger._format_console("WARNING", msg, source)
        Logger._log_to_file("WARNING", msg, source)
    
    @staticmethod
    def error(message: str) -> None:
        source, msg = Logger._parse_source(message)
        Logger._format_console("ERROR", msg, source)
        Logger._log_to_file("ERROR", msg, source)
    
    @staticmethod
    def debug(message: str) -> None:
        source, msg = Logger._parse_source(message)
        Logger._log_to_file("DEBUG", msg, source)
    
    @staticmethod
    def critical(message: str) -> None:
        source, msg = Logger._parse_source(message)
        Logger._format_console("CRITICAL", f"🛑 {msg}", source)
        Logger._log_to_file("ERROR", f"🛑 {msg}", source)
    
    @staticmethod
    def section(title: str) -> None:
        """Print a section header."""
        if HAS_RICH and _console:
            _console.print()
            _console.rule(f"[bold magenta]{title}[/]", style="dim")
        else:
            print("\n" + "─" * 60)
            ts = Logger._timestamp()
            print(f"{ts} | SECTION  | SYSTEM     | 🛸 {title}")
            print("─" * 60)
        
        Logger._log_to_file("INFO", f"=== {title} ===", "SYSTEM")
    
    @staticmethod
    def set_silent(silent: bool) -> None:
        """Enable/disable console output."""
        Logger._silent_mode = silent


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print(f"\n📋 Logger Test (Rich={HAS_RICH})")
    print("=" * 50)
    
    Logger.section("Testing All Log Levels")
    Logger.info("[BROKER] This is an info message")
    Logger.success("[ORCA] Position opened successfully")
    Logger.warning("[DSM] Tier 1 failed, switching to Tier 2")
    Logger.error("[ML] Model training failed")
    
    Logger.section("Testing Source Parsing")
    Logger.info("[DISCOVERY] New launch detected")
    Logger.info("[SCALPER] Quick trade executed")
    Logger.info("No source tag - defaults to SYSTEM")
    
    print("\n✅ Logger test complete!")
