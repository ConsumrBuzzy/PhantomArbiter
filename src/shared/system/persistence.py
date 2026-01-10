"""
Persistence Layer
=================
SQLite-based state management for the Phantom Arbiter Trading OS.

Features:
- Position state recovery after crashes
- Trade audit trail with UTC timestamps
- Signal/decision logging for analysis
- Atomic transactions for data consistency
- Engine state snapshots for resume capability
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
from contextlib import contextmanager
import threading


class TradeStatus(Enum):
    """Trade lifecycle states."""
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Position:
    """Represents an open position."""
    id: Optional[int] = None
    engine: str = ""
    symbol: str = ""
    side: str = "flat"
    size: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    leverage: float = 1.0
    opened_at: float = 0.0
    updated_at: float = 0.0
    metadata: str = "{}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class Trade:
    """Represents a completed trade."""
    id: Optional[int] = None
    engine: str = ""
    symbol: str = ""
    side: str = ""
    size: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    status: str = "pending"
    order_id: str = ""
    tx_signature: str = ""
    realized_pnl: float = 0.0
    created_at: float = 0.0
    executed_at: Optional[float] = None
    metadata: str = "{}"


@dataclass
class EngineSnapshot:
    """Engine state snapshot for recovery."""
    id: Optional[int] = None
    engine: str = ""
    status: str = "stopped"
    config: str = "{}"
    state: str = "{}"
    created_at: float = 0.0


class PersistenceDB:
    """
    Singleton SQLite persistence layer.
    
    Thread-safe with connection pooling per thread.
    All timestamps are stored as Unix epoch (UTC).
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        
        # Default path: data/arbiter.db
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent.parent / "data" / "arbiter.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-local storage for connections
        self._local = threading.local()
        
        # Initialize schema
        self._init_schema()
        self._initialized = True
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn
    
    @contextmanager
    def _transaction(self):
        """Context manager for atomic transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def _init_schema(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        
        conn.executescript("""
            -- Positions: Current open positions per engine
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL DEFAULT 'flat',
                size REAL NOT NULL DEFAULT 0,
                entry_price REAL NOT NULL DEFAULT 0,
                current_price REAL DEFAULT 0,
                unrealized_pnl REAL DEFAULT 0,
                leverage REAL DEFAULT 1.0,
                opened_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata TEXT DEFAULT '{}',
                UNIQUE(engine, symbol)
            );
            
            -- Trades: Audit trail of all executed trades
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                order_id TEXT,
                tx_signature TEXT,
                realized_pnl REAL DEFAULT 0,
                created_at REAL NOT NULL,
                executed_at REAL,
                metadata TEXT DEFAULT '{}'
            );
            
            -- Signals: Decision audit log
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                symbol TEXT,
                direction TEXT,
                confidence REAL,
                reason TEXT,
                created_at REAL NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            
            -- Engine Snapshots: State recovery data
            CREATE TABLE IF NOT EXISTS engine_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'stopped',
                config TEXT DEFAULT '{}',
                state TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );
            
            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_positions_engine ON positions(engine);
            CREATE INDEX IF NOT EXISTS idx_trades_engine ON trades(engine);
            CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_engine ON signals(engine);
        """)
        conn.commit()
    
    # ═══════════════════════════════════════════════════════════════
    # POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    def upsert_position(self, position: Position) -> int:
        """Insert or update a position."""
        now = time.time()
        position.updated_at = now
        if position.opened_at == 0:
            position.opened_at = now
        
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO positions (engine, symbol, side, size, entry_price, 
                                       current_price, unrealized_pnl, leverage,
                                       opened_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(engine, symbol) DO UPDATE SET
                    side = excluded.side,
                    size = excluded.size,
                    current_price = excluded.current_price,
                    unrealized_pnl = excluded.unrealized_pnl,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
            """, (
                position.engine, position.symbol, position.side, position.size,
                position.entry_price, position.current_price, position.unrealized_pnl,
                position.leverage, position.opened_at, position.updated_at,
                position.metadata
            ))
            return cursor.lastrowid
    
    def get_position(self, engine: str, symbol: str) -> Optional[Position]:
        """Get a specific position."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM positions WHERE engine = ? AND symbol = ?",
            (engine, symbol)
        ).fetchone()
        
        if row:
            return Position(**dict(row))
        return None
    
    def get_positions_by_engine(self, engine: str) -> List[Position]:
        """Get all positions for an engine."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM positions WHERE engine = ? AND size != 0",
            (engine,)
        ).fetchall()
        
        return [Position(**dict(row)) for row in rows]
    
    def close_position(self, engine: str, symbol: str) -> bool:
        """Mark position as flat (closed)."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE positions 
                SET side = 'flat', size = 0, unrealized_pnl = 0, updated_at = ?
                WHERE engine = ? AND symbol = ?
            """, (time.time(), engine, symbol))
            return True
    
    def get_all_open_positions(self) -> List[Position]:
        """Get all open positions across all engines."""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM positions WHERE size != 0"
        ).fetchall()
        
        return [Position(**dict(row)) for row in rows]
    
    # ═══════════════════════════════════════════════════════════════
    # TRADE LOGGING
    # ═══════════════════════════════════════════════════════════════
    
    def log_trade(self, trade: Trade) -> int:
        """Log a trade to the audit trail."""
        if trade.created_at == 0:
            trade.created_at = time.time()
        
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO trades (engine, symbol, side, size, price, fee,
                                   status, order_id, tx_signature, realized_pnl,
                                   created_at, executed_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.engine, trade.symbol, trade.side, trade.size, trade.price,
                trade.fee, trade.status, trade.order_id, trade.tx_signature,
                trade.realized_pnl, trade.created_at, trade.executed_at,
                trade.metadata
            ))
            return cursor.lastrowid
    
    def update_trade_status(self, trade_id: int, status: str, 
                           executed_at: float = None, 
                           realized_pnl: float = None) -> bool:
        """Update trade status after execution."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE trades 
                SET status = ?, executed_at = COALESCE(?, executed_at),
                    realized_pnl = COALESCE(?, realized_pnl)
                WHERE id = ?
            """, (status, executed_at, realized_pnl, trade_id))
            return True
    
    def get_trades(self, engine: str = None, limit: int = 100, 
                   since: float = None) -> List[Trade]:
        """Get trade history with optional filters."""
        conn = self._get_connection()
        
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if engine:
            query += " AND engine = ?"
            params.append(engine)
        if since:
            query += " AND created_at >= ?"
            params.append(since)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return [Trade(**dict(row)) for row in rows]
    
    def get_realized_pnl(self, engine: str = None, 
                         since: float = None) -> float:
        """Calculate total realized PnL."""
        conn = self._get_connection()
        
        query = "SELECT SUM(realized_pnl) as total FROM trades WHERE status = 'filled'"
        params = []
        
        if engine:
            query += " AND engine = ?"
            params.append(engine)
        if since:
            query += " AND executed_at >= ?"
            params.append(since)
        
        row = conn.execute(query, params).fetchone()
        return row['total'] or 0.0
    
    # ═══════════════════════════════════════════════════════════════
    # SIGNAL LOGGING
    # ═══════════════════════════════════════════════════════════════
    
    def log_signal(self, engine: str, signal_type: str, symbol: str = None,
                   direction: str = None, confidence: float = None,
                   reason: str = None, metadata: dict = None) -> int:
        """Log a trading signal/decision."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO signals (engine, signal_type, symbol, direction,
                                    confidence, reason, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                engine, signal_type, symbol, direction, confidence, reason,
                time.time(), json.dumps(metadata or {})
            ))
            return cursor.lastrowid
    
    # ═══════════════════════════════════════════════════════════════
    # ENGINE STATE SNAPSHOTS
    # ═══════════════════════════════════════════════════════════════
    
    def save_engine_snapshot(self, engine: str, status: str,
                            config: dict = None, state: dict = None) -> int:
        """Save engine state for recovery."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO engine_snapshots (engine, status, config, state, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(engine) DO UPDATE SET
                    status = excluded.status,
                    config = excluded.config,
                    state = excluded.state,
                    created_at = excluded.created_at
            """, (
                engine, status, 
                json.dumps(config or {}),
                json.dumps(state or {}),
                time.time()
            ))
            return cursor.lastrowid
    
    def get_engine_snapshot(self, engine: str) -> Optional[EngineSnapshot]:
        """Get saved engine state."""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM engine_snapshots WHERE engine = ?",
            (engine,)
        ).fetchone()
        
        if row:
            return EngineSnapshot(**dict(row))
        return None
    
    def get_all_engine_snapshots(self) -> List[EngineSnapshot]:
        """Get all engine snapshots."""
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM engine_snapshots").fetchall()
        return [EngineSnapshot(**dict(row)) for row in rows]
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        conn = self._get_connection()
        
        return {
            "positions": conn.execute("SELECT COUNT(*) FROM positions WHERE size != 0").fetchone()[0],
            "trades_total": conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
            "trades_today": conn.execute(
                "SELECT COUNT(*) FROM trades WHERE created_at >= ?",
                (time.time() - 86400,)
            ).fetchone()[0],
            "realized_pnl_total": self.get_realized_pnl(),
            "signals_today": conn.execute(
                "SELECT COUNT(*) FROM signals WHERE created_at >= ?",
                (time.time() - 86400,)
            ).fetchone()[0]
        }
    
    def vacuum(self):
        """Optimize database file size."""
        conn = self._get_connection()
        conn.execute("VACUUM")
    
    def close(self):
        """Close the database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Global singleton accessor
def get_db() -> PersistenceDB:
    """Get the global persistence database instance."""
    return PersistenceDB()
