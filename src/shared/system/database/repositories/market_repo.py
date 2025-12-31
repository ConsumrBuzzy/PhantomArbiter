import time
from typing import List, Optional, Dict
from src.shared.system.database.repositories.base import BaseRepository


class MarketRepository(BaseRepository):
    """
    Handles Market Data Analytics:
    - Spreads & Opportunities
    - Pool Registry & Liquidity
    - Gas Prices & Cycle Timing
    """

    def init_table(self):
        with self.db.cursor(commit=True) as c:
            # 1. Spreads
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
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_spreads_pair ON spread_observations(pair)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_spreads_timestamp ON spread_observations(timestamp)"
            )

            # 2. Pools
            c.execute("""
            CREATE TABLE IF NOT EXISTS pool_registry (
                mint TEXT PRIMARY KEY,
                symbol TEXT,
                has_jupiter BOOLEAN DEFAULT 0,
                has_raydium BOOLEAN DEFAULT 0,
                has_orca BOOLEAN DEFAULT 0,
                has_meteora BOOLEAN DEFAULT 0,
                last_checked REAL
            )
            """)

            # 3. Known Pools (Graph Nodes) - Phase 23
            c.execute("""
            CREATE TABLE IF NOT EXISTS known_pools (
                address TEXT PRIMARY KEY,
                token_a TEXT NOT NULL,
                token_b TEXT NOT NULL,
                dex_label TEXT,
                liquidity_usd REAL DEFAULT 0,
                vol_24h REAL DEFAULT 0,
                last_updated REAL
            )
            """)

            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_pools_tokens ON known_pools(token_a, token_b)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_pools_dex ON known_pools(dex_label)"
            )

            # 3. Cycle Timing
            c.execute("""
            CREATE TABLE IF NOT EXISTS cycle_timing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pod_name TEXT,
                pairs_scanned INTEGER,
                duration_ms REAL,
                timestamp INTEGER NOT NULL
            )
            """)

    def log_spread(self, spread_data: dict):
        """Log a spread observation."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            INSERT INTO spread_observations (
                timestamp, pair, spread_pct, net_profit_usd,
                buy_dex, sell_dex, buy_price, sell_price,
                fees_usd, trade_size_usd, was_profitable, was_executed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    spread_data.get("timestamp", time.time()),
                    spread_data.get("pair"),
                    spread_data.get("spread_pct"),
                    spread_data.get("net_profit_usd"),
                    spread_data.get("buy_dex"),
                    spread_data.get("sell_dex"),
                    spread_data.get("buy_price"),
                    spread_data.get("sell_price"),
                    spread_data.get("fees_usd", 0),
                    spread_data.get("trade_size_usd", 0),
                    spread_data.get("was_profitable", False),
                    spread_data.get("was_executed", False),
                ),
            )

    def register_pool(self, mint: str, dex: str, symbol: str = None):
        """Update pool registry."""
        col = f"has_{dex.lower()}"
        if col not in ["has_jupiter", "has_raydium", "has_orca", "has_meteora"]:
            return

        with self.db.cursor(commit=True) as c:
            c.execute("SELECT mint FROM pool_registry WHERE mint = ?", (mint,))
            if c.fetchone():
                c.execute(
                    f"UPDATE pool_registry SET {col} = 1, last_checked = ? WHERE mint = ?",
                    (time.time(), mint),
                )
            else:
                c.execute(
                    f"INSERT INTO pool_registry (mint, symbol, {col}, last_checked) VALUES (?, ?, 1, ?)",
                    (mint, symbol, time.time()),
                )

    def get_pool_registry(self, mint: str) -> Optional[Dict]:
        return self._fetchone("SELECT * FROM pool_registry WHERE mint = ?", (mint,))

    def log_cycle(self, pod_name: str, pairs_scanned: int, duration_ms: float):
        """Log scan cycle duration."""
        self._execute(
            """
            INSERT INTO cycle_timing (pod_name, pairs_scanned, duration_ms, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (pod_name, pairs_scanned, duration_ms, int(time.time())),
            commit=True,
        )

    def save_pool(
        self,
        address: str,
        token_a: str,
        token_b: str,
        dex_label: str,
        liquidity_usd: float = 0,
        vol_24h: float = 0,
    ):
        """Upsert a known pool node."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            INSERT INTO known_pools (address, token_a, token_b, dex_label, liquidity_usd, vol_24h, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                liquidity_usd=excluded.liquidity_usd,
                vol_24h=excluded.vol_24h,
                last_updated=excluded.last_updated
            """,
                (
                    address,
                    token_a,
                    token_b,
                    dex_label,
                    liquidity_usd,
                    vol_24h,
                    time.time(),
                ),
            )

    def get_all_pools(self) -> List[Dict]:
        """Fetch all pools for graph reconstruction."""
        with self.db.cursor() as c:
            c.execute("SELECT * FROM known_pools")
            return [dict(row) for row in c.fetchall()]
