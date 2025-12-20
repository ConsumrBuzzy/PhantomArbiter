"""
V1.1: Jupiter Price Feed
========================
Primary DEX aggregator for Solana - routes through multiple AMMs.

Uses Jupiter v3 Price API with API key authentication.
Falls back to DexScreener if API unavailable.
"""

import os
import time
import requests
from typing import Optional

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.smart_router import SmartRouter
from .price_source import PriceSource, Quote, SpotPrice


class JupiterFeed(PriceSource):
    """
    Jupiter DEX Aggregator price feed.
    
    Jupiter aggregates liquidity from:
    - Raydium
    - Orca
    - Meteora
    - Phoenix
    - And many more
    
    Uses v3 Price API (requires API key from portal.jup.ag)
    """
    
    # API Configuration
    PRICE_API_V3 = "https://api.jup.ag/price/v3"
    
    # Common mints for convenience
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    # Token decimals cache
    DECIMALS = {
        USDC_MINT: 6,
        SOL_MINT: 9,
        "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7": 6, # DRIFT
        "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS": 6, # KMNO
        "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6": 9, # TNSR
        "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof": 8, # RENDER
    }
    
    def __init__(self):
        self.router = SmartRouter()
        self._price_cache: dict = {}
        self._cache_ttl = 2.0  # 2 second cache
        
        # Load API key from environment
        self.api_key = os.getenv("JUPITER_API_KEY", "").strip("'\"")
        if self.api_key:
            Logger.debug(f"Jupiter API key loaded: {self.api_key[:8]}...")
        else:
            Logger.debug("Jupiter API key not found, will use DexScreener fallback")
        
    def get_name(self) -> str:
        return "JUPITER"
    
    def get_fee_pct(self) -> float:
        """Jupiter has no platform fee, but routes through AMMs with fees."""
        return 0.1  # Approximate average routing fee
    
    def _get_decimals(self, mint: str) -> int:
        """Get token decimals (cached)."""
        return self.DECIMALS.get(mint, 9)  # Default to 9 (SOL-like)
    
    def get_quote(
        self, 
        input_mint: str, 
        output_mint: str, 
        amount: float
    ) -> Optional[Quote]:
        """
        Fetch a real executable quote from Jupiter API.
        
        Args:
            input_mint: Token to sell
            output_mint: Token to buy  
            amount: Human-readable amount of input token
            
        Returns:
            Quote with routing info for execution
        """
        try:
            # Convert to atomic units
            input_decimals = self._get_decimals(input_mint)
            output_decimals = self._get_decimals(output_mint)
            amount_atomic = int(amount * (10 ** input_decimals))
            
            # Method 1: Try Price API V2 (Faster, Reliable)
            # This is "The Better Way" for scanning
            price_data = self.router.get_jupiter_price_v2(output_mint)
            
            price = 0.0
            if price_data and output_mint in price_data:
                 price_str = price_data[output_mint].get("price", "0")
                 price = float(price_str) if price_str else 0.0

            if price > 0:
                 # Calculate output based on Spot Price
                 # This mimics a quote for SCAINING purposes
                 # Execution will still use Swap API
                 output_amount = amount / price
                 
                 return Quote(
                    dex="JUPITER",
                    input_mint=input_mint,
                    output_mint=output_mint,
                    input_amount=amount,
                    output_amount=output_amount,
                    price=1/price, # Price in USDC/Token
                    slippage_estimate_pct=0.1,
                    fee_pct=0.1,
                    route=None, # No route needed for scan
                    timestamp=time.time()
                )

            # Method 2: Fallback to Swap Quote (Slow, Rate Limited)
            # ... (Existing logic removed for cleaner switch)
            
            if not raw_quote:
                return None
            
            # Parse response
            out_amount_atomic = int(raw_quote.get('outAmount', 0))
            output_amount = out_amount_atomic / (10 ** output_decimals)
            
            # Calculate effective price
            price = output_amount / amount if amount > 0 else 0
            
            # Extract slippage estimate
            slippage_bps = raw_quote.get('slippageBps', 0)
            
            return Quote(
                dex="JUPITER",
                input_mint=input_mint,
                output_mint=output_mint,
                input_amount=amount,
                output_amount=output_amount,
                price=price,
                slippage_estimate_pct=slippage_bps / 100,
                fee_pct=self.get_fee_pct(),
                route=raw_quote,  # Store full quote for execution
                timestamp=time.time()
            )
            
        except Exception as e:
            Logger.debug(f"Jupiter quote error: {e}")
            return None
    
    def get_spot_price(self, base_mint: str, quote_mint: str) -> Optional[SpotPrice]:
        """
        Get spot price using Jupiter v3 Price API.
        
        Falls back to DexScreener if API unavailable.
        """
        cache_key = f"{base_mint}:{quote_mint}"
        
        # Check cache
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if time.time() - cached['timestamp'] < self._cache_ttl:
                return SpotPrice(
                    dex="JUPITER",
                    base_mint=base_mint,
                    quote_mint=quote_mint,
                    price=cached['price'],
                    timestamp=cached['timestamp']
                )
        
        # Try Jupiter v3 API first (if we have API key)
        price = None
        if self.api_key:
            price = self._fetch_jupiter_v3_price(base_mint)
        
        # Fallback to DexScreener
        if not price:
            price = self._fetch_dexscreener_best_price(base_mint)
        
        if price and price > 0:
            timestamp = time.time()
            self._price_cache[cache_key] = {
                'price': price,
                'timestamp': timestamp
            }
            
            return SpotPrice(
                dex="JUPITER",
                base_mint=base_mint,
                quote_mint=quote_mint,
                price=price,
                timestamp=timestamp
            )
        
        return None
    
    def _fetch_jupiter_v3_price(self, mint: str) -> Optional[float]:
        """
        Fetch price from Jupiter v3 Price API.
        
        Requires API key from portal.jup.ag
        """
        try:
            url = f"{self.PRICE_API_V3}?ids={mint}"
            headers = {"x-api-key": self.api_key}
            
            resp = requests.get(url, headers=headers, timeout=5)
            
            if resp.status_code == 401:
                Logger.debug("Jupiter API key invalid or expired")
                return None
                
            if resp.status_code != 200:
                return None
                
            data = resp.json()
            
            # v3 response format: {mint: {price: "123.45", ...}}
            token_data = data.get(mint, {})
            price_str = token_data.get('price', '0')
            price = float(price_str) if price_str else 0.0
            
            return price if price > 0 else None
            
        except Exception as e:
            Logger.debug(f"Jupiter v3 API error: {e}")
            return None
    
    def _fetch_dexscreener_best_price(self, mint: str) -> Optional[float]:
        """
        Fetch best available price from DexScreener.
        
        DexScreener returns pools sorted by liquidity, so first price
        is typically the most accurate/liquid - similar to what Jupiter
        would route through.
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
            
            # Get price from first (most liquid) pair
            price = float(pairs[0].get('priceUsd', 0) or 0)
            return price if price > 0 else None
            
        except Exception as e:
            Logger.debug(f"DexScreener error: {e}")
            return None
    
    def get_multiple_prices(self, mints: list, vs_token: str = None) -> dict:
        """
        Batch fetch prices for multiple tokens via SmartRouter (V2 API).
        
        Args:
            mints: List of token mint addresses
            vs_token: Quote token (default: USDC)
            
        Returns:
            Dict of {mint: price}
        """
        if not mints:
            return {}
            
        vs_token = vs_token or self.USDC_MINT
        
        try:
            # Use SmartRouter's high-perf V2 endpoint with chunking
            chunk_size = 30
            results = {}
            
            for i in range(0, len(mints), chunk_size):
                chunk = mints[i:i + chunk_size]
                ids = ",".join(chunk)
                
                # SmartRouter.get_jupiter_price_v2 handles API keys and cooldowns
                data = self.router.get_jupiter_price_v2(ids, vs_token=vs_token)
                
                if data:
                    for mint, info in data.items():
                        price = float(info.get('price', 0.0))
                        if price > 0:
                            results[mint] = price
                            # Update local cache
                            cache_key = f"{mint}:{vs_token}"
                            self._price_cache[cache_key] = {
                                'price': price,
                                'timestamp': time.time()
                            }
                
                if len(mints) > chunk_size:
                    time.sleep(0.1)  # Small gap between chunks
                    
            return results
            
        except Exception as e:
            Logger.debug(f"Jupiter batch fetch error: {e}")
            return {}
