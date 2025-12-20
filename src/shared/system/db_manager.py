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
            
            # 6. FAST_PATH_ATTEMPTS (ML training data for near-miss execution)
            c.execute("""
            CREATE TABLE IF NOT EXISTS fast_path_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                pair TEXT NOT NULL,
                scan_profit_usd REAL,
                execution_profit_usd REAL,
                profit_delta REAL,
                spread_pct REAL,
                trade_size_usd REAL,
                gas_cost_usd REAL,
                latency_ms REAL,
                success BOOLEAN,
                revert_reason TEXT,
                buy_dex TEXT,
                sell_dex TEXT
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_fastpath_timestamp ON fast_path_attempts(timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fastpath_pair ON fast_path_attempts(pair)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fastpath_success ON fast_path_attempts(success)")

            # Pod State (for smart rotation persistence)
            c.execute("""
            CREATE TABLE IF NOT EXISTS pod_state (
                pod_name TEXT PRIMARY KEY,
                priority REAL NOT NULL,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                best_spread REAL DEFAULT 0,
                last_scan INTEGER DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
            """)

            # Slippage History (for ML slippage prediction)
            c.execute("""
            CREATE TABLE IF NOT EXISTS slippage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                pair TEXT NOT NULL,
                expected_out REAL,
                actual_out REAL,
                slippage_pct REAL,
                trade_size_usd REAL,
                dex TEXT,
                timestamp INTEGER NOT NULL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_slippage_token ON slippage_history(token)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_slippage_timestamp ON slippage_history(timestamp)")

            # Gas History (for gas price optimization)
            c.execute("""
            CREATE TABLE IF NOT EXISTS gas_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gas_cost_usd REAL,
                gas_cost_sol REAL,
                priority_fee REAL,
                hour_utc INTEGER,
                timestamp INTEGER NOT NULL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_gas_hour ON gas_history(hour_utc)")

            # Cycle Timing (for scan optimization)
            c.execute("""
            CREATE TABLE IF NOT EXISTS cycle_timing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pod_name TEXT,
                pairs_scanned INTEGER,
                duration_ms REAL,
                timestamp INTEGER NOT NULL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_cycle_pod ON cycle_timing(pod_name)")

            # Spread Decay (for learning decay velocity per token)
            c.execute("""
            CREATE TABLE IF NOT EXISTS spread_decay (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                initial_spread REAL,
                final_spread REAL,
                decay_pct REAL,
                time_delta_sec REAL,
                decay_per_sec REAL,
                timestamp INTEGER NOT NULL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_decay_pair ON spread_decay(pair)")

            # Pool Index (Meteora + Orca pool discovery)
            c.execute("""
            CREATE TABLE IF NOT EXISTS pool_index (
                pair TEXT PRIMARY KEY,
                meteora_pool TEXT,
                orca_pool TEXT,
                preferred_dex TEXT,
                updated_at REAL
            )
            """)
            
            # Pool Executions (Performance tracking for smart routing)
            c.execute("""
            CREATE TABLE IF NOT EXISTS pool_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                dex TEXT NOT NULL,
                success BOOLEAN,
                latency_ms INTEGER,
                error TEXT,
                timestamp REAL
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_pool_exec_pair ON pool_executions(pair)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_pool_exec_dex ON pool_executions(dex)")

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
    
    # --- Fast-Path Attempt Logging (ML Training Data) ---
    
    def log_fast_path(self, attempt_data: dict):
        """
        Log a fast-path execution attempt for ML training.
        
        Captures the delta between scan-time profit estimate and execution-time
        reality, enabling training of latency-aware profit predictors.
        """
        with self.cursor(commit=True) as c:
            c.execute("""
            INSERT INTO fast_path_attempts (
                timestamp, pair, scan_profit_usd, execution_profit_usd,
                profit_delta, spread_pct, trade_size_usd, gas_cost_usd,
                latency_ms, success, revert_reason, buy_dex, sell_dex
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                attempt_data.get('timestamp', time.time()),
                attempt_data.get('pair'),
                attempt_data.get('scan_profit_usd'),
                attempt_data.get('execution_profit_usd'),
                attempt_data.get('profit_delta'),
                attempt_data.get('spread_pct'),
                attempt_data.get('trade_size_usd'),
                attempt_data.get('gas_cost_usd', 0.02),  # Default gas estimate
                attempt_data.get('latency_ms'),
                attempt_data.get('success', False),
                attempt_data.get('revert_reason'),
                attempt_data.get('buy_dex'),
                attempt_data.get('sell_dex')
            ))
    
    def get_fast_path_stats(self, hours: int = 24) -> dict:
        """Get fast-path attempt statistics for analysis."""
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT 
                pair,
                COUNT(*) as attempts,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                AVG(profit_delta) as avg_delta,
                AVG(latency_ms) as avg_latency,
                SUM(gas_cost_usd) as total_gas_spent
            FROM fast_path_attempts 
            WHERE timestamp > ?
            GROUP BY pair
            ORDER BY attempts DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # LEARNING ANALYTICS - Data-driven optimization from scan history
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def get_spread_variance(self, hours: int = 1) -> list:
        """
        Get spread variance per pair for scan priority optimization.
        High variance = scan more frequently (volatile opportunities).
        Low variance = scan less (stable, predictable).
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT 
                pair,
                COUNT(*) as samples,
                AVG(spread_pct) as avg_spread,
                MAX(spread_pct) - MIN(spread_pct) as spread_range,
                AVG(net_profit_usd) as avg_profit
            FROM spread_observations 
            WHERE timestamp > ?
            GROUP BY pair
            HAVING samples >= 3
            ORDER BY spread_range DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    def get_dex_route_performance(self, hours: int = 24) -> list:
        """
        Analyze which DEX routes (buy→sell) have best execution reliability.
        Returns success rate per route combination.
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT 
                buy_dex || ' → ' || sell_dex as route,
                COUNT(*) as attempts,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                AVG(profit_delta) as avg_decay,
                AVG(latency_ms) as avg_latency
            FROM fast_path_attempts 
            WHERE timestamp > ?
            GROUP BY route
            HAVING attempts >= 2
            ORDER BY successes DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    def get_high_variance_pairs(self, hours: int = 1, min_range: float = 0.3) -> list:
        """
        Get pairs with high spread variance that should be scanned more frequently.
        These are volatile pairs where opportunities appear and disappear quickly.
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT pair
            FROM spread_observations 
            WHERE timestamp > ?
            GROUP BY pair
            HAVING (MAX(spread_pct) - MIN(spread_pct)) > ?
            """, (cutoff, min_range))
            return [row['pair'] for row in c.fetchall()]
    
    def get_liq_failure_rate(self, hours: int = 2) -> dict:
        """
        Calculate LIQ failure rate per pair.
        Pairs with >80% LIQ rate should be temporarily excluded.
        
        Returns: {pair: failure_rate}
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
            SELECT 
                pair,
                COUNT(*) as total,
                SUM(CASE WHEN was_profitable = 0 AND net_profit_usd < -0.05 THEN 1 ELSE 0 END) as liq_failures
            FROM spread_observations 
            WHERE timestamp > ?
            GROUP BY pair
            HAVING total >= 5
            """, (cutoff,))
            
            result = {}
            for row in c.fetchall():
                total = row['total'] or 1
                failures = row['liq_failures'] or 0
                result[row['pair']] = failures / total
            return result
    
    def get_profitable_hours(self, days: int = 7) -> list:
        """
        Analyze which hours of day have highest profitable spread frequency.
        Returns list of hours (0-23) sorted by profitability.
        """
        with self.cursor() as c:
            cutoff = time.time() - (days * 86400)
            c.execute("""
            SELECT 
                CAST((timestamp % 86400) / 3600 AS INTEGER) as hour_utc,
                COUNT(*) as total_spreads,
                SUM(CASE WHEN was_profitable THEN 1 ELSE 0 END) as profitable_count,
                AVG(CASE WHEN was_profitable THEN spread_pct ELSE NULL END) as avg_profitable_spread
            FROM spread_observations 
            WHERE timestamp > ?
            GROUP BY hour_utc
            ORDER BY profitable_count DESC
            """, (cutoff,))
            return [dict(row) for row in c.fetchall()]
    
    def get_pair_success_rate(self, pair: str, hours: int = 24) -> dict:
        """
        Get success rate for a pair at different spread levels.
        
        Returns: {
            'total_attempts': int,
            'successes': int,
            'success_rate': float,
            'avg_spread_at_success': float,
            'min_spread_at_success': float
        }
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            
            # From fast_path_attempts
            c.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                AVG(CASE WHEN success THEN spread_pct ELSE NULL END) as avg_spread_success,
                MIN(CASE WHEN success THEN spread_pct ELSE NULL END) as min_spread_success
            FROM fast_path_attempts 
            WHERE pair LIKE ? AND timestamp > ?
            """, (f"{pair.split('/')[0]}%", cutoff))
            
            row = c.fetchone()
            if not row or not row['total']:
                return {'total_attempts': 0, 'successes': 0, 'success_rate': 0, 
                        'avg_spread_at_success': 0, 'min_spread_at_success': 0}
            
            total = row['total'] or 0
            successes = row['successes'] or 0
            
            return {
                'total_attempts': total,
                'successes': successes,
                'success_rate': successes / total if total > 0 else 0,
                'avg_spread_at_success': row['avg_spread_success'] or 0,
                'min_spread_at_success': row['min_spread_success'] or 0
            }
    
    def get_minimum_profitable_spread(self, pair: str, hours: int = 24) -> float:
        """
        Get the minimum spread at which this pair was historically profitable.
        
        Used for smart filtering: if current spread < min_profitable, skip.
        Returns 0.0 if no data (allows all spreads).
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            
            c.execute("""
            SELECT MIN(spread_pct) as min_spread
            FROM fast_path_attempts 
            WHERE pair LIKE ? AND success = 1 AND timestamp > ?
            """, (f"{pair.split('/')[0]}%", cutoff))
            
            row = c.fetchone()
            if row and row['min_spread']:
                return float(row['min_spread'])
            return 0.0

    # --- Pod State (Smart Rotation Persistence) ---
    
    def save_pod_state(self, pod_name: str, state: dict):
        """Save pod state for persistence across restarts."""
        with self.cursor(commit=True) as c:
            c.execute("""
                INSERT OR REPLACE INTO pod_state 
                (pod_name, priority, success_count, fail_count, best_spread, last_scan, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pod_name,
                state.get('priority', 1),
                state.get('success_count', 0),
                state.get('fail_count', 0),
                state.get('best_spread', 0),
                state.get('last_scan', 0),
                int(time.time())
            ))
    
    def load_all_pod_states(self) -> dict:
        """Load all pod states from DB."""
        result = {}
        with self.cursor() as c:
            c.execute("SELECT * FROM pod_state")
            rows = c.fetchall()
            for row in rows:
                result[row['pod_name']] = {
                    'priority': row['priority'],
                    'success_count': row['success_count'],
                    'fail_count': row['fail_count'],
                    'best_spread': row['best_spread'],
                    'last_scan': row['last_scan'],
                    'cooldown_until': 0,  # Reset cooldown on restart
                }
        return result

    # --- Slippage Prediction (ML-based) ---
    
    def log_slippage(self, token: str, pair: str, expected_out: float, actual_out: float, 
                     trade_size_usd: float, dex: str):
        """Log actual slippage for ML training."""
        slippage_pct = ((expected_out - actual_out) / expected_out * 100) if expected_out > 0 else 0
        with self.cursor(commit=True) as c:
            c.execute("""
                INSERT INTO slippage_history 
                (token, pair, expected_out, actual_out, slippage_pct, trade_size_usd, dex, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (token, pair, expected_out, actual_out, slippage_pct, trade_size_usd, dex, int(time.time())))
    
    def get_expected_slippage(self, token: str, trade_size_usd: float = 50, hours: int = 24) -> float:
        """
        Get expected slippage for a token based on historical data.
        Returns estimated slippage as percentage (e.g., 0.5 = 0.5% slippage).
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            # Get average slippage for similar trade sizes (within 50% of target size)
            c.execute("""
                SELECT AVG(slippage_pct) as avg_slippage, COUNT(*) as samples
                FROM slippage_history 
                WHERE token = ? 
                AND timestamp > ?
                AND trade_size_usd BETWEEN ? AND ?
            """, (token, cutoff, trade_size_usd * 0.5, trade_size_usd * 1.5))
            row = c.fetchone()
            if row and row['samples'] >= 3 and row['avg_slippage']:
                return float(row['avg_slippage'])
            
            # Fallback: get average across all sizes
            c.execute("""
                SELECT AVG(slippage_pct) as avg_slippage
                FROM slippage_history 
                WHERE token = ? AND timestamp > ?
            """, (token, cutoff))
            row = c.fetchone()
            if row and row['avg_slippage']:
                return float(row['avg_slippage'])
            
            return 0.0  # No data = assume no extra slippage

    # --- Gas Price Learning ---
    
    def log_gas(self, gas_cost_usd: float, gas_cost_sol: float = 0, priority_fee: float = 0):
        """Log gas cost for time-of-day optimization."""
        from datetime import datetime
        hour_utc = datetime.utcnow().hour
        with self.cursor(commit=True) as c:
            c.execute("""
                INSERT INTO gas_history (gas_cost_usd, gas_cost_sol, priority_fee, hour_utc, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (gas_cost_usd, gas_cost_sol, priority_fee, hour_utc, int(time.time())))
    
    def get_cheap_gas_hours(self, days: int = 7) -> list:
        """Get hours with historically cheap gas."""
        with self.cursor() as c:
            cutoff = time.time() - (days * 86400)
            c.execute("""
                SELECT hour_utc, AVG(gas_cost_usd) as avg_gas
                FROM gas_history 
                WHERE timestamp > ?
                GROUP BY hour_utc
                HAVING COUNT(*) >= 3
                ORDER BY avg_gas ASC
                LIMIT 6
            """, (cutoff,))
            return [row['hour_utc'] for row in c.fetchall()]

    # --- Cycle Time Optimization ---
    
    def log_cycle(self, pod_name: str, pairs_scanned: int, duration_ms: float):
        """Log scan cycle duration for optimization."""
        with self.cursor(commit=True) as c:
            c.execute("""
                INSERT INTO cycle_timing (pod_name, pairs_scanned, duration_ms, timestamp)
                VALUES (?, ?, ?, ?)
            """, (pod_name, pairs_scanned, duration_ms, int(time.time())))
    
    def get_avg_cycle_time(self, pod_name: str = None) -> float:
        """Get average cycle time (ms) for a pod or all pods."""
        with self.cursor() as c:
            if pod_name:
                c.execute("""
                    SELECT AVG(duration_ms) as avg_time
                    FROM cycle_timing 
                    WHERE pod_name = ?
                """, (pod_name,))
            else:
                c.execute("SELECT AVG(duration_ms) as avg_time FROM cycle_timing")
            row = c.fetchone()
            return float(row['avg_time']) if row and row['avg_time'] else 0.0

    # --- Spread Decay Learning ---
    
    def log_spread_decay(self, pair: str, initial_spread: float, final_spread: float, time_delta_sec: float):
        """Log spread decay between consecutive scans for ML learning."""
        if time_delta_sec <= 0:
            return
        decay_pct = initial_spread - final_spread  # How much it dropped
        decay_per_sec = decay_pct / time_delta_sec
        with self.cursor(commit=True) as c:
            c.execute("""
                INSERT INTO spread_decay 
                (pair, initial_spread, final_spread, decay_pct, time_delta_sec, decay_per_sec, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (pair, initial_spread, final_spread, decay_pct, time_delta_sec, decay_per_sec, int(time.time())))
    
    def get_decay_velocity(self, pair: str, hours: int = 24) -> float:
        """
        Get expected decay velocity for a pair (% per second).
        Positive = spread shrinks over time (bad for arbitrage).
        Negative = spread grows over time (rare).
        """
        with self.cursor() as c:
            cutoff = time.time() - (hours * 3600)
            c.execute("""
                SELECT AVG(decay_per_sec) as avg_decay, COUNT(*) as samples
                FROM spread_decay 
                WHERE pair = ? AND timestamp > ?
            """, (pair, cutoff))
            row = c.fetchone()
            if row and row['samples'] >= 3 and row['avg_decay'] is not None:
                return float(row['avg_decay'])
            return 0.0  # No data
    
    def get_stable_pairs(self, min_samples: int = 5, max_decay: float = 0.05) -> list:
        """Get pairs with stable spreads (low decay velocity)."""
        with self.cursor() as c:
            cutoff = time.time() - 3600  # Last hour
            c.execute("""
                SELECT pair, AVG(decay_per_sec) as avg_decay, COUNT(*) as samples
                FROM spread_decay 
                WHERE timestamp > ?
                GROUP BY pair
                HAVING samples >= ? AND ABS(avg_decay) < ?
                ORDER BY ABS(avg_decay) ASC
            """, (cutoff, min_samples, max_decay))
            return [row['pair'] for row in c.fetchall()]

# Global Accessor
db_manager = DBManager()
