"""
V51.0: Unified Log Manager
==========================
Central routing layer for all logging output.

Features:
- Loguru for structured file logging with rotation
- Rich for beautiful console output
- Backward-compatible with existing Logger.* API
- Source tagging for filtering

Usage:
    from src.system.log_manager import get_log_manager, Logger
    
    # New API
    log = get_log_manager()
    log.info("Message", source="BROKER")
    log.trade("BUY", "WIF", 25.00, 2.45)
    
    # Legacy API (still works)
    Logger.info("[BROKER] Message")
"""

import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime

# Check for optional dependencies
try:
    from loguru import logger as loguru_logger
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False
    loguru_logger = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None


# =============================================================================
# STYLE CONFIGURATION
# =============================================================================

# Level styles for Rich console
LEVEL_STYLES = {
    "INFO": "cyan",
    "SUCCESS": "green bold",
    "WARNING": "yellow",
    "ERROR": "red bold",
    "DEBUG": "dim",
    "CRITICAL": "red bold reverse",
    "SECTION": "magenta bold",
}

# Source icons for compact display
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
}


class LogManager:
    """
    V51.0: Unified logging router.
    
    Routes logs to:
    1. Console (Rich if available, fallback to print)
    2. File (Loguru if available, fallback to RotatingFileHandler)
    3. Optionally to Telegram via CommsDaemon
    """
    
    def __init__(self):
        """Initialize log manager with available backends."""
        self._console = Console() if HAS_RICH else None
        self._setup_file_logging()
        self._silent_mode = False
        
    def _setup_file_logging(self):
        """Configure file logging backend."""
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            "logs"
        )
        os.makedirs(log_dir, exist_ok=True)
        
        if HAS_LOGURU:
            # Remove default handler
            loguru_logger.remove()
            
            # Add file handler with rotation
            loguru_logger.add(
                os.path.join(log_dir, "phantom_{time:YYYY-MM-DD}.log"),
                rotation="10 MB",
                retention="7 days",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {message}",
                level="INFO",
            )
            
            # Add structured JSON log for analysis
            loguru_logger.add(
                os.path.join(log_dir, "phantom_structured.jsonl"),
                rotation="50 MB",
                retention="3 days",
                serialize=True,
                level="DEBUG",
            )
    
    # =========================================================================
    # CORE LOGGING METHODS
    # =========================================================================
    
    def _timestamp(self) -> str:
        """Get high-precision timestamp."""
        now = datetime.now()
        return f"{now.strftime('%H:%M:%S')}.{str(now.microsecond)[:3]:0<3}"
    
    def _format_console(self, level: str, message: str, source: str) -> None:
        """Output to console with Rich formatting if available."""
        if self._silent_mode:
            return
            
        ts = self._timestamp()
        icon = SOURCE_ICONS.get(source.upper(), "")
        
        if HAS_RICH and self._console:
            style = LEVEL_STYLES.get(level, "white")
            lvl_display = level[:8].ljust(8)
            src_display = source[:10].ljust(10)
            
            # Rich formatted output
            line = Text()
            line.append(f"{ts} ", style="dim")
            line.append(f"| {lvl_display} ", style=style)
            line.append(f"| {src_display} | ", style="dim")
            line.append(f"{icon} {message}" if icon else message)
            
            self._console.print(line)
        else:
            # Fallback to plain print
            print(f"{ts} | {level:8} | {source:10} | {icon} {message}")
    
    def _log_to_file(self, level: str, message: str, source: str) -> None:
        """Write to file logger."""
        full_msg = f"[{source}] {message}"
        
        if HAS_LOGURU:
            if level == "INFO":
                loguru_logger.info(full_msg)
            elif level == "WARNING":
                loguru_logger.warning(full_msg)
            elif level == "ERROR":
                loguru_logger.error(full_msg)
            elif level == "DEBUG":
                loguru_logger.debug(full_msg)
            elif level == "SUCCESS":
                loguru_logger.success(full_msg)
            elif level == "CRITICAL":
                loguru_logger.critical(full_msg)
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def info(self, message: str, source: str = "SYSTEM") -> None:
        """Log info message."""
        self._format_console("INFO", message, source)
        self._log_to_file("INFO", message, source)
    
    def success(self, message: str, source: str = "SYSTEM") -> None:
        """Log success message."""
        self._format_console("SUCCESS", message, source)
        self._log_to_file("SUCCESS", message, source)
    
    def warning(self, message: str, source: str = "SYSTEM") -> None:
        """Log warning message."""
        self._format_console("WARNING", message, source)
        self._log_to_file("WARNING", message, source)
    
    def error(self, message: str, source: str = "SYSTEM") -> None:
        """Log error message."""
        self._format_console("ERROR", message, source)
        self._log_to_file("ERROR", message, source)
    
    def debug(self, message: str, source: str = "SYSTEM") -> None:
        """Log debug message (file only by default)."""
        self._log_to_file("DEBUG", message, source)
    
    def critical(self, message: str, source: str = "SYSTEM") -> None:
        """Log critical message."""
        self._format_console("CRITICAL", message, source)
        self._log_to_file("CRITICAL", message, source)
    
    def section(self, title: str) -> None:
        """Print a section header."""
        if HAS_RICH and self._console:
            self._console.print()
            self._console.rule(f"[bold magenta]{title}[/]", style="dim")
        else:
            print("\n" + "─" * 60)
            print(f"{self._timestamp()} | SECTION  | SYSTEM     | 🛸 {title}")
            print("─" * 60)
        
        self._log_to_file("INFO", f"=== {title} ===", "SYSTEM")
    
    # =========================================================================
    # RICH HELPERS (optional)
    # =========================================================================
    
    def table(self, title: str, data: Dict[str, Any]) -> None:
        """Display data as a formatted table (Rich only)."""
        if not HAS_RICH or not self._console:
            # Fallback
            print(f"\n{title}:")
            for k, v in data.items():
                print(f"  {k}: {v}")
            return
        
        table = Table(title=title, show_header=True)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        
        for key, value in data.items():
            table.add_row(str(key), str(value))
        
        self._console.print(table)
    
    def panel(self, content: str, title: str = "") -> None:
        """Display content in a panel (Rich only)."""
        if HAS_RICH and self._console:
            self._console.print(Panel(content, title=title))
        else:
            print(f"\n{'='*40}")
            if title:
                print(f" {title}")
            print(content)
            print('='*40)
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def set_silent(self, silent: bool) -> None:
        """Enable/disable console output."""
        self._silent_mode = silent


# =============================================================================
# SINGLETON
# =============================================================================

_log_manager_instance: Optional[LogManager] = None


def get_log_manager() -> LogManager:
    """Get or create the singleton LogManager."""
    global _log_manager_instance
    if _log_manager_instance is None:
        _log_manager_instance = LogManager()
    return _log_manager_instance


# =============================================================================
# LEGACY COMPATIBILITY WRAPPER
# =============================================================================

class LegacyLoggerWrapper:
    """
    Wrapper that maintains backward compatibility with Logger.info() style calls.
    
    Parses source from message format: "[SOURCE] message"
    """
    
    @staticmethod
    def _parse_source(message: str) -> tuple:
        """Extract source tag from message if present."""
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
    def info(message: str, icon: str = "") -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        if icon:
            msg = f"{icon} {msg}"
        get_log_manager().info(msg, source)
    
    @staticmethod
    def success(message: str) -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        get_log_manager().success(msg, source)
    
    @staticmethod
    def warning(message: str) -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        get_log_manager().warning(msg, source)
    
    @staticmethod
    def error(message: str) -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        get_log_manager().error(msg, source)
    
    @staticmethod
    def debug(message: str) -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        get_log_manager().debug(msg, source)
    
    @staticmethod
    def critical(message: str) -> None:
        source, msg = LegacyLoggerWrapper._parse_source(message)
        get_log_manager().critical(msg, source)
    
    @staticmethod
    def section(title: str) -> None:
        get_log_manager().section(title)


# Alias for backward compatibility
Logger = LegacyLoggerWrapper


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print(f"\n📋 Log Manager Test (Rich={HAS_RICH}, Loguru={HAS_LOGURU})")
    print("=" * 50)
    
    log = get_log_manager()
    
    log.section("Testing All Log Levels")
    log.info("This is an info message", source="TEST")
    log.success("This is a success message", source="ORCA")
    log.warning("This is a warning message", source="BROKER")
    log.error("This is an error message", source="DISCOVERY")
    
    log.section("Testing Legacy API")
    Logger.info("[BROKER] Legacy format message")
    Logger.warning("[ML] Legacy warning")
    
    if HAS_RICH:
        log.section("Rich Features")
        log.table("Status", {"Positions": 3, "Value": "$150.00", "Fees": "$2.50"})
        log.panel("This is a test panel with some content.", title="Info")
    
    print("\n✅ Test complete!")
