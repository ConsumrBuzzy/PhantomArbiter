import sqlite3
import time
import os
from contextlib import contextmanager
from src.shared.system.logging import Logger

class DBManager:
    """
    V10.5: Database Manager (SQLite)
    Singleton class for ACID-compliant persistence.
    Replaces JSON/CSV files for Trades and Positions.
    """
    _instance = None
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "trading_journal.db")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """Initialize connection and schema."""
        self._ensure_data_dir()
        self._init_schema()
    
    def wait_for_connection(self, timeout=2.0):
        """
        V11.6: Ensure database connection is ready before queries.
        Returns True if connection is verified, False on timeout.
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            try:
                with self.cursor() as c:
                    c.execute("SELECT 1")
                    result = c.fetchone()
                    if result:
                        Logger.info("   📦 DBManager connection verified")
                        return True
            except Exception as e:
                Logger.debug(f"   ⏳ DB not ready: {e}")
                time.sleep(0.5)
        
        Logger.warning("   ⚠️ DBManager connection timeout - proceeding anyway")
        return False

    def _ensure_data_dir(self):
        directory = os.path.dirname(self.DB_PATH)
        if not os.path.exists(directory):
            os.makedirs(directory)

    def get_connection(self):
        """Get a configured SQLite connection."""
        conn = sqlite3.connect(self.DB_PATH, timeout=10.0) # generous timeout for concurrency
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

    def _init_schema(self):
        """Create tables if they don't exist."""
        with self.cursor(commit=True) as c:
            # 1. TRADES (Audit) - V46.1: Added execution data columns
            c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                size_usd REAL,
                pnl_usd REAL,
                net_pnl_pct REAL,
                exit_reason TEXT,
                timestamp REAL,
                is_win BOOLEAN,
                engine_name TEXT DEFAULT 'UNKNOWN',
                slippage_pct REAL DEFAULT 0,
                slippage_usd REAL DEFAULT 0,
                fees_usd REAL DEFAULT 0,
                liquidity_usd REAL DEFAULT 0,
                is_volatile BOOLEAN DEFAULT 0
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            
            # V39.9: Migration - Add engine_name column if missing (for existing DBs)
            # Must happen BEFORE creating index on the column
            try:
                c.execute("SELECT engine_name FROM trades LIMIT 1")
            except:
                try:
                    c.execute("ALTER TABLE trades ADD COLUMN engine_name TEXT DEFAULT 'UNKNOWN'")
                    Logger.info("📦 [DB] Migrated trades table: added engine_name column")
                except:
                    pass  # Column might already exist
            
            # Now safe to create index on engine_name
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_engine ON trades(engine_name)")
            
            # V46.1: Migration - Add execution data columns for ML feedback loop
            for col_name, col_default in [
                ('slippage_pct', '0'),
                ('slippage_usd', '0'),
                ('fees_usd', '0'),
                ('liquidity_usd', '0'),
                ('is_volatile', '0')
            ]:
                try:
                    c.execute(f"SELECT {col_name} FROM trades LIMIT 1")
                except:
                    try:
                        c.execute(f"ALTER TABLE trades ADD COLUMN {col_name} REAL DEFAULT {col_default}")
                        Logger.info(f"📦 [DB] Migrated trades table: added {col_name} column")
                    except:
                        pass  # Column might already exist

            # 2. POSITIONS (State)
            c.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                entry_price REAL,
                cost_basis REAL,
                entry_time REAL,
                max_price_achieved REAL,
                trailing_stop_price REAL,
                token_balance REAL,
                updated_at REAL
            )
            """)
            
            # 3. ASSETS (Config/Discovery)
            c.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                symbol TEXT PRIMARY KEY,
                mint TEXT NOT NULL,
                category TEXT DEFAULT 'WATCH',
                safety_score REAL DEFAULT 0,
                updated_at REAL
            )
            """)
            
            # 4. TOKENS (V67.9: Token Registry for metadata)
            c.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                price REAL,
                liquidity REAL,
                volume_24h REAL,
                dex TEXT,
                source TEXT,
                first_seen REAL,
                last_seen REAL
            )
            """)
            
            # 5. SPREAD_OBSERVATIONS (Arbiter training data)
            c.execute("""
            CREATE TABLE IF NOT EXISTS spread_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                pair TEXT NOT NULL,
                spread_pct REAL,
                net_profit_usd REAL,
                buy_dex TEXT,
                sell_dex TEXT,
                buy_price REAL,
                sell_price REAL,
                fees_usd REAL,
                trade_size_usd REAL,
                was_profitable BOOLEAN,
                was_executed BOOLEAN DEFAULT 0
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_spreads_timestamp ON spread_observations(timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_spreads_pair ON spread_observations(pair)")

    # --- Position Operations (Replacing JSON) ---

    def save_position(self, symbol, data):
        """Upsert position state."""
        with self.cursor(commit=True) as c:
            c.execute("""
            INSERT INTO positions (
                symbol, entry_price, cost_basis, entry_time,
                max_price_achieved, trailing_stop_price, token_balance, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                entry_price=excluded.entry_price,
                cost_basis=excluded.cost_basis,
                entry_time=excluded.entry_time,
                max_price_achieved=excluded.max_price_achieved,
                trailing_stop_price=excluded.trailing_stop_price,
                token_balance=excluded.token_balance,
                updated_at=excluded.updated_at
            """, (
                symbol,
                data.get('entry_price', 0),
                data.get('cost_basis', 0),
                data.get('entry_time', 0) or time.time(),
                data.get('max_price_achieved', 0),
                data.get('trailing_stop_price', 0),
                data.get('token_balance', 0),
                time.time()
            ))

    def get_position(self, symbol):
        """Retrieve position state."""
        with self.cursor() as c:
            c.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,))
            row = c.fetchone()
            if row:
                return dict(row)
            return None

    def delete_position(self, symbol):
        """Remove position state (on exit)."""
        with self.cursor(commit=True) as c:
            c.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))

    def get_all_positions(self):
        """Get all active positions."""
        with self.cursor() as c:
            c.execute("SELECT * FROM positions")
            return [dict(row) for row in c.fetchall()]

    # --- Trade Logging (Audit) ---

    def log_trade(self, trade_data):
        """Insert a completed trade record. V46.1: Now includes execution data for ML."""
        with self.cursor(commit=True) as c:
            c.execute("""
            INSERT INTO trades (
                symbol, entry_price, exit_price, size_usd,
                pnl_usd, net_pnl_pct, exit_reason, timestamp, is_win, engine_name,
                slippage_pct, slippage_usd, fees_usd, liquidity_usd, is_volatile
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_data.get('symbol'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                trade_data.get('size_usd'),
                trade_data.get('pnl_usd'),
                trade_data.get('net_pnl_pct'),
                trade_data.get('exit_reason'),
                trade_data.get('timestamp', time.time()),
                trade_data.get('is_win', False),
                trade_data.get('engine_name', 'UNKNOWN'),
                # V46.1: Execution data for ML feedback loop
                trade_data.get('slippage_pct', 0),
                trade_data.get('slippage_usd', 0),
                trade_data.get('fees_usd', 0),
                trade_data.get('liquidity_usd', 0),
                trade_data.get('is_volatile', False)
            ))

    def get_win_rate(self, limit=20) -> float:
        """
        Calculate rolling win rate for the last N trades.
        Returns float between 0.0 and 1.0.
        """
        with self.cursor() as c:
            # V11.0: Precise SQLite calculation
            c.execute("""
            SELECT 
                CAST(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
            FROM (
                SELECT is_win FROM trades 
                ORDER BY timestamp DESC 
                LIMIT ?
            )
            """, (limit,))
            result = c.fetchone()[0]
            return float(result) if result is not None else 0.5 # Default to neutral if no history

    def get_total_trades(self) -> int:
        """V16.1: Get total number of trades for DSA warmup logic."""
        with self.cursor() as c:
            c.execute("SELECT COUNT(*) FROM trades")
            result = c.fetchone()[0]
            return int(result) if result else 0
    
    # --- Arbiter Spread Logging ---
    
    def log_spread(self, spread_data: dict):
        """Log a spread observation for training data."""
        with self.cursor(commit=True) as c:
            c.execute("""
            INSERT INTO spread_observations (
                timestamp, pair, spread_pct, net_profit_usd,
                buy_dex, sell_dex, buy_price, sell_price,
                fees_usd, trade_size_usd, was_profitable, was_executed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                spread_data.get('timestamp', time.time()),
                spread_data.get('pair'),
                spread_data.get('spread_pct'),
                spread_data.get('net_profit_usd'),
                spread_data.get('buy_dex'),
                spread_data.get('sell_dex'),
                spread_data.get('buy_price'),
                spread_data.get('sell_price'),
                spread_data.get('fees_usd', 0),
                spread_data.get('trade_size_usd', 0),
                spread_data.get('was_profitable', False),
                spread_data.get('was_executed', False)
            ))
    
    def get_spread_stats(self, hours: int = 24) -> dict:
        """Get spread statistics for analysis."""
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT 
                pair,
                COUNT(*) as observations,
                AVG(spread_pct) as avg_spread,
                MAX(spread_pct) as max_spread,
                SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as profitable_count,
                SUM(CASE WHEN was_executed THEN 1 ELSE 0 END) as executed_count
            FROM spread_observations 
            WHERE timestamp > ?
            GROUP BY pair
            ORDER BY max_spread DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]

# Global Accessor
db_manager = DBManager()
