
import sys
import logging
from loguru import logger
from rich.logging import RichHandler

class InterceptHandler(logging.Handler):
    """
    Redirects standard logging messages to Loguru.
    """
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def setup_logging(level="INFO", log_file=None):
    """
    Configures Loguru to use Rich for console output and standard formatted text for files.
    """
    # Remove default handler
    logger.remove()

    # 1. rich console handler (Beautiful TUI)
    logger.add(
        RichHandler(rich_tracebacks=True, markup=True),
        level=level,
        format="{message}", # RichHandler handles timestamp/level
        colorize=True,
    )

    # 2. File Handler (optional)
    if log_file:
        logger.add(
            log_file,
            rotation="10 MB",
            retention="1 week",
            level="DEBUG",
            format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
        )

    # 3. Intercept Standard Logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # Silence noisy libs
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("multipart").setLevel(logging.WARNING)

    return logger

# Global instance for quick import
# But preferred usage is `from loguru import logger` after setup
