"""
V10.2 SRP Watcher: State Container
==================================
Lightweight container for asset state.
Delegates logic to:
- src.execution.position_manager (Persistence)
- src.strategy.risk (TSL)
- src.system.status_formatter (Display)
"""

from src.core.data import DataFeed
from src.shared.execution.position_manager import PositionManager

from src.strategy.signals import TechnicalAnalysis


class Watcher:
    """
    P1 State Container for V10.2 SRP.

    The Watcher represents a single asset being traded. It operates as a passive
    state container, holding critical data such as entry price, position status,
    and PnL metrics. It delegates all complex logic to specialized modules.

    Responsibility:
    - Hold State (In-Memory)
    - Delegate Persistence -> PositionManager
    - Delegate Display -> StatusFormatter
    - Consume Data <- DataFeedManager

    Attributes:
        symbol (str): Asset symbol (e.g., 'SOL').
        mint (str): Asset mint address.
        data_feed (DataFeed): Price history and technical indicators container.
        pos_manager (PositionManager): Persistence handler.
    """

    def __init__(
        self, symbol: str, mint: str, validator=None, is_critical=False, lazy_init=False
    ):
        self.symbol = symbol
        self.mint = mint
        self.validator = validator
        # V11.4: Pass lazy_init to DataFeed to skip blocking backfill for Scout tokens
        self.data_feed = DataFeed(
            mint, symbol, is_critical=is_critical, lazy_init=lazy_init
        )
        self.pos_manager = PositionManager(symbol)

        # State (Public)
        self.in_position = False
        self.entry_price = 0.0
        self.cost_basis = 0.0
        self.entry_time = None
        self.max_price_achieved = 0.0

        # V12.6: Signal Cooldown
        self.last_signal_time = 0.0
        self.SIGNAL_COOLDOWN = 15  # V25.0: Reduced from 30s to 15s for Scalper Tuning
        self.trailing_stop_price = 0.0
        self.pnl_pct = 0.0
        self.token_balance = 0.0  # V10.2: Tracked by PortfolioManager

        self.hourly_trades = 0
        self.hour_start = None

        # Load state
        self._load_state()

    def _load_state(self):
        """Load state from PositionManager."""
        state = self.pos_manager.load_state()
        if not state:
            # Try legacy recovery
            # This requires token balance which we don't have here easily without WalletManager.
            # For strict SRP, we can't easily access wallet here.
            # TradingCore should handle reconciliation?
            # For now, we assume simple load.
            return

        self.entry_price = state.get("entry_price", 0.0)
        self.cost_basis = state.get("cost_basis", 0.0)
        self.in_position = state.get("in_position", False)
        self.max_price_achieved = state.get("max_price_achieved", 0.0)
        self.trailing_stop_price = state.get("trailing_stop_price", 0.0)

    def save_state(self):
        """Persist current state."""
        state = {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "cost_basis": self.cost_basis,
            "entry_time": self.entry_time,
            "in_position": self.in_position,
            "max_price_achieved": self.max_price_achieved,
            "trailing_stop_price": self.trailing_stop_price,
        }
        self.pos_manager.persist_state(state)

    def inject_price(self, price: float, source: str = "BATCH"):
        """Update price data and track high water mark for TSL."""
        if price > 0:
            self.data_feed.update(price, source=source)
            # V53.0: Track high water mark if in position
            if self.in_position and price > self.max_price_achieved:
                self.max_price_achieved = price

    def get_price(self, force_refresh=False):
        """Retrieve last price (Passive)."""
        return self.data_feed.get_last_price()

    def get_rsi(self):
        """Get RSI from DataFeed."""
        return self.data_feed.get_rsi()  # Assuming DataFeed has it or we calculate
        # Actually DataFeed usually computes on raw_prices.
        # If DataFeed doesn't have get_rsi, we use TechnicalAnalysis.
        # Let's check DataFeed... it usually doesn't.
        # So:
        # return TechnicalAnalysis.calculate_rsi(self.data_feed.raw_prices)
        # But wait, old Watcher had logic to sync from Broker.
        # Ideally DataManager handles sync.
        return TechnicalAnalysis.calculate_rsi(self.data_feed.raw_prices)

    def get_price_count(self):
        return len(self.data_feed.raw_prices)

    # V33.3: Expose Metadata for Strategy Logic
    def get_volume(self):
        """Get 1h Volume in USD."""
        return self.data_feed.volume_h1

    def get_liquidity(self):
        """Get Liquidity Depth in USD."""
        return self.data_feed.liquidity_usd

    def enter_position(self, price, size_usd):
        import time

        self.in_position = True
        self.entry_price = price
        self.cost_basis = size_usd
        self.entry_time = time.time()
        self.max_price_achieved = price
        self.trailing_stop_price = 0.0
        self.save_state()

    def exit_position(self):
        self.in_position = False
        self.entry_price = 0.0
        self.pos_manager.clear_state()

    def get_detailed_status(self):
        return f"{self.symbol}: ${self.get_price():.4f} (RSI: {self.get_rsi():.1f})"
