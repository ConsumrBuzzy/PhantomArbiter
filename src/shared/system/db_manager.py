from typing import List, Dict, Optional
from src.shared.system.database.core import DatabaseCore
from src.shared.system.database.repositories.trade_repo import TradeRepository
from src.shared.system.database.repositories.position_repo import PositionRepository
from src.shared.system.database.repositories.market_repo import MarketRepository
from src.shared.system.database.repositories.market_repo import MarketRepository
from src.shared.system.database.repositories.wallet_repo import WalletRepository
from src.shared.system.database.repositories.token_repo import TokenRepository

class DBManager:
    """
    V12.0: Database Manager Facade.
    Delegates operations to improved modular repositories.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DBManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        # 1. Initialize Core (Connection, WAL)
        self.core = DatabaseCore()
        
        # 2. Initialize Repositories
        self.trades = TradeRepository(self.core)
        self.positions = PositionRepository(self.core)
        self.market = MarketRepository(self.core)
        self.wallets = WalletRepository(self.core)
        
        # 3. Initialize Schemas
        self.trades.init_table()
        self.positions.init_table()
        self.market.init_table()
        self.wallets.init_table()
        self.tokens = TokenRepository(self.core)
        self.tokens.init_table()

    def wait_for_connection(self, timeout=2.0) -> bool:
        return self.core.wait_for_connection(timeout)

    # ═══════════════════════════════════════════════════════════════
    # DELEGATED METHODS (Maintaining API Compatibility)
    # ═══════════════════════════════════════════════════════════════

    # --- TRADES ---
    def log_trade(self, trade_data: dict):
        self.trades.log_trade(trade_data)

    def get_win_rate(self, limit=20) -> float:
        return self.trades.get_win_rate(limit)
        
    def get_total_trades(self) -> int:
        return self.trades.get_total_trades()

    # --- POSITIONS ---
    def save_position(self, symbol, data):
        self.positions.save_position(symbol, data)

    def get_position(self, symbol):
        return self.positions.get_position(symbol)

    def delete_position(self, symbol):
        self.positions.delete_position(symbol)

    def get_all_positions(self):
        return self.positions.get_all_positions()

    # --- MARKET / SPREADS ---
    def log_spread(self, spread_data: dict):
        self.market.log_spread(spread_data)
        
    def register_pool(self, mint: str, dex: str, symbol: str = None):
        self.market.register_pool(mint, dex, symbol)
        
    def get_pool_registry(self, mint: str) -> dict:
        return self.market.get_pool_registry(mint)
        
    def log_cycle(self, pod_name: str, pairs_scanned: int, duration_ms: float):
        self.market.log_cycle(pod_name, pairs_scanned, duration_ms)

    # --- WALLETS ---
    def add_target_wallet(self, address: str, tags: str = "ALFA"):
        self.wallets.add_target_wallet(address, tags)
        
    def get_target_wallets(self) -> List[str]:
        return self.wallets.get_target_wallets()

    # --- TOKENS (METADATA) ---
    def save_token_metadata(self, identity, risk=None):
        self.tokens.save_token(identity, risk)
        
    def get_token_metadata(self, mint: str):
        return self.tokens.get_token(mint)

# Global Instance
db_manager = DBManager()
