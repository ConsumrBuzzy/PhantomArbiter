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
from src.shared.system.logging import Logger
from .price_source import PriceSource, Quote, SpotPrice
from src.shared.execution.pool_index import get_pool_index


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
        self._bridge = None  # Lazy-loaded RaydiumBridge
        self.use_live_quotes = True  # Set False to save API credits
        
    def _get_bridge(self):
        """Lazy-load RaydiumBridge to avoid circular imports."""
        if self._bridge is None:
            from src.shared.execution.raydium_bridge import RaydiumBridge
            self._bridge = RaydiumBridge()
        return self._bridge
        
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
        Get quote from Raydium with dual-path strategy:
        1. Fast Path: Raydium Trade API (accurate, accounts for ticks/fees)
        2. Fallback: Spot price estimation (saves API credits)
        """
        # Path 1: Use Trade API for accurate quote
        if self.use_live_quotes:
            try:
                bridge = self._get_bridge()
                result = bridge.fetch_api_quote(input_mint, output_mint, amount)
                
                if result and result.get("success"):
                    output_amount = result.get("outputAmount", 0)
                    price_impact = result.get("priceImpactPct", 0)
                    
                    return Quote(
                        dex="RAYDIUM",
                        input_mint=input_mint,
                        output_mint=output_mint,
                        input_amount=amount,
                        output_amount=output_amount,
                        price=output_amount / amount if amount > 0 else 0,
                        slippage_estimate_pct=price_impact,
                        fee_pct=self.get_fee_pct(),
                        route=None,
                        timestamp=time.time()
                    )
            except Exception as e:
                Logger.debug(f"[RAYDIUM] Trade API quote failed: {e}")
        
        # Path 2: Fallback to spot price estimation
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
        Get spot price from Raydium via Daemon (fast) or DexScreener (fallback).
        """
        cache_key = f"{base_mint}:{quote_mint}"
        
        # Check cache (short TTL)
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

        # 1. Try Daemon (Fast Path)
        try:
            pool_index = get_pool_index()
            # Only checking CLMM pools for now (Daemon requirement)
            pools = pool_index.get_pools(base_mint, quote_mint)
            
            if pools and pools.raydium_clmm_pool:
                bridge = self._get_bridge()
                
                # Check if bridge is actually daemonized/ready? 
                # Just call get_price, it handles daemon communication.
                result = bridge.get_price(pools.raydium_clmm_pool)
                
                if result and result.success:
                    # Determine price direction
                    token_a = result.token_a
                    token_b = result.token_b
                    price_a_to_b = float(result.price_a_to_b)
                    price_b_to_a = float(result.price_b_to_a)
                    
                    price = 0.0
                    if base_mint == token_a:
                        price = price_a_to_b
                    elif base_mint == token_b:
                        price = price_b_to_a
                        
                    if price > 0:
                        Logger.debug(f"[RAYDIUM] 🟢 Daemon price for {base_mint[:4]}: ${price}")
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
        except Exception as e:
            Logger.debug(f"[RAYDIUM] Daemon check failed: {e}")
        
        # 2. Try DexScreener (Fallback)
        price = self._fetch_dexscreener_price(base_mint, "raydium")
        
        # 3. Try Raydium V2 API (Last Resort)
        if not price or price <= 0:
            price = self._fetch_raydium_api_price(base_mint)
            if price:
                Logger.info(f"   Using Raydium API fallback for {base_mint[:4]}...")

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

    def get_multiple_prices(self, mints: list, vs_token: str = None) -> dict:
        """
        Batch fetch prices via DexScreener (up to 30 tokens).
        V92.2: Added to prevent sequential scan bottlenecks.
        """
        if not mints:
            return {}
            
        try:
            ids = ",".join(mints[:30])
            url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return {}
                
            data = resp.json()
            pairs = data.get('pairs', [])
            results = {}
            
            for pair in pairs:
                # Filter for Raydium pairs
                if "raydium" not in pair.get('dexId', '').lower():
                    continue
                    
                base = pair.get('baseToken', {}).get('address')
                price = float(pair.get('priceUsd', 0) or 0)
                
                if base and price > 0 and base not in results:
                    results[base] = price
                    
                    # Update cache
                    key = f"{base}:{self.USDC_MINT}"
                    self._price_cache[key] = {
                        'price': price,
                        'timestamp': time.time()
                    }
            
            return results
            
        except Exception as e:
            Logger.debug(f"Raydium batch fetch error: {e}")
            return {}

    
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

    def get_multiple_prices(self, mints: list, vs_token: str = None) -> dict:
        """
        Batch fetch prices via DexScreener (up to 30 tokens).
        """
        if not mints:
            return {}
            
        try:
            # Chunking handled by caller or here? DexScreener supports 30.
            # SpreadDetector sends all mints (26 for trending). safe.
            ids = ",".join(mints[:30])
            url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return {}
                
            data = resp.json()
            pairs = data.get('pairs', [])
            results = {}
            
            for pair in pairs:
                # Filter for Raydium pairs
                if "raydium" not in pair.get('dexId', '').lower():
                    continue
                    
                base = pair.get('baseToken', {}).get('address')
                price = float(pair.get('priceUsd', 0) or 0)
                
                # Check if this pair is better (higher liquidity?)
                # For simplicity, if we already have a price, skip (first is usually best)
                if base and price > 0 and base not in results:
                    results[base] = price
                    
                    # Update cache
                    key = f"{base}:{self.USDC_MINT}"
                    self._price_cache[key] = {
                        'price': price,
                        'timestamp': time.time()
                    }
            
            return results
            
        except Exception as e:
            Logger.debug(f"Raydium batch fetch error: {e}")
            return {}


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
