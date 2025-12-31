"""
NotificationService - Async Telegram Alerts
============================================
Non-blocking Telegram notifications for trade signals and alerts.
"""

import os
import requests
import threading
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), "../../.env")
load_dotenv(env_path)


class NotificationService:
    """Async Telegram notification service with rate limiting."""

    # V11.10: Rate limiting (Telegram allows ~30 messages/sec, but we're conservative)
    # V18.2: Increased from 3s to 5s to prevent 400 errors during signal bursts
    MIN_INTERVAL_SECONDS = 5  # Minimum time between messages

    def __init__(self):
        self.TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "2022758508")
        self.BASE_URL = f"https://api.telegram.org/bot{self.TOKEN}/sendMessage"

        # V11.10: Rate limiting state
        self.last_send_time = 0
        self.pending_messages = []
        self.rate_lock = threading.Lock()
        self.error_count = 0  # V18.2: Track errors silently

        if not self.TOKEN or self.TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("   ⚠️ Telegram BOT_TOKEN not set. Notifications disabled.")
            self.enabled = False
        else:
            self.enabled = True
            print("   📱 Telegram Notifications enabled")

    def send_alert(self, message: str, priority: str = "INFO"):
        """
        Send an alert with rate limiting (non-blocking).

        Args:
            message: Alert message text
            priority: Alert level (INFO, BUY, SELL, STOP_LOSS, CRITICAL)
        """
        if not self.enabled:
            return

        import time

        with self.rate_lock:
            now = time.time()

            # V11.10: Rate limiting check (Bypass for CRITICAL)
            if priority in ["CRITICAL", "IMPORTANT"] or "STATUS" in message:
                pass  # Skip rate limit check
            elif now - self.last_send_time < self.MIN_INTERVAL_SECONDS:
                # Queue message to be batched with next send
                self.pending_messages.append(f"• {message}")
                return

            # Include any pending messages
            if self.pending_messages:
                combined = "\n".join(self.pending_messages) + f"\n• {message}"
                self.pending_messages = []
                message = combined

            self.last_send_time = now

        # Start new thread for network request (non-blocking)
        thread = threading.Thread(target=self._send_threaded, args=(message, priority))
        thread.daemon = True
        thread.start()

    def _send_threaded(self, message: str, priority: str):
        """Internal method - executes blocking HTTP request in thread with retry."""
        import time

        # Emoji prefix based on priority
        emoji = {
            "INFO": "ℹ️",
            "BUY": "🚀",
            "SELL": "💰",
            "STOP_LOSS": "🛑",
            "CRITICAL": "⚠️",
            "DISCOVERY": "🔭",
        }.get(priority, "📝")

        # V11.11: Sanitize Markdown to prevent 400 errors
        # Telegram Markdown is strict. We need to escape special chars if we use Markdown mode.
        # Or simpler: Just use HTML or no parse_mode if complexities arise.
        # For now, we'll just escape common issues or downgrade to text for safety if needed.

        # V51.0: Use HTML for robustness (avoids Markdown underscore issues)
        formatted_message = f"{emoji} <b>{priority}</b>\n{message}"

        # Simple fix: If message contains unclosed formatting, it crashes.
        # Better strategy: Catch the 400, sanitize, and retry once as PLAIN TEXT.

        params = {
            "chat_id": self.CHAT_ID,
            "text": formatted_message,
            "parse_mode": "HTML",
        }

        # V18.2: Exponential backoff retry (5s, 10s, 15s)
        backoff_delays = [5, 10, 15]

        for attempt, delay in enumerate(backoff_delays):
            try:
                response = requests.post(self.BASE_URL, data=params, timeout=5)

                if response.status_code == 200:
                    return  # Success!
                elif response.status_code == 429:
                    # Rate limited - backoff and retry
                    self.error_count += 1
                    if self.error_count % 10 == 1:
                        print(f"   ⚠️ Telegram Rate Limit (429), retry in {delay}s...")
                    time.sleep(delay)
                elif response.status_code == 400:
                    # V11.11: Markdown parse error? Retry as PLAIN TEXT
                    if "parse entities" in response.text and params.get("parse_mode"):
                        print("   ⚠️ Markdown Error (400). Retrying as Plain Text...")
                        params.pop("parse_mode")  # Remove markdown
                        continue  # Retry loop immediately

                    print(f"   ❌ Telegram Bad Request (400) - {response.text}")
                    return  # Don't retry other bad requests
                else:
                    # Other error - don't retry
                    self.error_count += 1
                    return
            except requests.exceptions.Timeout:
                time.sleep(delay)  # Retry on timeout
            except Exception:
                return  # Don't retry on other errors

        # All retries failed
        self.error_count += 1


# Singleton instance
_notifier = None


def get_notifier() -> NotificationService:
    """Get or create the singleton NotificationService instance."""
    global _notifier
    if _notifier is None:
        _notifier = NotificationService()
    return _notifier
