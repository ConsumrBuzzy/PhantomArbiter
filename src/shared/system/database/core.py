import sqlite3
import os
import time
from contextlib import contextmanager
from src.shared.system.logging import Logger

class DatabaseCore:
    """
    Core Database Connection Manager.
    Handles connection pooling, WAL mode, and schema initialization.
    Singleton pattern ensures single point of truth.
    """
    _instance = None
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "data", "trading_journal.db")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseCore, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._ensure_data_dir()
        self._init_wal_mode()
        # Schema init is handled by the Facade or individual repos now, 
        # but Core provides the connection.

    def _ensure_data_dir(self):
        directory = os.path.dirname(self.DB_PATH)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except OSError as e:
                Logger.error(f"❌ Failed to create data dir: {e}")

    def _init_wal_mode(self):
        """Enable Write-Ahead Logging for concurrency."""
        try:
            with self.cursor(commit=True) as c:
                c.execute("PRAGMA journal_mode=WAL;")
                c.execute("PRAGMA synchronous=NORMAL;") # Faster, slightly less safe than FULL
        except Exception as e:
            Logger.warning(f"⚠️ Failed to enable WAL mode: {e}")

    def get_connection(self):
        """Get a configured SQLite connection."""
        conn = sqlite3.connect(self.DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def cursor(self, commit=False):
        """Context manager for database interaction."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            if commit:
                conn.rollback()
            Logger.error(f"❌ DB Error: {e}")
            raise e
        finally:
            conn.close()

    def wait_for_connection(self, timeout=2.0) -> bool:
        """Ensure database is ready."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with self.cursor() as c:
                    c.execute("SELECT 1")
                    if c.fetchone():
                        Logger.info("   📦 DB Connection Verified (WAL Mode)")
                        return True
            except:
                time.sleep(0.1)
        return False
