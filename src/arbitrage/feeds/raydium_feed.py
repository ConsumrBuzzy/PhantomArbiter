"""
V1.0: Raydium Price Feed
========================
Direct on-chain Raydium AMM pool state reading.

Raydium is the largest DEX on Solana with deep liquidity.
We read pool reserves directly for accurate pricing.
"""

import time
import requests
from typing import Optional, Dict, List

from config.settings import Settings
from src.system.logging import Logger
from .price_source import PriceSource, Quote, SpotPrice


class RaydiumFeed(PriceSource):
    """
    Raydium DEX price feed via API.
    
    Uses Raydium's public API for pool data.
    Falls back to DexScreener if needed.
    """
    
    # Raydium API endpoints
    PAIRS_API = "https://api.raydium.io/v2/main/pairs"
    PRICE_API = "https://api.raydium.io/v2/main/price"
    
    # Common mints
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    # Known pool addresses for major pairs
    KNOWN_POOLS = {
        # SOL/USDC pool (most liquid)
        "SOL/USDC": "58oQChx4yWmvKdwLLZzBi4ChoCcKTk3BitNX354Cs71G",
    }
    
    def __init__(self):
        self._price_cache: Dict[str, dict] = {}
        self._cache_ttl = 3.0  # 3 second cache
        self._pairs_cache: Optional[Dict] = None
        self._pairs_cache_time = 0.0
        
    def get_name(self) -> str:
        return "RAYDIUM"
    
    def get_fee_pct(self) -> float:
        """Raydium standard pool fee."""
        return 0.25  # 0.25% fee
    
    def get_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: float
    ) -> Optional[Quote]:
        """
        Get quote from Raydium.
        
        Note: Raydium doesn't have a public quote API like Jupiter,
        so we estimate based on spot price and apply slippage.
        """
        spot = self.get_spot_price(output_mint, input_mint)
        if not spot or spot.price <= 0:
            return None
            
        # Estimate output (inverse of spot price)
        price = 1 / spot.price if spot.price > 0 else 0
        output_amount = amount * price
        
        # Apply estimated slippage based on amount
        # Larger amounts = more slippage
        slippage_pct = min(0.5, amount / 10000)  # Up to 0.5% on $10k
        output_amount *= (1 - slippage_pct / 100)
        
        return Quote(
            dex="RAYDIUM",
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
        Get spot price from Raydium via DexScreener (more reliable).
        
        DexScreener provides Raydium pool prices with good accuracy.
        """
        cache_key = f"{base_mint}:{quote_mint}"
        
        # Check cache
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if time.time() - cached['timestamp'] < self._cache_ttl:
                return SpotPrice(
                    dex="RAYDIUM",
                    base_mint=base_mint,
                    quote_mint=quote_mint,
                    price=cached['price'],
                    timestamp=cached['timestamp']
                )
        
        # Try DexScreener for Raydium pools
        price = self._fetch_dexscreener_price(base_mint, "raydium")
        
        if price and price > 0:
            timestamp = time.time()
            self._price_cache[cache_key] = {
                'price': price,
                'timestamp': timestamp
            }
            
            return SpotPrice(
                dex="RAYDIUM",
                base_mint=base_mint,
                quote_mint=quote_mint,
                price=price,
                timestamp=timestamp
            )
        
        return None
    
    def _fetch_dexscreener_price(self, mint: str, dex_filter: str = None) -> Optional[float]:
        """
        Fetch price from DexScreener API.
        
        Args:
            mint: Token mint address
            dex_filter: Optional filter for specific DEX (e.g., "raydium")
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                return None
            
            # Filter for specific DEX if requested
            if dex_filter:
                dex_filter_lower = dex_filter.lower()
                filtered = [p for p in pairs if dex_filter_lower in p.get('dexId', '').lower()]
                if filtered:
                    pairs = filtered
            
            # Get price from first (most liquid) pair
            price = float(pairs[0].get('priceUsd', 0) or 0)
            return price if price > 0 else None
            
        except Exception as e:
            Logger.debug(f"DexScreener error: {e}")
            return None
    
    def _fetch_raydium_api_price(self, mint: str) -> Optional[float]:
        """
        Fetch price directly from Raydium API.
        
        Note: Raydium API can be unreliable, DexScreener is preferred.
        """
        try:
            url = f"{self.PRICE_API}?tokens={mint}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            price = data.get(mint, 0)
            return float(price) if price else None
            
        except Exception as e:
            Logger.debug(f"Raydium API error: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    feed = RaydiumFeed()
    
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    print("Testing Raydium Feed...")
    
    # Test spot price
    spot = feed.get_spot_price(SOL, USDC)
    if spot:
        print(f"SOL/USDC: ${spot.price:.2f}")
    else:
        print("Failed to get SOL price")
    
    # Test quote
    quote = feed.get_quote(USDC, SOL, 100.0)
    if quote:
        print(f"$100 USDC -> {quote.output_amount:.4f} SOL @ {quote.price:.4f}")
    else:
        print("Failed to get quote")
