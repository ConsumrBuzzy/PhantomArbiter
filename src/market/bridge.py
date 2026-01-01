"""
Market Bridge - Strangler Fig Transition Layer
===============================================
Provides backward-compatible interface for DataBroker to
gradually migrate to the new Market Monitor services.

Usage:
    from src.market.bridge import MarketBridge
    
    bridge = MarketBridge(use_new_services=True)
    prices = bridge.get_prices(mints)  # Delegates to PriceFeedService

Feature Flag:
    Settings.USE_MARKET_SERVICES (default: False)
    When True, routes calls to src/market/ services.
    When False, uses legacy DataBroker logic.
"""

import time
from typing import Dict, List, Optional

from src.shared.system.logging import Logger


class MarketBridge:
    """
    Strangler Fig bridge for gradual migration.
    
    Wraps old and new implementations, controlled by feature flag.
    Once migration is complete, this class becomes a thin passthrough.
    """
    
    def __init__(self, use_new_services: bool = None):
        """
        Initialize the bridge.
        
        Args:
            use_new_services: Override feature flag (for testing)
        """
        # Check feature flag
        if use_new_services is None:
            try:
                from config.settings import Settings
                use_new_services = getattr(Settings, "USE_MARKET_SERVICES", False)
            except:
                use_new_services = False
        
        self._use_new = use_new_services
        self._price_feed = None
        self._wallet_sync = None
        self._token_discovery = None
        self._market_data = None
        
        Logger.info(f"🌉 MarketBridge initialized (new_services={self._use_new})")
    
    # =========================================================================
    # SERVICE ACCESSORS (Lazy Loading)
    # =========================================================================
    
    @property
    def price_feed(self):
        """Get PriceFeedService (lazy)."""
        if self._price_feed is None and self._use_new:
            from src.market import get_price_feed
            self._price_feed = get_price_feed()
        return self._price_feed
    
    @property
    def wallet_sync(self):
        """Get WalletSyncService (lazy)."""
        if self._wallet_sync is None and self._use_new:
            from src.market import get_wallet_sync
            self._wallet_sync = get_wallet_sync()
        return self._wallet_sync
    
    @property
    def token_discovery(self):
        """Get TokenDiscoveryService (lazy)."""
        if self._token_discovery is None and self._use_new:
            from src.market import get_token_discovery
            self._token_discovery = get_token_discovery()
        return self._token_discovery
    
    @property
    def market_data(self):
        """Get MarketDataService (lazy)."""
        if self._market_data is None and self._use_new:
            from src.market import get_market_data
            self._market_data = get_market_data()
        return self._market_data
    
    # =========================================================================
    # PRICE OPERATIONS (Strangler Fig)
    # =========================================================================
    
    def get_prices(self, mints: List[str]) -> Dict[str, float]:
        """
        Get prices for a list of mints.
        
        Strangler: Routes to PriceFeedService when enabled.
        """
        if self._use_new and self.price_feed:
            # New path: Use PriceFeedService
            return self.price_feed.get_all_prices()
        else:
            # Legacy path: Use DSM directly
            from src.shared.system.data_source_manager import DataSourceManager
            dsm = DataSourceManager()
            return dsm.get_prices(mints) or {}
    
    def get_price(self, mint: str) -> Optional[float]:
        """Get single mint price."""
        if self._use_new and self.price_feed:
            return self.price_feed.get_price(mint)
        else:
            from src.core.shared_cache import SharedPriceCache
            price, _ = SharedPriceCache.get_price(mint)
            return price
    
    def start_price_feed(self) -> None:
        """Start the price feed service."""
        if self._use_new and self.price_feed:
            self.price_feed.start()
            Logger.info("🚀 PriceFeedService started via bridge")
    
    def stop_price_feed(self) -> None:
        """Stop the price feed service."""
        if self._use_new and self.price_feed:
            self.price_feed.stop()
    
    # =========================================================================
    # WALLET OPERATIONS (Strangler Fig)
    # =========================================================================
    
    def sync_wallet(self, force: bool = False) -> Dict:
        """
        Sync wallet state.
        
        Strangler: Routes to WalletSyncService when enabled.
        """
        if self._use_new and self.wallet_sync:
            state = self.wallet_sync.sync(force=force)
            if state:
                return {
                    "sol": state.sol_balance,
                    "usdc": state.usdc_balance,
                    "held_assets": state.held_assets,
                }
            return {}
        else:
            # Legacy path: Use SharedPriceCache
            from src.core.shared_cache import SharedPriceCache
            return SharedPriceCache.get_wallet_state()
    
    def invalidate_wallet(self) -> None:
        """Invalidate wallet cache after trade."""
        if self._use_new and self.wallet_sync:
            self.wallet_sync.invalidate()
        else:
            from src.core.shared_cache import SharedPriceCache
            SharedPriceCache.invalidate_wallet_state()
    
    # =========================================================================
    # TOKEN OPERATIONS (Strangler Fig)
    # =========================================================================
    
    def get_symbol(self, mint: str) -> str:
        """Get symbol for a mint."""
        if self._use_new and self.token_discovery:
            return self.token_discovery.get_symbol(mint)
        else:
            from src.shared.infrastructure.token_registry import get_registry
            return get_registry().get_symbol(mint)
    
    def validate_token(self, mint: str, symbol: str = None):
        """Validate token safety."""
        if self._use_new and self.token_discovery:
            return self.token_discovery.validate(mint, symbol)
        else:
            from src.core.validator import TokenValidator
            validator = TokenValidator()
            return validator.validate(mint, symbol or mint[:8])
    
    # =========================================================================
    # MARKET CONTEXT (Strangler Fig)
    # =========================================================================
    
    def get_regime(self) -> str:
        """Get current market regime."""
        if self._use_new and self.market_data:
            return self.market_data.get_regime().value
        else:
            from src.core.shared_cache import SharedPriceCache
            cached = SharedPriceCache.get_market_regime()
            return cached.get("regime", "UNKNOWN") if cached else "UNKNOWN"
    
    def get_ofi(self, mint: str) -> float:
        """Get Order Flow Imbalance."""
        if self._use_new and self.market_data:
            return self.market_data.get_ofi(mint)
        return 0.0
    
    def get_momentum(self, mint: str) -> float:
        """Get price momentum."""
        if self._use_new and self.market_data:
            return self.market_data.get_momentum(mint)
        return 0.0


# ============================================================================
# SINGLETON
# ============================================================================

_bridge: Optional[MarketBridge] = None


def get_market_bridge(use_new_services: bool = None) -> MarketBridge:
    """Get the MarketBridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = MarketBridge(use_new_services=use_new_services)
    return _bridge
