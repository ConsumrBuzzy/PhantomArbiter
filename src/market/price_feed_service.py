"""
PriceFeedService - The Pulse
============================
Layer A: Market Monitor - Real-time price ingestion.

Responsibilities:
- WebSocket connection management (Helius, native WSS)
- DEX feed aggregation (Jupiter, Raydium, Orca, Meteora)
- Price cache writes (SharedPriceCache)
- Observer pattern for price update broadcasts

Design:
- Implementation-agnostic: works with or without Rust WSS
- Uses SignalBus for broadcasting PRICE_UPDATE events
- Maintains priority cascade: WSS > Jupiter > DexScreener

Usage:
    from src.market import get_price_feed
    
    feed = get_price_feed()
    feed.start()
    price = feed.get_price("So111...112")
"""

import asyncio
import time
from typing import Dict, Optional, Callable, List, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class PriceSource(Enum):
    """Priority order for price sources."""
    WSS_RUST = 1      # Fastest: Rust aggregator
    WSS_PYTHON = 2    # Fast: Native Python WSS
    JUPITER_HTTP = 3  # Medium: Jupiter API
    DEXSCREENER = 4   # Fallback: DexScreener
    STALE = 99        # Cached but potentially stale


@dataclass
class PriceUpdate:
    """Immutable price update event."""
    mint: str
    price: float
    source: PriceSource
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0  # 0.0 - 1.0


@dataclass 
class FeedHealth:
    """Health status for a price feed."""
    name: str
    connected: bool = False
    last_update: float = 0.0
    updates_per_minute: int = 0
    errors_last_hour: int = 0


class PriceFeedService:
    """
    The Pulse - Central price ingestion service.
    
    Aggregates prices from multiple sources with priority cascade.
    Broadcasts updates via SignalBus using Observer pattern.
    """
    
    def __init__(self):
        # Price state
        self._prices: Dict[str, PriceUpdate] = {}
        self._subscriptions: Set[str] = set()
        
        # Feed adapters (lazy loaded)
        self._rust_wss = None
        self._python_wss = None
        self._jupiter_feed = None
        self._dex_feeds: Dict[str, object] = {}
        
        # Health tracking
        self._feed_health: Dict[str, FeedHealth] = {}
        self._running = False
        
        # Callbacks for Observer pattern
        self._observers: List[Callable[[PriceUpdate], None]] = []
        
        # Configuration
        self._stale_threshold_seconds = 30.0
        self._batch_interval_seconds = 1.0
        
        Logger.info("🏁 PriceFeedService initialized")
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def start(self) -> None:
        """Start all price feeds."""
        if self._running:
            return
        
        self._running = True
        Logger.info("📡 PriceFeedService starting...")
        
        # Initialize feeds in priority order
        self._init_rust_wss()
        self._init_python_wss()
        self._init_http_feeds()
        
        # Subscribe to internal events
        signal_bus.subscribe(SignalType.WATCH_TOKEN, self._on_watch_token)
        
        Logger.info("✅ PriceFeedService started")
    
    def stop(self) -> None:
        """Stop all price feeds gracefully."""
        if not self._running:
            return
        
        self._running = False
        Logger.info("🛑 PriceFeedService stopping...")
        
        # Disconnect feeds
        if self._rust_wss:
            try:
                self._rust_wss.stop()
            except Exception as e:
                Logger.error(f"Error stopping Rust WSS: {e}")
        
        if self._python_wss:
            try:
                self._python_wss.stop()
            except Exception as e:
                Logger.error(f"Error stopping Python WSS: {e}")
        
        Logger.info("✅ PriceFeedService stopped")
    
    # =========================================================================
    # FEED INITIALIZATION
    # =========================================================================
    
    def _init_rust_wss(self) -> None:
        """Initialize Rust WSS aggregator (Bridge Adapter pattern)."""
        try:
            from src.shared.infrastructure.rust_wss_listener import RustWssListener
            self._rust_wss = RustWssListener()
            self._rust_wss.on_price_update = self._handle_wss_update
            self._rust_wss.start()
            self._feed_health["rust_wss"] = FeedHealth(name="Rust WSS", connected=True)
            Logger.info("🦀 Rust WSS adapter connected")
        except ImportError:
            Logger.warning("⚠️ Rust WSS not available, using Python fallback")
            self._feed_health["rust_wss"] = FeedHealth(name="Rust WSS", connected=False)
        except Exception as e:
            Logger.error(f"❌ Rust WSS init failed: {e}")
            self._feed_health["rust_wss"] = FeedHealth(name="Rust WSS", connected=False)
    
    def _init_python_wss(self) -> None:
        """Initialize Python native WebSocket listener."""
        try:
            from src.core.websocket_listener import create_websocket_listener
            self._python_wss = create_websocket_listener()
            self._python_wss.on_price_update = self._handle_wss_update
            # Don't start if Rust WSS is working
            if not self._feed_health.get("rust_wss", FeedHealth("")).connected:
                self._python_wss.start()
                self._feed_health["python_wss"] = FeedHealth(name="Python WSS", connected=True)
                Logger.info("🐍 Python WSS connected (Rust fallback)")
            else:
                self._feed_health["python_wss"] = FeedHealth(name="Python WSS", connected=False)
        except Exception as e:
            Logger.error(f"❌ Python WSS init failed: {e}")
            self._feed_health["python_wss"] = FeedHealth(name="Python WSS", connected=False)
    
    def _init_http_feeds(self) -> None:
        """Initialize HTTP-based price feeds."""
        try:
            from src.shared.feeds.jupiter_feed import JupiterFeed
            self._jupiter_feed = JupiterFeed()
            self._feed_health["jupiter"] = FeedHealth(name="Jupiter API", connected=True)
            Logger.info("🪐 Jupiter HTTP feed initialized")
        except Exception as e:
            Logger.error(f"❌ Jupiter feed init failed: {e}")
        
        # Additional DEX feeds (lazy loaded on demand)
        self._dex_feeds = {}
    
    # =========================================================================
    # PRICE RETRIEVAL
    # =========================================================================
    
    def get_price(self, mint: str, max_age: float = None) -> Optional[float]:
        """
        Get the current price for a mint.
        
        Args:
            mint: Token mint address
            max_age: Maximum age in seconds (default: stale_threshold)
        
        Returns:
            Price in USD or None if unavailable/stale
        """
        max_age = max_age or self._stale_threshold_seconds
        
        update = self._prices.get(mint)
        if not update:
            return None
        
        age = time.time() - update.timestamp
        if age > max_age:
            return None
        
        return update.price
    
    def get_price_with_metadata(self, mint: str) -> Optional[PriceUpdate]:
        """Get full price update with source and timestamp."""
        return self._prices.get(mint)
    
    def get_all_prices(self, max_age: float = None) -> Dict[str, float]:
        """Get all non-stale prices."""
        max_age = max_age or self._stale_threshold_seconds
        now = time.time()
        return {
            mint: update.price
            for mint, update in self._prices.items()
            if (now - update.timestamp) <= max_age
        }
    
    # =========================================================================
    # SUBSCRIPTIONS
    # =========================================================================
    
    def subscribe(self, mint: str) -> None:
        """Subscribe to price updates for a mint."""
        if mint not in self._subscriptions:
            self._subscriptions.add(mint)
            Logger.debug(f"📌 Subscribed to {mint[:8]}...")
    
    def unsubscribe(self, mint: str) -> None:
        """Unsubscribe from price updates."""
        self._subscriptions.discard(mint)
    
    def add_observer(self, callback: Callable[[PriceUpdate], None]) -> None:
        """Add an observer for price updates (Observer pattern)."""
        self._observers.append(callback)
    
    def remove_observer(self, callback: Callable[[PriceUpdate], None]) -> None:
        """Remove a price update observer."""
        if callback in self._observers:
            self._observers.remove(callback)
    
    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================
    
    def _handle_wss_update(self, event: dict) -> None:
        """
        Handle WebSocket price update.
        Called by Rust or Python WSS adapter.
        """
        mint = event.get("mint")
        price = event.get("price")
        
        if not mint or not price or price <= 0:
            return
        
        source = PriceSource.WSS_RUST if self._rust_wss else PriceSource.WSS_PYTHON
        
        update = PriceUpdate(
            mint=mint,
            price=price,
            source=source,
            confidence=0.95,
        )
        
        self._apply_update(update)
    
    def _on_watch_token(self, signal: Signal) -> None:
        """Handle WATCH_TOKEN signal from SignalBus."""
        mint = signal.data.get("mint")
        if mint:
            self.subscribe(mint)
    
    def _apply_update(self, update: PriceUpdate) -> None:
        """
        Apply a price update with priority logic.
        Only updates if the new source has higher priority.
        """
        existing = self._prices.get(update.mint)
        
        # Update if: no existing, or newer source, or same source with newer timestamp
        should_update = (
            not existing or
            update.source.value < existing.source.value or
            (update.source == existing.source and update.timestamp > existing.timestamp)
        )
        
        if should_update:
            self._prices[update.mint] = update
            
            # Write to SharedPriceCache for cross-process sharing
            self._write_to_cache(update)
            
            # Notify observers (Observer pattern)
            self._notify_observers(update)
            
            # Broadcast via SignalBus
            signal_bus.publish(SignalType.PRICE_UPDATE, {
                "mint": update.mint,
                "price": update.price,
                "source": update.source.name,
            })
    
    def _write_to_cache(self, update: PriceUpdate) -> None:
        """Write price to SharedPriceCache for IPC."""
        try:
            from src.core.shared_cache import SharedPriceCache
            SharedPriceCache.write_price(
                symbol=update.mint,  # TODO: resolve to symbol
                price=update.price,
                source=update.source.name,
            )
        except Exception as e:
            Logger.error(f"Cache write failed: {e}")
    
    def _notify_observers(self, update: PriceUpdate) -> None:
        """Notify all registered observers of price update."""
        for callback in self._observers:
            try:
                callback(update)
            except Exception as e:
                Logger.error(f"Observer callback failed: {e}")
    
    # =========================================================================
    # HTTP BATCH FETCHING (Fallback)
    # =========================================================================
    
    async def fetch_batch_prices(self, mints: List[str]) -> Dict[str, float]:
        """
        Fetch prices for multiple mints via HTTP (Jupiter API).
        Used as fallback when WSS doesn't have data.
        """
        if not self._jupiter_feed:
            return {}
        
        try:
            prices = await self._jupiter_feed.get_prices(mints)
            
            # Apply updates
            for mint, price in prices.items():
                if price and price > 0:
                    update = PriceUpdate(
                        mint=mint,
                        price=price,
                        source=PriceSource.JUPITER_HTTP,
                        confidence=0.80,
                    )
                    self._apply_update(update)
            
            return prices
        except Exception as e:
            Logger.error(f"Batch price fetch failed: {e}")
            return {}
    
    # =========================================================================
    # HEALTH & DIAGNOSTICS
    # =========================================================================
    
    def get_health(self) -> Dict[str, FeedHealth]:
        """Get health status for all feeds."""
        return self._feed_health.copy()
    
    def get_stats(self) -> dict:
        """Get service statistics."""
        now = time.time()
        stale_count = sum(
            1 for u in self._prices.values()
            if (now - u.timestamp) > self._stale_threshold_seconds
        )
        
        return {
            "total_prices": len(self._prices),
            "stale_prices": stale_count,
            "subscriptions": len(self._subscriptions),
            "observers": len(self._observers),
            "feeds": {k: v.connected for k, v in self._feed_health.items()},
        }
