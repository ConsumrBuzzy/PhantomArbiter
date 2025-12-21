"""
V44.0: Database Manager (Unified Backend)
==========================================
Factory pattern for SQLite/PostgreSQL backend selection.

Features:
- SQLite for local development (default)
- PostgreSQL + TimescaleDB for production
- Same interface regardless of backend
- Backwards compatible with existing code

Usage:
    from src.data_storage.db_manager import db_manager
    db_manager.insert_tick(mint, price, volume, liq, latency)
"""

import sqlite3
import time
import os
import threading
from typing import List, Tuple, Any

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════
# SQLITE ADAPTER (Original Implementation)
# ═══════════════════════════════════════════════════════════════════════════

class SQLiteAdapter:
    """
    V35.0: SQLite Market Data Storage (Local Development).
    Original implementation preserved for backwards compatibility.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, db_path=None):
        if db_path is None:
            # Default to data/market_data.db
            db_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "market_data.db")
            
        self.db_path = db_path
        self._conn = None
        self._cursor = None
        self._init_db()
        
    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance
        
    def _get_conn(self):
        # SQLite connection per thread check (simplified with check_same_thread=False)
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._cursor = self._conn.cursor()
        return self._conn
        
    def _init_db(self):
        """Initialize Schema."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_data (
                    timestamp REAL,
                    token_mint TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume_h1 REAL,
                    liquidity_usd REAL,
                    latency_ms INTEGER,
                    PRIMARY KEY (timestamp, token_mint)
                )
            """)
            
            # V63.1: Simulated Trades Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS simulated_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    side TEXT,
                    price REAL,
                    size_usd REAL,
                    pnl_usd REAL,
                    reason TEXT,
                    confidence REAL,
                    is_win INTEGER  -- 0 or 1
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mint_ts ON market_data (token_mint, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sim_ts ON simulated_trades (timestamp)")
            conn.commit()
            Logger.info(f"💾 SQLite Initialized: {self.db_path} (+Trades)")
        except Exception as e:
            Logger.error(f"❌ DB Init Error: {e}")
            
    def insert_tick(self, mint, price, volume=0.0, liq=0.0, latency=0):
        """Insert a single tick."""
        try:
            ts = time.time()
            conn = self._get_conn()
            conn.execute("""
                INSERT INTO market_data (timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ts, mint, price, price, price, price, volume, liq, latency))
            conn.commit()
            return True
        except Exception:
            return False  # Silent fail to not block Broker loop

    def insert_simulated_trade(self, trade_data: dict):
        """
        V63.1: Log a simulated trade to DB.
        Expected keys: timestamp, symbol, side, price, size_usd, pnl_usd, reason, confidence, is_win
        """
        try:
            conn = self._get_conn()
            conn.execute("""
                INSERT INTO simulated_trades (timestamp, symbol, side, price, size_usd, pnl_usd, reason, confidence, is_win)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('timestamp', time.time()),
                trade_data.get('symbol', 'UNKNOWN'),
                trade_data.get('side', 'UNKNOWN'),
                trade_data.get('price', 0.0),
                trade_data.get('size_usd', 0.0),
                trade_data.get('pnl_usd', 0.0),
                trade_data.get('reason', ''),
                trade_data.get('confidence', 0.0),
                1 if trade_data.get('is_win', False) else 0
            ))
            conn.commit()
            return True
        except Exception as e:
            Logger.error(f"❌ DB Log Error: {e}")
            return False

    def get_history(self, mint, start_ts=0, end_ts=None) -> List[Tuple]:
        """Fetch historical rows."""
        if end_ts is None: 
            end_ts = time.time()
        try:
            conn = self._get_conn()
            cursor = conn.execute("""
                SELECT timestamp, open, high, low, close, volume_h1 
                FROM market_data 
                WHERE token_mint = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (mint, start_ts, end_ts))
            return cursor.fetchall()
        except Exception as e:
            Logger.error(f"❌ DB Read Error: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM market_data")
            total_rows = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(DISTINCT token_mint) FROM market_data")
            unique_tokens = cursor.fetchone()[0]
            
            return {
                "total_rows": total_rows,
                "unique_tokens": unique_tokens,
                "backend": "sqlite",
                "path": self.db_path
            }
        except Exception as e:
            return {"error": str(e)}

    def close(self):
        if self._conn:
            self._conn.close()
    
    def __repr__(self):
        return f"<SQLiteAdapter path={self.db_path}>"


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def get_db_manager():
    """
    V44.0: Factory function to get appropriate database adapter.
    
    Returns SQLite or PostgreSQL adapter based on DB_BACKEND environment variable.
    """
    try:
        from config.db_config import DB_BACKEND, validate_config
        
        if DB_BACKEND == "postgres":
            validate_config()
            from src.data_storage.postgres_adapter import PostgresAdapter
            return PostgresAdapter()
        else:
            return SQLiteAdapter.get_instance()
            
    except ImportError:
        # Fallback to SQLite if config not available
        return SQLiteAdapter.get_instance()
    except Exception as e:
        Logger.warning(f"DB init error, using SQLite fallback: {e}")
        return SQLiteAdapter.get_instance()


# ═══════════════════════════════════════════════════════════════════════════
# BACKWARDS COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════════════

# Legacy: DBManager class alias
class DBManager(SQLiteAdapter):
    """Legacy alias for backwards compatibility."""
    pass


# Global Instance (factory-based)
try:
    db_manager = get_db_manager()
except Exception:
    # Ultimate fallback
    db_manager = SQLiteAdapter()
