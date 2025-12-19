"""
V1.0: Jupiter Price Feed
========================
Primary DEX aggregator for Solana - routes through multiple AMMs.
"""

import time
import requests
from typing import Optional

from config.settings import Settings
from src.system.logging import Logger
from src.system.smart_router import SmartRouter
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
    
    This gives us the "best execution" price but may not reflect
    individual DEX prices for arbitrage detection.
    """
    
    # Common mints for convenience
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    # Token decimals cache
    DECIMALS = {
        USDC_MINT: 6,
        SOL_MINT: 9,
        # Add more as needed
    }
    
    def __init__(self):
        self.router = SmartRouter()
        self._price_cache: dict = {}
        self._cache_ttl = 2.0  # 2 second cache
        
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
            
            # Fetch quote from Jupiter
            raw_quote = self.router.get_jupiter_quote(
                input_mint, 
                output_mint, 
                amount_atomic, 
                slippage_bps=50  # 0.5% default slippage
            )
            
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
        Get spot price - uses DexScreener as primary (more reliable).
        
        Jupiter aggregates from multiple DEXs so we show the "best available"
        price which is typically what Jupiter would route through.
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
        
        # Use DexScreener (most reliable) - get best price across DEXs
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
        Batch fetch prices for multiple tokens.
        
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
            ids = ",".join(mints[:30])  # Jupiter limit
            url = f"https://price.jup.ag/v6/price?ids={ids}&vsToken={vs_token}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return {}
                
            data = resp.json()
            results = {}
            
            for mint, info in data.get('data', {}).items():
                price = float(info.get('price', 0.0))
                if price > 0:
                    results[mint] = price
                    # Update cache
                    cache_key = f"{mint}:{vs_token}"
                    self._price_cache[cache_key] = {
                        'price': price,
                        'timestamp': time.time()
                    }
                    
            return results
            
        except Exception as e:
            Logger.debug(f"Jupiter batch price error: {e}")
            return {}
