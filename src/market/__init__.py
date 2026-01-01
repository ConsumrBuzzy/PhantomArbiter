"""
PhantomArbiter Market Monitor Layer
====================================
Layer A: Data Ingestion Services

Services:
- PriceFeedService: WSS + HTTP price streaming
- TokenDiscoveryService: Token metadata and validation
- MarketDataService: Regime detection, OFI, momentum
- WalletSyncService: Wallet balance synchronization

Usage:
    from src.market import get_price_feed, get_token_discovery
    
    price_feed = get_price_feed()
    price_feed.start()
    
    token_svc = get_token_discovery()
    metadata = token_svc.get_metadata(mint)
"""

from typing import Optional

# Service singletons
_price_feed_service: Optional["PriceFeedService"] = None
_token_discovery_service: Optional["TokenDiscoveryService"] = None
_market_data_service: Optional["MarketDataService"] = None
_wallet_sync_service: Optional["WalletSyncService"] = None


def get_price_feed() -> "PriceFeedService":
    """Get the PriceFeedService singleton."""
    global _price_feed_service
    if _price_feed_service is None:
        from src.market.price_feed_service import PriceFeedService
        _price_feed_service = PriceFeedService()
    return _price_feed_service


def get_token_discovery() -> "TokenDiscoveryService":
    """Get the TokenDiscoveryService singleton."""
    global _token_discovery_service
    if _token_discovery_service is None:
        from src.market.token_discovery_service import TokenDiscoveryService
        _token_discovery_service = TokenDiscoveryService()
    return _token_discovery_service


def get_market_data() -> "MarketDataService":
    """Get the MarketDataService singleton."""
    global _market_data_service
    if _market_data_service is None:
        from src.market.market_data_service import MarketDataService
        _market_data_service = MarketDataService()
    return _market_data_service


def get_wallet_sync() -> "WalletSyncService":
    """Get the WalletSyncService singleton."""
    global _wallet_sync_service
    if _wallet_sync_service is None:
        from src.market.wallet_sync_service import WalletSyncService
        _wallet_sync_service = WalletSyncService()
    return _wallet_sync_service


# Convenience imports (lazy)
__all__ = [
    "get_price_feed",
    "get_token_discovery", 
    "get_market_data",
    "get_wallet_sync",
    "get_market_bridge",
    "get_signal_scout",
    "get_signal_hub",
]


def get_market_bridge(use_new_services: bool = None) -> "MarketBridge":
    """Get the MarketBridge singleton (Strangler Fig)."""
    from src.market.bridge import get_market_bridge as _get_bridge
    return _get_bridge(use_new_services)


def get_signal_scout() -> "SignalScoutService":
    """Get the SignalScoutService singleton (Asymmetric Intel)."""
    from src.market.signal_scout_service import get_signal_scout as _get_scout
    return _get_scout()


def get_signal_hub() -> "MarketSignalHub":
    """Get the MarketSignalHub singleton (Signal Aggregator)."""
    from src.market.signal_hub import get_signal_hub as _get_hub
    return _get_hub()
