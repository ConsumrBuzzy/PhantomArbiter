"""
V1.0: Orca Price Feed
=====================
Orca Whirlpools (CLMM) price feed.

Orca is the second largest DEX on Solana with concentrated liquidity.
We leverage the existing OrcaAdapter for pool state reading.
"""

import time
from typing import Optional, Dict

from config.settings import Settings
from src.system.logging import Logger
from .price_source import PriceSource, Quote, SpotPrice


class OrcaFeed(PriceSource):
    """
    Orca Whirlpools price feed.
    
    Uses DexScreener for price data (reliable and fast).
    Can optionally use the full OrcaAdapter for on-chain reads.
    """
    
    # Common mints
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    def __init__(self, use_on_chain: bool = False):
        """
        Initialize Orca feed.
        
        Args:
            use_on_chain: If True, use OrcaAdapter for on-chain reads.
                         If False, use DexScreener API (faster).
        """
        self.use_on_chain = use_on_chain
        self._price_cache: Dict[str, dict] = {}
        self._cache_ttl = 3.0  # 3 second cache
        
        # Lazy-load on-chain adapter
        self._orca_adapter = None
        
    def _get_orca_adapter(self):
        """Lazy-load the Orca adapter."""
        if self._orca_adapter is None and self.use_on_chain:
            try:
                from src.liquidity.orca_adapter import OrcaAdapter
                self._orca_adapter = OrcaAdapter()
            except Exception as e:
                Logger.debug(f"Failed to load OrcaAdapter: {e}")
        return self._orca_adapter
        
    def get_name(self) -> str:
        return "ORCA"
    
    def get_fee_pct(self) -> float:
        """Orca typical fee tier."""
        return 0.30  # 0.30% for standard pools
    
    def get_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: float
    ) -> Optional[Quote]:
        """
        Get quote from Orca.
        
        Uses spot price with slippage estimation.
        """
        spot = self.get_spot_price(output_mint, input_mint)
        if not spot or spot.price <= 0:
            return None
            
        # Estimate output
        price = 1 / spot.price if spot.price > 0 else 0
        output_amount = amount * price
        
        # Orca CLMM typically has lower slippage for concentrated ranges
        slippage_pct = min(0.3, amount / 15000)  # Up to 0.3% on $15k
        output_amount *= (1 - slippage_pct / 100)
        
        return Quote(
            dex="ORCA",
            input_mint=input_mint,
            output_mint=output_mint,
            input_amount=amount,
            output_amount=output_amount,
            price=output_amount / amount if amount > 0 else 0,
            slippage_estimate_pct=slippage_pct,
            fee_pct=self.get_fee_pct(),
            route=None,
            timestamp=time.time()
        )
    
    def get_spot_price(self, base_mint: str, quote_mint: str) -> Optional[SpotPrice]:
        """
        Get spot price from Orca.
        
        Uses DexScreener filtered for Orca pools.
        """
        cache_key = f"{base_mint}:{quote_mint}"
        
        # Check cache
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if time.time() - cached['timestamp'] < self._cache_ttl:
                return SpotPrice(
                    dex="ORCA",
                    base_mint=base_mint,
                    quote_mint=quote_mint,
                    price=cached['price'],
                    timestamp=cached['timestamp']
                )
        
        # Try on-chain first if enabled
        price = None
        if self.use_on_chain:
            price = self._fetch_on_chain_price(base_mint, quote_mint)
        
        # Fallback to DexScreener
        if not price:
            price = self._fetch_dexscreener_price(base_mint, "orca")
        
        if price and price > 0:
            timestamp = time.time()
            self._price_cache[cache_key] = {
                'price': price,
                'timestamp': timestamp
            }
            
            return SpotPrice(
                dex="ORCA",
                base_mint=base_mint,
                quote_mint=quote_mint,
                price=price,
                timestamp=timestamp
            )
        
        return None
    
    def _fetch_on_chain_price(self, base_mint: str, quote_mint: str) -> Optional[float]:
        """Fetch price from on-chain Whirlpool state."""
        adapter = self._get_orca_adapter()
        if not adapter:
            return None
            
        try:
            pool = adapter.find_whirlpool(base_mint, quote_mint)
            if pool:
                return pool.price
        except Exception as e:
            Logger.debug(f"Orca on-chain error: {e}")
        
        return None
    
    def _fetch_dexscreener_price(self, mint: str, dex_filter: str = None) -> Optional[float]:
        """
        Fetch price from DexScreener API.
        
        Args:
            mint: Token mint address
            dex_filter: Filter for specific DEX
        """
        import requests
        
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                return None
            
            # Filter for Orca
            if dex_filter:
                dex_filter_lower = dex_filter.lower()
                filtered = [p for p in pairs if dex_filter_lower in p.get('dexId', '').lower()]
                if filtered:
                    pairs = filtered
                else:
                    return None  # No Orca pools found
            
            price = float(pairs[0].get('priceUsd', 0) or 0)
            return price if price > 0 else None
            
        except Exception as e:
            Logger.debug(f"DexScreener error: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    feed = OrcaFeed(use_on_chain=False)
    
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    print("Testing Orca Feed...")
    
    # Test spot price
    spot = feed.get_spot_price(SOL, USDC)
    if spot:
        print(f"SOL/USDC: ${spot.price:.2f}")
    else:
        print("Failed to get SOL price (may not have Orca pool)")
    
    # Test quote
    quote = feed.get_quote(USDC, SOL, 100.0)
    if quote:
        print(f"$100 USDC -> {quote.output_amount:.4f} SOL @ {quote.price:.4f}")
    else:
        print("Failed to get quote")
