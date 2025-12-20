"""
V1.0: Meteora Price Feed
========================
Meteora DLMM (Dynamic Liquidity Market Maker) price feed.

Meteora provides deep liquidity for major Solana pairs with
dynamic fees based on volatility.

Uses DexScreener API filtered for Meteora pools.
"""

import time
import requests
from typing import Optional, Dict

from config.settings import Settings
from src.shared.system.logging import Logger
from .price_source import PriceSource, Quote, SpotPrice
from src.shared.execution.pool_index import get_pool_index


class MeteoraFeed(PriceSource):
    """
    Meteora DLMM price feed.
    
    Uses DexScreener for price data filtered to Meteora pools.
    Meteora offers dynamic fees and concentrated liquidity.
    """
    
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
    
    # Typical Meteora DLMM fee range (dynamic based on volatility)
    BASE_FEE_PCT = 0.25
    
    def __init__(self):
        """Initialize Meteora feed."""
        self._price_cache: Dict[str, tuple] = {}  # mint -> (price, timestamp)
        self._cache_ttl = 5.0  # 5 second cache
        self._bridge = None

    def _get_bridge(self):
        """Lazy-load MeteoraBridge."""
        if self._bridge is None:
            from src.shared.execution.meteora_bridge import MeteoraBridge
            self._bridge = MeteoraBridge()
        return self._bridge
    
    def get_name(self) -> str:
        return "METEORA"
    
    def get_fee_pct(self) -> float:
        """Meteora dynamic fee (base estimate)."""
        return self.BASE_FEE_PCT
    
    def get_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: float
    ) -> Optional[Quote]:
        """
        Get quote from Meteora.
        
        Uses spot price with slippage estimation.
        """
        spot = self.get_spot_price(output_mint, input_mint)
        if not spot or spot.price <= 0:
            return None
        
        # For buying output_mint with input_mint
        # price = input per output
        output_amount = amount / spot.price if spot.price > 0 else 0
        
        # Apply estimated slippage (0.1% for liquid pairs)
        slippage_pct = 0.1
        output_after_slippage = output_amount * (1 - slippage_pct / 100)
        
        return Quote(
            input_mint=input_mint,
            output_mint=output_mint,
            input_amount=amount,
            output_amount=output_after_slippage,
            price=spot.price,
            fee_pct=self.BASE_FEE_PCT,
            route=f"METEORA: {input_mint[:8]}→{output_mint[:8]}",
            liquidity_usd=spot.liquidity_usd,
            timestamp=time.time()
        )
    
    def get_spot_price(self, base_mint: str, quote_mint: str) -> Optional[SpotPrice]:
        """
        Get spot price from Meteora via DexScreener.
        
        Uses DexScreener filtered for Meteora pools.
        """
        try:
            # Check cache
            cache_key = f"{base_mint}_{quote_mint}"
            if cache_key in self._price_cache:
                cached_price, cached_time = self._price_cache[cache_key]
                if time.time() - cached_time < self._cache_ttl:
                    return SpotPrice(
                        base_mint=base_mint,
                        quote_mint=quote_mint,
                        price=cached_price,
                        source="METEORA",
                        timestamp=cached_time
                    )
            
            # 1. Try Daemon (Fast Path)
            try:
                pool_index = get_pool_index()
                pools = pool_index.get_pools(base_mint, quote_mint)
                
                if pools and pools.meteora_pool:
                    bridge = self._get_bridge()
                    result = bridge.get_price(pools.meteora_pool)
                    
                    if result and result.success:
                        token_x = result.token_x
                        token_y = result.token_y
                        
                        price = 0.0
                        if base_mint == token_x:
                            price = result.price_x_to_y
                        elif base_mint == token_y:
                            price = result.price_y_to_x
                            
                        if price > 0:
                            Logger.debug(f"[METEORA] 🟢 Daemon price for {base_mint[:4]}: ${price}")
                            self._price_cache[cache_key] = (price, time.time())
                            return SpotPrice(
                                dex="METEORA",
                                base_mint=base_mint,
                                quote_mint=quote_mint,
                                price=price,
                                source="METEORA",
                                liquidity_usd=0, # Not provided by fast check
                                timestamp=time.time()
                            )
                    else:
                        Logger.debug(f"[METEORA] Daemon price failed: {result.error if result else 'No result'}")
            except Exception as e:
                Logger.debug(f"[METEORA] Daemon check failed: {e}")
            
            # 2. Fetch from DexScreener (Fallback)
            result = self._fetch_dexscreener_price(base_mint, dex_filter="meteora")
            
            if result:
                price, liquidity = result
                
                # Cache it
                self._price_cache[cache_key] = (price, time.time())
                
                return SpotPrice(
                    dex="METEORA",
                    base_mint=base_mint,
                    quote_mint=quote_mint,
                    price=price,
                    source="METEORA",
                    liquidity_usd=liquidity,
                    timestamp=time.time()
                )
            
            return None
            
        except Exception as e:
            Logger.debug(f"[METEORA] Price fetch error: {e}")
            return None
    
    def _fetch_dexscreener_price(self, mint: str, dex_filter: str = None) -> Optional[tuple]:
        """
        Fetch price from DexScreener API.
        
        Args:
            mint: Token mint address
            dex_filter: Filter for specific DEX (e.g., "meteora")
            
        Returns:
            (price, liquidity) tuple or None
        """
        try:
            url = f"{self.DEXSCREENER_API}/{mint}"
            response = requests.get(url, timeout=5.0)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                return None
            
            # Filter for specific DEX if requested
            if dex_filter:
                filtered = [
                    p for p in pairs 
                    if dex_filter.lower() in p.get("dexId", "").lower()
                ]
                if filtered:
                    pairs = filtered
                else:
                    # No Meteora pool found
                    return None
            
            # Get first (most liquid) matching pool
            pool = pairs[0]
            price = float(pool.get("priceUsd", 0))
            liquidity = float(pool.get("liquidity", {}).get("usd", 0))
            
            if price > 0:
                return (price, liquidity)
            
            return None
            
        except Exception as e:
            Logger.debug(f"[METEORA] DexScreener error: {e}")
            return None
    
    def get_multiple_prices(self, mints: list, vs_token: str = None) -> Dict[str, float]:
        """
        Batch fetch prices via DexScreener (up to 30 tokens).
        """
        prices = {}
        
        for mint in mints[:30]:  # DexScreener limit
            try:
                result = self._fetch_dexscreener_price(mint, dex_filter="meteora")
                if result:
                    prices[mint] = result[0]
            except:
                pass
        
        return prices


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Meteora Feed Test")
    print("=" * 60)
    
    feed = MeteoraFeed()
    
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    
    print(f"\nFeed: {feed.get_name()}")
    print(f"Fee: {feed.get_fee_pct()}%")
    
    # Test SOL price
    spot = feed.get_spot_price(SOL, USDC)
    if spot:
        print(f"\n✅ SOL/USDC: ${spot.price:.2f} (Liquidity: ${spot.liquidity_usd:,.0f})")
    else:
        print("\n⚠️ No Meteora pool for SOL/USDC")
    
    # Test BONK price
    spot = feed.get_spot_price(BONK, USDC)
    if spot:
        print(f"✅ BONK/USDC: ${spot.price:.8f} (Liquidity: ${spot.liquidity_usd:,.0f})")
    else:
        print("⚠️ No Meteora pool for BONK/USDC")
    
    # Test quote
    quote = feed.get_quote(USDC, SOL, 100.0)
    if quote:
        print(f"\n$100 USDC -> {quote.output_amount:.4f} SOL @ {quote.price:.4f}")
    else:
        print("\nFailed to get quote")
    
    print("\n" + "=" * 60)
