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
    
    @property
    def is_profitable(self) -> bool:
        """Is this opportunity profitable after fees?"""
        min_profit = getattr(Settings, 'MIN_PROFIT_AFTER_FEES', 0.10)
        return self.net_profit_usd >= min_profit
    
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
        
        # === ADAPTIVE FEE MODEL ===
        # Get live SOL price for gas calculation
        sol_price_usd = self._get_sol_price()
        
        # Per-DEX trading fees (actual fees vary by DEX)
        DEX_FEES = {
            "JUPITER": 0.0035,    # ~0.35% (includes route optimization)
            "RAYDIUM": 0.0025,    # 0.25%
            "ORCA": 0.0025,       # 0.25%
            "PUMPFUN": 0.01,      # 1% (bonding curve)
            "METEORA": 0.003,     # 0.3%
        }
        buy_fee_pct = DEX_FEES.get(buy_dex.upper(), 0.003)
        sell_fee_pct = DEX_FEES.get(sell_dex.upper(), 0.003)
        trading_fees = trade_size * (buy_fee_pct + sell_fee_pct)
        
        # Gas: ~5000 lamports per tx, ~2 txs = 0.00001 SOL base + priority
        # Priority varies 0.0001-0.001 SOL depending on congestion
        base_gas_sol = 0.0001
        priority_fee_sol = getattr(Settings, 'PRIORITY_FEE_SOL', 0.0005)
        gas_usd = (base_gas_sol + priority_fee_sol) * sol_price_usd * 2  # x2 for round trip
        
        # Dynamic slippage: scales with trade size vs liquidity
        # Base 0.1% + impact proportional to size
        slippage_base_pct = getattr(Settings, 'SLIPPAGE_BASE_PCT', 0.001)  # 0.1%
        slippage_impact = 0.001 * (trade_size / max(trade_size * 10, 10000))  # ~0.01-0.1%
        slippage_pct = slippage_base_pct + slippage_impact
        slippage_cost = trade_size * slippage_pct
        
        # Safety buffer: quote staleness, rent, rounding (scales with trade size)
        safety_buffer = max(0.02, trade_size * 0.0005)  # min $0.02 or 0.05% of trade
        
        total_fees = trading_fees + gas_usd + slippage_cost + safety_buffer
        
        net_profit = gross_profit - total_fees
        
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
            estimated_fees_usd=total_fees,
            net_profit_usd=net_profit,
            max_size_usd=trade_size,
            confidence=0.9,
            timestamp=time.time()
        )
    
    def scan_all_pairs(self, pairs: List[Tuple[str, str, str]]) -> List[SpreadOpportunity]:
        """
        Scan multiple pairs for opportunities.
        
        Args:
            pairs: List of (pair_name, base_mint, quote_mint) tuples
            
        Returns:
            List of SpreadOpportunity sorted by spread_pct descending
        """
        opportunities = []
        
        for pair_name, base_mint, quote_mint in pairs:
            opp = self.scan_pair(base_mint, quote_mint, pair_name)
            if opp:
                opportunities.append(opp)
                
        return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)
    
    def get_price_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current price cache as a matrix.
        
        Returns:
            {pair: {dex: price, ...}, ...}
        """
        return self._price_cache.copy()
