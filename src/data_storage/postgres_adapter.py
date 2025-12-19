"""
V44.0: PostgreSQL + TimescaleDB Adapter
========================================
Production-grade database adapter with connection pooling.

Features:
- Connection pooling for concurrent access
- TimescaleDB hypertable for time-series optimization
- Same interface as SQLite adapter for seamless switching
- Batch inserts for high-frequency tick data

Dependencies:
    pip install psycopg2-binary

Usage:
    from src.data_storage.postgres_adapter import PostgresAdapter
    db = PostgresAdapter()
    db.insert_tick(mint, price, volume, liquidity, latency)
"""

import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import pool, sql
    from psycopg2.extras import execute_batch, RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

from config.db_config import (
    POSTGRES_URL, 
    POSTGRES_MARKET_DATA_SCHEMA,
    PG_POOL_MIN_CONN,
    PG_POOL_MAX_CONN
)


class PostgresAdapter:
    """
    V44.0: PostgreSQL adapter with TimescaleDB support.
    
    Thread-safe connection pooling for concurrent engine access.
    """
    
    def __init__(self, connection_url: str = None):
        """
        Initialize PostgreSQL adapter with connection pool.
        
        Args:
            connection_url: PostgreSQL connection URL (defaults to DATABASE_URL env var)
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
        
        self.connection_url = connection_url or POSTGRES_URL
        
        if not self.connection_url:
            raise EnvironmentError(
                "DATABASE_URL environment variable required for PostgreSQL.\n"
                "Format: postgresql://user:password@host:port/dbname"
            )
        
        print(f"🌐 [POSTGRES] Initializing connection pool...")
        
        # Create connection pool
        self._pool = pool.ThreadedConnectionPool(
            minconn=PG_POOL_MIN_CONN,
            maxconn=PG_POOL_MAX_CONN,
            dsn=self.connection_url
        )
        
        # Initialize schema
        self._init_schema()
        
        print(f"✅ [POSTGRES] Connection pool ready (min={PG_POOL_MIN_CONN}, max={PG_POOL_MAX_CONN})")
    
    @contextmanager
    def _get_connection(self):
        """Get connection from pool with automatic return."""
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            self._pool.putconn(conn)
    
    def _init_schema(self):
        """Initialize database schema with TimescaleDB hypertable."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    # 1. Enable TimescaleDB extension (if available)
                    try:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
                        print("   📊 TimescaleDB extension enabled")
                        self._has_timescaledb = True
                    except psycopg2.Error:
                        print("   ⚠️ TimescaleDB not available (using standard PostgreSQL)")
                        self._has_timescaledb = False
                    
                    # 2. Create market_data table
                    cur.execute(POSTGRES_MARKET_DATA_SCHEMA)
                    
                    # 3. Create index for fast mint queries
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_market_data_mint_ts 
                        ON market_data (token_mint, timestamp DESC)
                    """)
                    
                    # 4. Convert to hypertable (TimescaleDB)
                    if self._has_timescaledb:
                        try:
                            cur.execute("""
                                SELECT create_hypertable(
                                    'market_data', 
                                    'timestamp',
                                    if_not_exists => TRUE,
                                    chunk_time_interval => INTERVAL '1 day'
                                )
                            """)
                            print("   📊 Hypertable configured (1-day chunks)")
                        except psycopg2.Error as e:
                            if "already a hypertable" not in str(e):
                                print(f"   ⚠️ Hypertable creation: {e}")
                    
                    conn.commit()
                    print("   ✅ Schema initialized")
                    
                except psycopg2.Error as e:
                    conn.rollback()
                    print(f"   ❌ Schema init error: {e}")
                    raise
    
    # ═══════════════════════════════════════════════════════════════════════
    # WRITE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════
    
    def insert_tick(
        self, 
        mint: str, 
        price: float, 
        volume: float = 0.0, 
        liq: float = 0.0, 
        latency: int = 0
    ) -> bool:
        """
        Insert a single tick (OHLC = same price for tick data).
        
        Same interface as SQLite db_manager for seamless switching.
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO market_data 
                        (timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms)
                        VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (timestamp, token_mint) DO UPDATE SET
                            close = EXCLUDED.close,
                            volume_h1 = EXCLUDED.volume_h1,
                            liquidity_usd = EXCLUDED.liquidity_usd,
                            latency_ms = EXCLUDED.latency_ms
                    """, (mint, price, price, price, price, volume, liq, latency))
                    conn.commit()
                    return True
        except psycopg2.Error as e:
            # Silent fail to not block broker loop
            return False
    
    def insert_tick_batch(self, ticks: List[Tuple]) -> int:
        """
        Batch insert multiple ticks for efficiency.
        
        Args:
            ticks: List of (mint, price, volume, liq, latency) tuples
            
        Returns:
            Number of ticks inserted
        """
        if not ticks:
            return 0
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Prepare data with timestamp
                    data = [
                        (datetime.utcnow(), mint, price, price, price, price, vol, liq, lat)
                        for mint, price, vol, liq, lat in ticks
                    ]
                    
                    execute_batch(cur, """
                        INSERT INTO market_data 
                        (timestamp, token_mint, open, high, low, close, volume_h1, liquidity_usd, latency_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (timestamp, token_mint) DO NOTHING
                    """, data)
                    
                    conn.commit()
                    return len(ticks)
        except psycopg2.Error as e:
            print(f"   ⚠️ Batch insert error: {e}")
            return 0
    
    # ═══════════════════════════════════════════════════════════════════════
    # READ OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_history(
        self, 
        mint: str, 
        start_ts: float = 0, 
        end_ts: float = None,
        limit: int = 10000
    ) -> List[Tuple]:
        """
        Fetch historical data for a token.
        
        Same interface as SQLite db_manager.
        
        Returns:
            List of (timestamp, open, high, low, close, volume) tuples
        """
        if end_ts is None:
            end_ts = time.time()
        
        # Convert Unix timestamps to datetime
        start_dt = datetime.utcfromtimestamp(start_ts)
        end_dt = datetime.utcfromtimestamp(end_ts)
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            EXTRACT(EPOCH FROM timestamp) as ts,
                            open, high, low, close, volume_h1
                        FROM market_data
                        WHERE token_mint = %s 
                          AND timestamp >= %s 
                          AND timestamp <= %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                    """, (mint, start_dt, end_dt, limit))
                    
                    return cur.fetchall()
        except psycopg2.Error as e:
            print(f"   ❌ History fetch error: {e}")
            return []
    
    def get_all_mints(self) -> List[str]:
        """Get list of all unique token mints in database."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT DISTINCT token_mint FROM market_data")
                    return [row[0] for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"   ❌ Get mints error: {e}")
            return []
    
    def get_recent_data(self, lookback_hours: int = 24, limit: int = 50000) -> List[Dict]:
        """
        Get recent data for all tokens (for ML training).
        
        Returns:
            List of dicts with all columns
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            EXTRACT(EPOCH FROM timestamp) as timestamp,
                            token_mint,
                            close,
                            volume_h1,
                            liquidity_usd,
                            latency_ms
                        FROM market_data
                        WHERE timestamp >= NOW() - INTERVAL '%s hours'
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (lookback_hours, limit))
                    
                    return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"   ❌ Recent data error: {e}")
            return []
    
    # ═══════════════════════════════════════════════════════════════════════
    # MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM market_data")
                    total_rows = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(DISTINCT token_mint) FROM market_data")
                    unique_tokens = cur.fetchone()[0]
                    
                    cur.execute("""
                        SELECT MIN(timestamp), MAX(timestamp) FROM market_data
                    """)
                    min_ts, max_ts = cur.fetchone()
                    
                    return {
                        "total_rows": total_rows,
                        "unique_tokens": unique_tokens,
                        "oldest_record": str(min_ts) if min_ts else None,
                        "newest_record": str(max_ts) if max_ts else None,
                        "has_timescaledb": self._has_timescaledb,
                        "pool_min": PG_POOL_MIN_CONN,
                        "pool_max": PG_POOL_MAX_CONN
                    }
        except psycopg2.Error as e:
            return {"error": str(e)}
    
    def close(self):
        """Close all connections in pool."""
        if self._pool:
            self._pool.closeall()
            print("🔌 [POSTGRES] Connection pool closed")
    
    def __repr__(self):
        return f"<PostgresAdapter pool={PG_POOL_MIN_CONN}-{PG_POOL_MAX_CONN}>"


# ═══════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("PostgreSQL Adapter Test")
    print("=" * 60)
    
    try:
        db = PostgresAdapter()
        print(f"\n✅ Adapter: {db}")
        print(f"\n📊 Stats: {db.get_stats()}")
        
        # Test insert
        success = db.insert_tick("TEST-MINT", 123.45, 1000, 50000, 15)
        print(f"\n✅ Insert test: {success}")
        
        # Test history
        history = db.get_history("TEST-MINT", limit=10)
        print(f"\n📜 History: {len(history)} rows")
        
        db.close()
        print("\n✅ Test complete!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
