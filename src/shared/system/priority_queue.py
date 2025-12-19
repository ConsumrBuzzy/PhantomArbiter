import threading
import queue
import time
from src.shared.system.logging import Logger

class PriorityQueue:
    """
    V10.2: System-wide Async I/O Queue.
    Offloads slow tasks (logging, alerts, disk I/O) from the main trading thread.
    Singleton pattern.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PriorityQueue, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.queue = queue.PriorityQueue()
        self.running = False
        self.worker_thread = None
        self._seq = 0  # Tie-breaker for tasks with same priority
        self._seq_lock = threading.Lock()
        
        # Priority Constants (Lower number = Higher Priority)
        self.PRIORITY_CRITICAL = 1  # Trade Alerts, Errors
        self.PRIORITY_HIGH = 2      # Trade Records
        self.PRIORITY_NORMAL = 3    # Standard Logs
        self.PRIORITY_LOW = 4       # Datasets, Debug
        
    def start(self):
        """Start the background worker thread."""
        if self.running:
            return
            
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        Logger.info("⚡ Priority Queue Started (Async I/O)")
        
    def stop(self):
        """Stop the worker thread gracefully."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
            
    def add(self, priority, task_type, payload):
        """
        Add a task to the queue.
        priority: 1 (Critical) to 4 (Low)
        task_type: 'LOG', 'ALERT', 'TRADE_RECORD'
        payload: dict of arguments for the task
        """
        if not self.running:
            # Fallback for sync execution if not running (e.g. startup/shutdown)
            self._process_task(task_type, payload)
            return
            
        with self._seq_lock:
            count = self._seq
            self._seq += 1
            
        # Store as (priority, count, task_type, payload)
        # Sequence count breaks ties, so 'payload' (dict) is never compared
        self.queue.put((priority, count, task_type, payload))
        
    def _worker_loop(self):
        while self.running:
            try:
                # Get task with timeout to allow checking self.running
                # Unpack sequence count (ignored for processing)
                priority, _, task_type, payload = self.queue.get(timeout=1.0)
                
                try:
                    self._process_task(task_type, payload)
                except Exception as e:
                    print(f"❌ Queue Task Failed: {e}")
                    
                self.queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Queue Worker Error: {e}")
                
    def _process_task(self, task_type, payload):
        """Execute the specific task logic."""
        if task_type == 'LOG':
            level = payload.get('level', 'INFO')
            msg = payload.get('message', '')
            icon = payload.get('icon', '')
            
            if level == 'INFO':
                Logger.info(msg, icon)
            elif level == 'SUCCESS':
                Logger.success(msg)
            elif level == 'WARNING':
                Logger.warning(msg)
            elif level == 'ERROR':
                Logger.error(msg)
                
        elif task_type == 'ALERT':
            # V11.12: DEPRECATED - Redirect to CommsDaemon
            # All alerts should use send_telegram() from comms_daemon.py instead
            from src.shared.system.comms_daemon import send_telegram
            msg = payload.get('message', '')
            priority = payload.get('priority', 'LOW')
            send_telegram(msg, source="LEGACY", priority=priority)
            Logger.warning(f"⚠️ [DEPRECATION] Use send_telegram() instead of priority_queue ALERT")
                
        elif task_type == 'TRADE_RECORD':
            # V10.5: Log to DB
            from src.shared.system.db_manager import db_manager
            db_manager.log_trade(payload)

# Global Instance Accessor
priority_queue = PriorityQueue()
