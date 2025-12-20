"""
V1.0: Spread Detector
=====================
Monitors price differences across DEXs to detect arbitrage opportunities.
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from config.settings import Settings


@dataclass
class SpreadOpportunity:
    """
    Represents an arbitrage opportunity between two DEXs.
    
    A "spread" is the price difference between the best place to buy
    and the best place to sell the same asset.
    """
    pair: str                   # e.g., "SOL/USDC"
    base_mint: str              # Token being traded
    quote_mint: str             # Quote currency (usually USDC)
    
    buy_dex: str                # DEX with lowest price (buy here)
    sell_dex: str               # DEX with highest price (sell here)
    buy_price: float            # Price on buy DEX
    sell_price: float           # Price on sell DEX
    
    spread_pct: float           # (sell - buy) / buy * 100
    gross_profit_usd: float     # Profit before fees
    estimated_fees_usd: float   # Trading + gas fees
    net_profit_usd: float       # Profit after all costs
    
    max_size_usd: float         # Limited by liquidity depth
    confidence: float           # 0-1, based on price freshness
    
    timestamp: float = field(default_factory=time.time)
    
    # Dashboard/Verification fields (added for compatibility)
    verification_status: Optional[str] = None
    
    # Dashboard/Verification fields (added for compatibility)
    verification_status: Optional[str] = None
    
    @property
    def is_profitable(self) -> bool:
        """Is this opportunity profitable after fees?"""
        # For simulation: trigger on any net gain > 0
        # For live: use MIN_PROFIT_AFTER_FEES threshold
        return self.net_profit_usd > 0
    
    @property
    def status(self) -> str:
        """Status indicator for dashboard."""
        if self.is_profitable and self.spread_pct >= 0.3:
            return "READY"
        elif self.spread_pct >= 0.1:
            return "MONITOR"
        else:
            return "LOW"


class SpreadDetector:
    """
    Detects price spreads across multiple DEXs.
    
    This is the core of spatial arbitrage - finding where
    to buy low and sell high across different venues.
    """
    
    def __init__(self, feeds: List = None):
        from src.shared.feeds import PriceSource
        self.feeds: Dict[str, 'PriceSource'] = {}
        
        if feeds:
            for feed in feeds:
                self.feeds[feed.get_name()] = feed
                
        # Configuration
        self.min_spread_pct = getattr(Settings, 'MIN_SPREAD_PCT', 0.1)
        self.default_trade_size = getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 100.0)
        
        # SOL price cache for gas calculation
        self._sol_price_cache = 95.0  # Default fallback
        self._sol_price_ts = 0.0
        
        # Cache
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._last_scan = 0.0
        
    def add_feed(self, feed) -> None:
        """Add a price feed source."""
        self.feeds[feed.get_name()] = feed
        
    def _get_sol_price(self) -> float:
        """Get live SOL/USD price for gas cost estimation."""
        import time
        
        # Cache for 30 seconds to avoid excessive API calls
        if time.time() - self._sol_price_ts < 30:
            return self._sol_price_cache
        
        SOL_MINT = "So11111111111111111111111111111111111111112"
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        for feed in self.feeds.values():
            try:
                spot = feed.get_spot_price(SOL_MINT, USDC_MINT)
                if spot and spot.price > 0:
                    self._sol_price_cache = spot.price
                    self._sol_price_ts = time.time()
                    return spot.price
            except:
                pass
        
        return self._sol_price_cache  # Return cached/default
        
    def scan_pair(
        self, 
        base_mint: str, 
        quote_mint: str,
        pair_name: str = None,
        trade_size: float = None
    ) -> Optional[SpreadOpportunity]:
        """
        Scan all DEXs for spread opportunity on a single pair.
        
        Args:
            base_mint: Token to trade
            quote_mint: Quote currency
            pair_name: Optional human-readable name (e.g., "SOL/USDC")
            trade_size: USD value to test (affects slippage)
            
        Returns:
            SpreadOpportunity if a spread exists, else None
        """
        if not self.feeds:
            return None
            
        trade_size = trade_size or self.default_trade_size
        pair_name = pair_name or f"{base_mint[:8]}/{quote_mint[:8]}"
        
        # Fetch prices from all feeds
        prices: Dict[str, float] = {}
        
        for name, feed in self.feeds.items():
            try:
                spot = feed.get_spot_price(base_mint, quote_mint)
                if spot and spot.price > 0:
                    prices[name] = spot.price
            except Exception as e:
                pass  # Skip failed feeds
                
        if len(prices) < 2:
            return None  # Need at least 2 DEXs to compare
            
        # Find best buy and sell
        sorted_prices = sorted(prices.items(), key=lambda x: x[1])
        buy_dex, buy_price = sorted_prices[0]      # Lowest price
        sell_dex, sell_price = sorted_prices[-1]   # Highest price
        
        # Calculate spread
        spread_pct = ((sell_price - buy_price) / buy_price) * 100
        
        if spread_pct < 0.01:  # Negligible spread
            return None
            
        # Estimate profitability with ADAPTIVE fees
        gross_profit = trade_size * (spread_pct / 100)
        
        # Use centralized FeeEstimator for adaptive fees
        from src.arbiter.core.fee_estimator import get_fee_estimator
        fee_est = get_fee_estimator()
        
        # Update estimator's SOL price cache
        fee_est._sol_price_cache = self._get_sol_price()
        fee_est._sol_price_ts = time.time()
        
        fees = fee_est.estimate(
            trade_size_usd=trade_size,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            sol_price=fee_est._sol_price_cache
        )
        
        # ML Slippage Prediction: adjust for expected slippage based on historical data
        expected_slippage_pct = 0.0
        try:
            from src.shared.system.db_manager import db_manager
            # Get token symbol from pair name (e.g., "SOL/USDC" -> "SOL")
            token = pair_name.split('/')[0] if '/' in pair_name else pair_name
            expected_slippage_pct = db_manager.get_expected_slippage(token, trade_size)
        except Exception:
            pass  # No data = assume no extra slippage
        
        slippage_cost = trade_size * (expected_slippage_pct / 100)
        
        # ML Decay Prediction: adjust for expected spread decay during execution
        # Uses learned cycle time (or default 3s) as execution window
        decay_cost = 0.0
        try:
            from src.shared.system.db_manager import db_manager
            decay_velocity = db_manager.get_decay_velocity(pair_name)  # %/sec
            if decay_velocity > 0:
                # Use learned cycle time (ms -> sec), fallback to 3s
                exec_window = db_manager.get_avg_cycle_time() / 1000 if db_manager.get_avg_cycle_time() > 0 else 3.0
                exec_window = min(exec_window, 10.0)  # Cap at 10s
                
                # Dampen penalty for established tokens (trust them more)
                token_base = pair_name.split('/')[0] if '/' in pair_name else pair_name
                ESTABLISHED = {'SOL', 'USDC', 'USDT', 'BONK', 'RAY', 'JUP', 'ORCA', 'WIF', 'JTO', 'PYTH'}
                decay_multiplier = 0.3 if token_base in ESTABLISHED else 1.0
                
                expected_decay = decay_velocity * exec_window * decay_multiplier
                decay_cost = trade_size * (expected_decay / 100)
        except Exception:
            pass
        
        net_profit = gross_profit - fees.total_usd - slippage_cost - decay_cost
        
        return SpreadOpportunity(
            pair=pair_name,
            base_mint=base_mint,
            quote_mint=quote_mint,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=spread_pct,
            gross_profit_usd=gross_profit,
            estimated_fees_usd=fees.total_usd,
            net_profit_usd=net_profit,
            max_size_usd=trade_size,
            confidence=0.9,
            timestamp=time.time()
        )
    
    def scan_all_pairs(self, pairs: List[Tuple[str, str, str]], trade_size: float = None) -> List[SpreadOpportunity]:
        """
        Scan multiple pairs for opportunities using SHARED batch price fetch.
        
        Uses src/core/data.batch_fetch_jupiter_prices which has:
        - Circuit breaker for Jupiter API
        - DexScreener fallback
        - Chunking for large batches
        
        Args:
            pairs: List of (pair_name, base_mint, quote_mint) tuples
            trade_size: USD value to test (affects slippage/fees)
            
        Returns:
            List of SpreadOpportunity sorted by spread_pct descending
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        trade_size = trade_size or self.default_trade_size
        opportunities = []
        
        # Collect unique mints
        all_mints = list(set(
            base_mint for pair_name, base_mint, quote_mint in pairs
        ))
        
        if not all_mints or not self.feeds:
            return []
        
        # Parallel fetch from ALL feeds
        feed_prices: Dict[str, Dict[str, float]] = {}
        
        def fetch_from_feed(feed_item):
            feed_name, feed = feed_item
            try:
                if hasattr(feed, 'get_multiple_prices'):
                    return feed_name, feed.get_multiple_prices(all_mints)
                else:
                    # Fallback: parallel individual fetches
                    prices = {}
                    for mint in all_mints:
                        try:
                            spot = feed.get_spot_price(mint, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
                            if spot and spot.price > 0:
                                prices[mint] = spot.price
                        except:
                            pass
                    return feed_name, prices
            except Exception:
                return feed_name, {}
        
        # Fetch from all feeds in parallel (3 feeds = 3 threads)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_from_feed, item) for item in self.feeds.items()]
            
            for future in as_completed(futures, timeout=10):
                try:
                    feed_name, prices = future.result()
                    if prices:
                        feed_prices[feed_name] = prices
                except Exception as e:
                    import traceback
                    print(f"DEBUG: Feed {future} failed: {e}")
                    # traceback.print_exc()
                    pass
        
        if len(feed_prices) < 2:
            # Need at least 2 feeds for spread comparison
            # Fall back to sequential scan
            # DEBUG: Why sequential?
            # print(f"DEBUG: Falling back to sequential (Feeds: {len(feed_prices)} - {list(feed_prices.keys())})")
            
            opps_seq = []
            for pair_name, base_mint, quote_mint in pairs:
                opp = self.scan_pair(base_mint, quote_mint, pair_name, trade_size=trade_size)
                if opp:
                    opps_seq.append(opp)
            return sorted(opps_seq, key=lambda x: x.spread_pct, reverse=True)
        
        # Calculate spreads for each pair
        # print(f"DEBUG: Parallel Scan: {len(pairs)} pairs | Feeds: {list(feed_prices.keys())}") # CONFIRM FEEDS
        
        from src.arbiter.core.fee_estimator import get_fee_estimator
        fee_est = get_fee_estimator()
        fee_est._sol_price_cache = self._get_sol_price()
        fee_est._sol_price_ts = time.time()
        
        for pair_name, base_mint, quote_mint in pairs:
            # Gather prices from all feeds for this token
            prices: Dict[str, float] = {}
            for feed_name, feed_data in feed_prices.items():
                if base_mint in feed_data:
                    prices[feed_name] = feed_data[base_mint]
            
            # Update PoolRegistry (Smart Pool Tracking)
            try:
                from src.shared.execution.pool_registry import get_pool_registry
                registry = get_pool_registry()
                registry.update_coverage(
                    symbol=pair_name.split('/')[0],
                    mint=base_mint,
                    has_raydium=("RAYDIUM" in prices),
                    has_orca=("ORCA" in prices),
                    has_meteora=("METEORA" in prices)
                )
            except ImportError:
                pass
            
            if len(prices) < 2:
                continue
            
            # Find best buy and sell
            sorted_prices = sorted(prices.items(), key=lambda x: x[1])
            buy_dex, buy_price = sorted_prices[0]
            sell_dex, sell_price = sorted_prices[-1]
            
            spread_pct = ((sell_price - buy_price) / buy_price) * 100
            
            # Allow ALL spreads (even negative) to show up in dashboard (proof of life)
            # if spread_pct < -2.0: 
            #     continue
            
            # Show even tiny spreads so dashboard isn't blank
            # if spread_pct < 0.01:
            #     continue
            
            gross_profit = trade_size * (spread_pct / 100)
            fees = fee_est.estimate(
                trade_size_usd=trade_size,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                sol_price=fee_est._sol_price_cache
            )
            
            # ML Slippage Prediction
            slippage_cost = 0.0
            try:
                from src.shared.system.db_manager import db_manager
                token = pair_name.split('/')[0] if '/' in pair_name else pair_name
                expected_slippage_pct = db_manager.get_expected_slippage(token, trade_size)
                slippage_cost = trade_size * (expected_slippage_pct / 100)
            except:
                pass
            
            # ML Decay Prediction
            decay_cost = 0.0
            try:
                decay_velocity = db_manager.get_decay_velocity(pair_name)
                if decay_velocity > 0:
                    exec_window = db_manager.get_avg_cycle_time() / 1000 if db_manager.get_avg_cycle_time() > 0 else 3.0
                    exec_window = min(exec_window, 10.0)
                    
                    # Dampen penalty for established tokens (trust them more)
                    token_base = pair_name.split('/')[0] if '/' in pair_name else pair_name
                    ESTABLISHED = {'SOL', 'USDC', 'USDT', 'BONK', 'RAY', 'JUP', 'ORCA', 'WIF', 'JTO', 'PYTH'}
                    decay_multiplier = 0.3 if token_base in ESTABLISHED else 1.0
                    
                    decay_cost = trade_size * (decay_velocity * exec_window / 100) * decay_multiplier
            except:
                pass
            
            net_profit = gross_profit - fees.total_usd - slippage_cost - decay_cost
            
            opportunities.append(SpreadOpportunity(
                pair=pair_name,
                base_mint=base_mint,
                quote_mint=quote_mint,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=buy_price,
                sell_price=sell_price,
                spread_pct=spread_pct,
                gross_profit_usd=gross_profit,
                estimated_fees_usd=fees.total_usd,
                net_profit_usd=net_profit,
                max_size_usd=trade_size,
                confidence=0.9,
                timestamp=time.time()
            ))
        
        return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)
    
    def get_price_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current price cache as a matrix.
        
        Returns:
            {pair: {dex: price, ...}, ...}
        """
        return self._price_cache.copy()
