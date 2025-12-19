"""
V11.12: Communications Daemon
=============================
Dedicated alert queue and daemon for Telegram notifications.
Separates alert I/O from the operational PriorityQueue.

Features:
- Independent AlertsQueue for all Telegram messages
- Rate limiting (3 seconds between sends)
- Message batching during high-volume periods
- Thread-safe singleton pattern
"""

import threading
import queue
import time
from src.system.logging import Logger


class CommsDaemon:
    """
    V11.12: Dedicated Communications Daemon.
    
    Manages all Telegram alerts independently from operational tasks.
    Implements throttling and batching to prevent rate limiting.
    """
    
    _instance = None
    
    # V18.1: Enhanced Rate limiting
    MIN_INTERVAL_S = 15  # Relaxed to 15s to satisfy strict Telegram pacing
    BATCH_WINDOW_S = 10  # Batch messages for 10s to group noisy bursts
    MAX_RETRIES = 3     # Max retry attempts on API error
    ERROR_BACKOFF_S = 30  # Back off 30s after error to really cool down
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommsDaemon, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.alerts_queue = queue.Queue()
        self.running = False
        self.worker_thread = None
        self.last_send_time = 0
        self.pending_batch = []
        self._lock = threading.Lock()
        
    def start(self):
        """Start the communications daemon."""
        if self.running:
            return
            
        self.running = True
        self.worker_thread = threading.Thread(
            target=self._daemon_loop, 
            daemon=True, 
            name="CommsDaemon"
        )
        self.worker_thread.start()
        Logger.info("📡 [COMMS] Communications Daemon started")
        
    def stop(self):
        """Stop the daemon gracefully."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
            
    def send_alert(self, message: str, source: str = "SYSTEM", priority: str = "LOW"):
        """
        Queue an alert to be sent via Telegram.
        
        Args:
            message: Alert message text
            source: Component identifier (BROKER, PRIMARY, DISCOVERY, etc.)
            priority: HIGH (immediate), LOW (can be batched)
        """
        alert = {
            "message": message,
            "source": source,
            "priority": priority,
            "timestamp": time.time()
        }
        self.alerts_queue.put(alert)
        
    def _daemon_loop(self):
        """Main daemon loop - processes alerts with throttling."""
        from src.utils.notifications import get_notifier
        notifier = get_notifier()
        
        while self.running:
            try:
                # Get alert with timeout
                alert = self.alerts_queue.get(timeout=1.0)
                
                now = time.time()
                
                # HIGH priority: Send immediately (respect minimum interval)
                if alert["priority"] == "HIGH":
                    if now - self.last_send_time >= self.MIN_INTERVAL_S:
                        # Flush any pending batch first
                        if self.pending_batch:
                            self._send_batch(notifier)
                        
                        # Send high priority immediately
                        full_msg = f"[{alert['source']}] {alert['message']}"
                        notifier.send_alert(full_msg, alert["priority"])
                        self.last_send_time = now
                    else:
                        # Queue it
                        self.pending_batch.append(alert)
                else:
                    # LOW priority: Add to batch
                    self.pending_batch.append(alert)
                
                # Check if batch should be sent
                if self.pending_batch:
                    oldest = self.pending_batch[0]["timestamp"]
                    if now - oldest >= self.BATCH_WINDOW_S and now - self.last_send_time >= self.MIN_INTERVAL_S:
                        self._send_batch(notifier)
                        
                self.alerts_queue.task_done()
                
            except queue.Empty:
                # Check for stale batch
                if self.pending_batch:
                    now = time.time()
                    if now - self.last_send_time >= self.MIN_INTERVAL_S:
                        from src.utils.notifications import get_notifier
                        self._send_batch(get_notifier())
                continue
            except Exception as e:
                Logger.warning(f"[COMMS] Daemon error: {e}")
                
    def _send_batch(self, notifier):
        """Send batched messages as multiple Telegram messages if needed."""
        if not self.pending_batch:
            return
            
        # Group by source
        all_lines = []
        for alert in self.pending_batch:
            all_lines.append(f"• [{alert['source']}] {alert['message']}")
        
        # Helper to send a single chunk
        def send_chunk(text):
            for attempt in range(self.MAX_RETRIES):
                try:
                    notifier.send_alert(text, "BATCH")
                    return True
                except Exception as e:
                    if "400" in str(e) or "429" in str(e):
                        Logger.warning(f"[COMMS] Rate limit/Error, backing off {self.ERROR_BACKOFF_S}s")
                        time.sleep(self.ERROR_BACKOFF_S)
                    else:
                        Logger.warning(f"[COMMS] Send error: {e}")
                        break
            return False

        # Build chunks respecting MAX_TELEGRAM_CHARS
        current_chunk = []
        current_length = 0
        MAX_CHARS = 3900 # Safety buffer below 4096
        
        for line in all_lines:
            line_len = len(line) + 1 # +1 for newline
            
            if current_length + line_len > MAX_CHARS:
                # Send current chunk
                if current_chunk:
                    success = send_chunk("\n".join(current_chunk))
                    if not success:
                        # If failed after retries, abort rest to prevent blocking? 
                        # Or continue? safer to continue best effort.
                        pass
                
                # Start new chunk
                current_chunk = [line]
                current_length = line_len
            else:
                current_chunk.append(line)
                current_length += line_len
        
        # Send final chunk
        if current_chunk:
            send_chunk("\n".join(current_chunk))
            
        self.pending_batch = []
        self.last_send_time = time.time()


# Singleton accessor
_comms_daemon = None

def get_comms_daemon() -> CommsDaemon:
    """Get or create the singleton CommsDaemon."""
    global _comms_daemon
    if _comms_daemon is None:
        _comms_daemon = CommsDaemon()
    return _comms_daemon


# Convenience function for quick alerts
def send_telegram(message: str, source: str = "SYSTEM", priority: str = "LOW"):
    """
    Send a Telegram alert via the CommsDaemon.
    
    Args:
        message: Alert text
        source: Component name (BROKER, PRIMARY, DISCOVERY, HUNTER, etc.)
        priority: HIGH (immediate) or LOW (can be batched)
    """
    daemon = get_comms_daemon()
    if not daemon.running:
        daemon.start()
    daemon.send_alert(message, source, priority)


# V11.16: Chunked message support for large reports
MAX_TELEGRAM_CHARS = 3900  # Leave buffer from 4096 limit

def send_telegram_chunked(message: str, source: str = "SYSTEM", priority: str = "LOW"):
    """
    V11.16: Send a large message in chunks if it exceeds Telegram's limit.
    
    Args:
        message: Full message text (will be split if > 3900 chars)
        source: Component name
        priority: HIGH or LOW
    """
    if len(message) <= MAX_TELEGRAM_CHARS:
        send_telegram(message, source, priority)
        return
    
    # Split by lines to avoid breaking mid-word
    lines = message.split('\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_length + line_len > MAX_TELEGRAM_CHARS:
            # Save current chunk and start new one
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = line_len
        else:
            current_chunk.append(line)
            current_length += line_len
    
    # Add final chunk
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    # Send each chunk with part numbering
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        header = f"[{i}/{total}]\n" if total > 1 else ""
        send_telegram(header + chunk, source, priority)
