"""
Mock Price Feeds
================
Deterministic price feeds for testing without HTTP calls.
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
import time


@dataclass
class MockQuote:
    """Mock quote response."""
    input_mint: str
    output_mint: str
    in_amount: float
    out_amount: float
    price: float
    price_impact_pct: float = 0.1
    route: str = "MOCK_ROUTE"
    

@dataclass
class MockSpotPrice:
    """Mock spot price response."""
    base: str
    quote: str
    price: float
    source: str = "MOCK"
    timestamp: float = field(default_factory=time.time)


class MockPriceFeed:
    """
    Base mock price feed with preset prices.
    
    Usage:
        feed = MockPriceFeed()
        feed.set_price("SOL", "USDC", 150.0)
        price = feed.get_spot_price("SOL", "USDC")
    """
    
    def __init__(self, name: str = "MOCK"):
        self.name = name
        self._prices: Dict[str, Dict[str, float]] = {}
        self._fee_pct = 0.003  # 0.3% default
        self.call_count = 0
        
    def set_price(self, base: str, quote: str, price: float):
        """Set a price for a trading pair."""
        if base not in self._prices:
            self._prices[base] = {}
        self._prices[base][quote] = price
        
    def set_prices(self, prices: Dict[str, float]):
        """Set multiple prices (token -> USD value)."""
        for token, price in prices.items():
            self.set_price(token, "USDC", price)
            
    def get_name(self) -> str:
        return self.name
        
    def get_fee_pct(self) -> float:
        return self._fee_pct
        
    def get_spot_price(self, base: str, quote: str) -> Optional[MockSpotPrice]:
        """Get spot price for a pair."""
        self.call_count += 1
        
        if base in self._prices and quote in self._prices[base]:
            return MockSpotPrice(
                base=base,
                quote=quote,
                price=self._prices[base][quote],
                source=self.name
            )
        return None
        
    def get_quote(self, input_mint: str, output_mint: str, amount: float) -> Optional[MockQuote]:
        """Get a quote for swapping tokens."""
        self.call_count += 1
        
        price_data = self.get_spot_price(input_mint, output_mint)
        if not price_data:
            return None
            
        out_amount = amount * price_data.price * (1 - self._fee_pct)
        
        return MockQuote(
            input_mint=input_mint,
            output_mint=output_mint,
            in_amount=amount,
            out_amount=out_amount,
            price=price_data.price,
            price_impact_pct=0.1
        )


class MockJupiterFeed(MockPriceFeed):
    """
    Mock Jupiter aggregator feed.
    
    Provides all JupiterFeed methods without HTTP calls.
    Pre-configured with common Solana tokens.
    """
    
    def __init__(self):
        super().__init__(name="JUPITER")
        self._fee_pct = 0.0035  # Jupiter typical fee
        
        # Pre-seed common prices
        self.set_prices({
            "SOL": 150.0,
            "USDC": 1.0,
            "JUP": 0.85,
            "JTO": 2.50,
            "BONK": 0.00001,
            "WIF": 1.20,
            "PYTH": 0.40,
            "RNDR": 8.50,
        })
        
        # Mint address mapping
        self._mint_to_symbol = {
            "So11111111111111111111111111111111111111112": "SOL",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
            "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL": "JTO",
        }
        
    def get_spot_price(self, base_mint: str, quote_mint: str) -> Optional[MockSpotPrice]:
        """Get spot price, supporting mint addresses."""
        # Resolve mint to symbol
        base = self._mint_to_symbol.get(base_mint, base_mint)
        quote = self._mint_to_symbol.get(quote_mint, quote_mint)
        
        return super().get_spot_price(base, quote)
        
    async def get_multiple_prices(self, mints: List[str], vs_token: str = None) -> Dict[str, float]:
        """Async batch price fetch (mocked)."""
        self.call_count += 1
        
        result = {}
        for mint in mints:
            symbol = self._mint_to_symbol.get(mint, mint)
            if symbol in self._prices and "USDC" in self._prices[symbol]:
                result[mint] = self._prices[symbol]["USDC"]
        return result
    
    def set_arb_opportunity(self, spread_pct: float = 1.0):
        """
        Configure prices to create an arbitrage opportunity.
        
        Sets up SOL/JUP/USDC triangle with specified spread.
        """
        base_sol = 150.0
        base_jup = 0.85
        
        # Create mispricing: SOL/JUP should be 150/0.85 = 176.47
        # Set it higher to create arb opportunity
        mispriced_ratio = (base_sol / base_jup) * (1 + spread_pct / 100)
        
        self.set_price("SOL", "USDC", base_sol)
        self.set_price("JUP", "USDC", base_jup)
        self.set_price("SOL", "JUP", mispriced_ratio)


class MockVenueFeed(MockPriceFeed):
    """
    Mock feed for a specific venue (Raydium, Orca, etc).
    
    Used to test cross-venue spread detection.
    """
    
    def __init__(self, venue_name: str, fee_pct: float = 0.003):
        super().__init__(name=venue_name)
        self._fee_pct = fee_pct
