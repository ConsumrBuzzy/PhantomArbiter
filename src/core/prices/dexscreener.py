import requests
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, asdict
from src.system.logging import Logger
from .base import PriceProvider


@dataclass
class MarketData:
    """
    V48.0: Rich market data from Universal Watcher.
    Provides price + context for ML trust signals.
    """
    mint: str
    symbol: str
    price_usd: float
    dex_id: str                    # Primary market DEX (raydium, orca, meteora, etc.)
    liquidity_usd: float           # Total liquidity in primary pool
    volume_24h_usd: float          # 24h trading volume
    price_change_5m: float         # 5-minute price change %
    price_change_1h: float         # 1-hour price change %
    price_change_24h: float        # 24-hour price change %
    txns_buys_24h: int             # Buy transactions in 24h
    txns_sells_24h: int            # Sell transactions in 24h
    pair_address: str              # DEX pool address
    pair_created_at: Optional[int] # Pool creation timestamp (ms)
    fdv: float                     # Fully diluted valuation
    market_cap: float              # Market cap (if available)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @property
    def buy_sell_ratio(self) -> float:
        """Buy/Sell transaction ratio (>1 = more buys)."""
        if self.txns_sells_24h == 0:
            return float('inf') if self.txns_buys_24h > 0 else 1.0
        return self.txns_buys_24h / self.txns_sells_24h
    
    @property
    def is_new_pool(self) -> bool:
        """True if pool created within last 7 days."""
        if not self.pair_created_at:
            return False
        import time
        age_days = (time.time() * 1000 - self.pair_created_at) / (1000 * 60 * 60 * 24)
        return age_days < 7


class DexScreenerProvider(PriceProvider):
    """
    V48.0: Universal Watcher - DexScreener Price Provider.
    
    Provides both simple price fetching (fetch_prices) and rich market data
    (fetch_market_data) for ML trust signals and Primary Market selection.
    """
    
    # Known DEX reliability ranking (higher = more trusted)
    DEX_TRUST_SCORES = {
    "raydium": 10,   # The Standard (Deepest Liquidity)
    "orca": 9,       # The Pro (Concentrated Liquidity / Whirlpools)
    "meteora": 8,    # The Innovator (Dynamic Pools / DLMM)
    "fluxbeam": 7,   # The Specialist (Token-2022 / Tax Tokens)
    "phoenix": 7,    # The Speed Demon (On-Chain Orderbook)
    "lifinity": 6,   # The Oracle (Market Maker for Majors)
    "openbook": 5,   # The Legacy (Old Serum Orderbook)
    "moonshot": 3,   # The Rival Nursery (DexScreener's Launchpad)
}
    
    def get_name(self) -> str:
        return "DexScreener"
        
    def fetch_prices(self, mints: list) -> dict:
        """
        Fetch prices using DexScreener API.
        Enforces 30 mint limit per request.
        """
        if not mints:
            return {}
            
        CHUNK_SIZE = 30
        all_results = {}
        
        chunks = [mints[i:i + CHUNK_SIZE] for i in range(0, len(mints), CHUNK_SIZE)]
        
        for chunk in chunks:
            try:
                ids = ",".join(chunk)
                url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
                resp = requests.get(url, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get('pairs', [])
                    if pairs:
                        for pair in pairs:
                            base_mint = pair.get('baseToken', {}).get('address')
                            
                            # Case-insensitive matching
                            if base_mint:
                                base_lower = base_mint.lower()
                                chunk_map = {m.lower(): m for m in chunk}
                                
                                if base_lower in chunk_map:
                                    original_mint = chunk_map[base_lower]
                                    if original_mint not in all_results:
                                        price_usd = float(pair.get('priceUsd', 0) or 0)
                                        if price_usd > 0:
                                            all_results[original_mint] = price_usd
                    else:
                        Logger.warning(f"      ⚠️ DexScreener returned no pairs for {len(chunk)} mints")
                        
                elif resp.status_code == 429:
                     Logger.warning(f"      ⚠️ DexScreener Rate Limit (429)")

            except Exception as e:
                Logger.error(f"      ❌ DexScreener Chunk Failed: {e}")
        
        # Debug missing
        found = set(all_results.keys())
        missing = set(mints) - found
        if missing:
             pass
                
        return all_results

    def fetch_market_data(self, mint: str, symbol: str = "UNKNOWN") -> Optional[MarketData]:
        """
        V48.0: Universal Watcher - Fetch rich market data for a single token.
        
        Selects the Primary Market (highest liquidity pool) and extracts
        comprehensive data for ML trust signals.
        
        Args:
            mint: Token mint address
            symbol: Token symbol (for logging)
            
        Returns:
            MarketData object with rich context, or None if fetch failed.
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                Logger.warning(f"⚠️ DexScreener returned {resp.status_code} for {symbol}")
                return None
            
            data = resp.json()
            pairs = data.get('pairs', [])
            
            if not pairs:
                Logger.warning(f"⚠️ No pairs found for {symbol}")
                return None
            
            # Select Primary Market: Sort by liquidity (highest first)
            primary_pair = self._select_primary_market(pairs)
            
            if not primary_pair:
                return None
            
            return self._parse_pair_to_market_data(mint, symbol, primary_pair)
            
        except Exception as e:
            Logger.error(f"❌ fetch_market_data failed for {symbol}: {e}")
            return None
    
    def fetch_market_data_batch(self, mints: List[str], symbol_map: Dict[str, str] = None) -> Dict[str, MarketData]:
        """
        V48.0: Batch fetch market data for multiple tokens.
        
        Args:
            mints: List of mint addresses
            symbol_map: Optional {mint: symbol} mapping for logging
            
        Returns:
            Dict of {mint: MarketData}
        """
        if not mints:
            return {}
        
        symbol_map = symbol_map or {}
        CHUNK_SIZE = 30
        all_results = {}
        
        chunks = [mints[i:i + CHUNK_SIZE] for i in range(0, len(mints), CHUNK_SIZE)]
        
        for chunk in chunks:
            try:
                ids = ",".join(chunk)
                url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
                resp = requests.get(url, timeout=5)
                
                if resp.status_code != 200:
                    continue
                
                data = resp.json()
                pairs = data.get('pairs', [])
                
                # Group pairs by mint
                mint_pairs: Dict[str, List] = {}
                chunk_lower_map = {m.lower(): m for m in chunk}
                
                for pair in pairs:
                    base_mint = pair.get('baseToken', {}).get('address', '').lower()
                    if base_mint in chunk_lower_map:
                        original_mint = chunk_lower_map[base_mint]
                        if original_mint not in mint_pairs:
                            mint_pairs[original_mint] = []
                        mint_pairs[original_mint].append(pair)
                
                # Select primary market for each mint
                for original_mint, token_pairs in mint_pairs.items():
                    primary = self._select_primary_market(token_pairs)
                    if primary:
                        symbol = symbol_map.get(original_mint, "UNKNOWN")
                        market_data = self._parse_pair_to_market_data(original_mint, symbol, primary)
                        if market_data:
                            all_results[original_mint] = market_data
                            
            except Exception as e:
                Logger.error(f"❌ fetch_market_data_batch chunk failed: {e}")
        
        return all_results
    
    def _select_primary_market(self, pairs: List[dict]) -> Optional[dict]:
        """
        Select the Primary Market from a list of pairs.
        
        Selection criteria (in order):
        1. Highest liquidity (USD)
        2. Tie-breaker: DEX trust score
        3. Tie-breaker: 24h volume
        """
        if not pairs:
            return None
        
        def score_pair(pair: dict) -> tuple:
            liquidity = float(pair.get('liquidity', {}).get('usd', 0) or 0)
            dex_id = pair.get('dexId', '').lower()
            trust_score = self.DEX_TRUST_SCORES.get(dex_id, 0)
            volume = float(pair.get('volume', {}).get('h24', 0) or 0)
            return (liquidity, trust_score, volume)
        
        # Sort by score tuple (highest first)
        sorted_pairs = sorted(pairs, key=score_pair, reverse=True)
        return sorted_pairs[0]
    
    def _parse_pair_to_market_data(self, mint: str, symbol: str, pair: dict) -> Optional[MarketData]:
        """Parse DexScreener pair JSON into MarketData dataclass."""
        try:
            # Extract price changes
            price_change = pair.get('priceChange', {})
            
            # Extract transaction counts
            txns = pair.get('txns', {}).get('h24', {})
            
            return MarketData(
                mint=mint,
                symbol=symbol,
                price_usd=float(pair.get('priceUsd', 0) or 0),
                dex_id=pair.get('dexId', 'unknown'),
                liquidity_usd=float(pair.get('liquidity', {}).get('usd', 0) or 0),
                volume_24h_usd=float(pair.get('volume', {}).get('h24', 0) or 0),
                price_change_5m=float(price_change.get('m5', 0) or 0),
                price_change_1h=float(price_change.get('h1', 0) or 0),
                price_change_24h=float(price_change.get('h24', 0) or 0),
                txns_buys_24h=int(txns.get('buys', 0) or 0),
                txns_sells_24h=int(txns.get('sells', 0) or 0),
                pair_address=pair.get('pairAddress', ''),
                pair_created_at=pair.get('pairCreatedAt'),
                fdv=float(pair.get('fdv', 0) or 0),
                market_cap=float(pair.get('marketCap', 0) or 0)
            )
        except Exception as e:
            Logger.error(f"❌ Failed to parse pair data for {symbol}: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# V48.0: Universal Watcher Test Script
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    """
    Manual verification script for Universal Watcher.
    Tests fetch_market_data on known multi-market tokens.
    """
    print("=" * 60)
    print("🔍 UNIVERSAL WATCHER - DexScreener Provider Test")
    print("=" * 60)
    
    provider = DexScreenerProvider()
    
    # Test tokens (known to have multiple DEX pairs)
    TEST_TOKENS = {
        "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    }
    
    print("\n📊 Testing Single Token Fetch (fetch_market_data):")
    print("-" * 60)
    
    for symbol, mint in TEST_TOKENS.items():
        print(f"\n🪙 {symbol}:")
        market_data = provider.fetch_market_data(mint, symbol)
        
        if market_data:
            print(f"   ✅ Primary Market: {market_data.dex_id.upper()}")
            print(f"   💰 Price: ${market_data.price_usd:.8f}")
            print(f"   🌊 Liquidity: ${market_data.liquidity_usd:,.0f}")
            print(f"   📈 Volume 24h: ${market_data.volume_24h_usd:,.0f}")
            print(f"   📊 Price Change (1h): {market_data.price_change_1h:+.2f}%")
            print(f"   📊 Price Change (24h): {market_data.price_change_24h:+.2f}%")
            print(f"   🔄 Buys/Sells 24h: {market_data.txns_buys_24h}/{market_data.txns_sells_24h}")
            print(f"   📐 Buy/Sell Ratio: {market_data.buy_sell_ratio:.2f}")
            print(f"   🆕 New Pool (<7d): {market_data.is_new_pool}")
            print(f"   💎 FDV: ${market_data.fdv:,.0f}")
        else:
            print(f"   ❌ Failed to fetch market data")
    
    print("\n" + "=" * 60)
    print("📦 Testing Batch Fetch (fetch_market_data_batch):")
    print("-" * 60)
    
    mints = list(TEST_TOKENS.values())
    symbol_map = {v: k for k, v in TEST_TOKENS.items()}
    
    batch_results = provider.fetch_market_data_batch(mints, symbol_map)
    
    print(f"\n✅ Fetched {len(batch_results)} / {len(mints)} tokens")
    
    for mint, data in batch_results.items():
        print(f"   • {data.symbol}: ${data.price_usd:.6f} via {data.dex_id.upper()} (Liq: ${data.liquidity_usd:,.0f})")
    
    print("\n" + "=" * 60)
    print("✅ Universal Watcher Test Complete!")
    print("=" * 60)
