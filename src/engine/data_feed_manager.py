"""
V10.2 DataFeed Manager
======================
Centralized price fetching component for TradingCore (P1).
Responsibility:
1. Batch fetch prices from SmartRouter/Jupiter.
2. Inject prices into Watchers.
3. specific P1 maintenance tasks related to data.
"""

from src.core.data import batch_fetch_jupiter_prices
from src.shared.system.priority_queue import priority_queue
from src.strategy.watcher import Watcher

class DataFeedManager:
    """
    Manages data Ingestion for the TradingCore.
    Decouples 'How to get data' from the Core Loop.
    """
    
    def __init__(self):
        pass
        
    def update_prices(self, watchers: dict[str, Watcher], scout_watchers: dict[str, Watcher]) -> dict:
        """
        Batch fetch prices for all watchers and inject them.
        Returns: Map of {mint: price}
        """
        # 1. Collect Mints
        active_mints = [w.mint for w in watchers.values()]
        scout_mints = [w.mint for w in scout_watchers.values()]
        all_mints = active_mints + scout_mints
        
        if not all_mints:
            return {}
            
        # 2. Strategy: Broker (Preferred) vs Batch Fetch (Fallback)
        from src.core.shared_cache import SharedPriceCache, is_broker_alive
        
        price_map = {}
        
        if is_broker_alive():
            # V10.8: Read from Broker Cache (High Performance)
            # We fetching ALL prices from cache to cover our mint list
            cached_data = SharedPriceCache.get_all_prices(max_age=30)
            
            # Map symbol back to mint for injection logic?
            # Cache keys are SYMBOLS (e.g. "SOL"). Watchers know their mints.
            # We need to map symbol -> price.
            # But wait, batch_fetch_jupiter_prices returns {mint: price}.
            # Watcher inject uses price. The keying in step 3 maps mints.
            
            # Let's see Combined Watchers loop (Step 3).
            # It iterates watchers, checks if watcher.mint is in price_map.
            # So price_map MUST be {mint: price}.
            
            # Broker Cache returns {symbol: {price, ...}}
            # We need to convert it.
            
            # Get Mint Map from Settings (or AssetManager)
            # Actually watchers have symbol property.
            
            # Optimization: Just build price_map from cache for requested mints
            for watcher in {**watchers, **scout_watchers}.values():
                sym = watcher.symbol
                if sym in cached_data:
                     price_map[watcher.mint] = cached_data[sym]['price']
                     
        else:
            # Fallback: Direct Network Call (Blocking I/O - P1)
            # SmartRouter handles the network call
            price_map = batch_fetch_jupiter_prices(all_mints)
        
        # 3. Inject into Watchers
        combined_watchers = {**watchers, **scout_watchers}
        for symbol, watcher in combined_watchers.items():
            if watcher.mint in price_map:
                price = price_map[watcher.mint]
                watcher.inject_price(price, source="BATCH")
                
        return price_map
