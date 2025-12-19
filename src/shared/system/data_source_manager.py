"""
Data Source Manager - V10.13
============================
Implements Tiered Data Reliability (DSM).
Prevents "Zombie Broker" syndrome by managing fallbacks between data providers.

Tiers:
1. SmartRouter (Jupiter/RPC) - High Quality, Rate Limited.
2. DexScreener (API) - High Availability, Fallback.
"""

import time
import requests
from src.system.logging import Logger
from src.system.smart_router import SmartRouter

class DataSourceManager:
    """
    V11.7: Data Reliability Manager (DSM) with RPC Blacklisting.
    
    Implements tiered fallback system with proactive RPC failure tracking.
    RPCs that fail 3 times in 15 minutes are blacklisted for 2 hours.

    Tiers:
    - Tier 1 (High Quality): Jupiter RPC / SmartRouter. Best precision, rate-limited.
    - Tier 2 (High Availability): DexScreener API. Good availability, less precise.

    Priority Level: P2 (Infrastructure)
    """
    
    # V11.7a: Blacklist thresholds
    FAILURE_WINDOW_S = 15 * 60     # 15 minutes
    FAILURE_THRESHOLD = 3          # 3 failures within window
    BLACKLIST_DURATION_S = 2 * 60 * 60  # 2 hours
    
    def __init__(self):
        self.router = SmartRouter()
        
        # State
        self.use_fallback = False
        self.fallback_start_time = 0
        self.fallback_duration = 30  # Seconds to stay on Tier 2
        
        # Stats
        self.consecutive_failures = 0
        self.failure_threshold = 2
        self.tier1_successes = 0
        self.tier2_requests = 0
        
        # V11.7a: Per-RPC failure tracking
        self.tier1_failures = []       # List of failure timestamps
        self.tier1_blacklist_until = 0  # Blacklist end timestamp
        
    def get_prices(self, mints: list) -> dict:
        """
        Fetch prices for a list of mints, handling tier switching automatically.
        Returns: {mint: price}
        """
        if not mints:
            return {}
        
        # V11.7a: Check if Tier 1 is blacklisted
        if self._is_tier1_blacklisted():
            self.tier2_requests += 1
            return self._fetch_tier2(mints)
            
        # 1. Check if we should exit fallback mode
        if self.use_fallback:
            if time.time() - self.fallback_start_time > self.fallback_duration:
                Logger.info("[DSM] Attempting return to Tier 1 (Jupiter)...")
                self.use_fallback = False
                self.consecutive_failures = 0
        
        # 2. Tier 1: Smart Router (Jupiter)
        if not self.use_fallback:
            try:
                results = self._fetch_tier1(mints)
                
                if results:
                    self.consecutive_failures = 0
                    self.tier1_successes += 1
                    return results
                else:
                    self.consecutive_failures += 1
                    self._record_tier1_failure()
                    Logger.warning(f"[DSM] Tier 1 Failed ({self.consecutive_failures}/{self.failure_threshold})")
            except Exception as e:
                self.consecutive_failures += 1
                self._record_tier1_failure()
                Logger.warning(f"[DSM] Tier 1 Error: {str(e)[:40]}")

            # Switch to Fallback if threshold reached
            if self.consecutive_failures >= self.failure_threshold:
                Logger.warning(f"[DSM] Switching to Tier 2 (DexScreener) for {self.fallback_duration}s")
                self.use_fallback = True
                self.fallback_start_time = time.time()
        
        # 3. Tier 2: DexScreener (Fallback)
        self.tier2_requests += 1
        return self._fetch_tier2(mints)
    
    def _is_tier1_blacklisted(self) -> bool:
        """V11.7a: Check if Tier 1 is currently blacklisted."""
        now = time.time()
        
        if now < self.tier1_blacklist_until:
            remaining = int((self.tier1_blacklist_until - now) / 60)
            # Only log occasionally to avoid spam
            if int(now) % 60 == 0:
                Logger.debug(f"   🚫 DSM: Tier 1 blacklisted ({remaining}m remaining)")
            return True
        return False
    
    def _record_tier1_failure(self):
        """V11.7a: Record a Tier 1 failure and check for blacklist threshold."""
        now = time.time()
        
        # Add failure timestamp
        self.tier1_failures.append(now)
        
        # Clean old failures outside window
        cutoff = now - self.FAILURE_WINDOW_S
        self.tier1_failures = [t for t in self.tier1_failures if t > cutoff]
        
        # Check if threshold reached
        if len(self.tier1_failures) >= self.FAILURE_THRESHOLD:
            self.tier1_blacklist_until = now + self.BLACKLIST_DURATION_S
            self.tier1_failures = []  # Reset
            Logger.warning(f"   🚫 DSM: Tier 1 BLACKLISTED for 2 hours (3 failures in 15min)")


    def _fetch_tier1(self, mints: list) -> dict:
        """Fetch from Jupiter using SmartRouter."""
        # Using a simplistic bulk approach for now, assuming SmartRouter handles it or we split chunks.
        # SmartRouter.get_jupiter_price expects comma-separated IDs.
        
        all_results = {}
        chunk_size = 30
        chunks = [mints[i:i + chunk_size] for i in range(0, len(mints), chunk_size)]
        
        success = False
        for chunk in chunks:
            ids = ",".join(chunk)
            data = self.router.get_jupiter_price(ids, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v") # USDC
            
            if data and 'data' in data:
                for mint, info in data['data'].items():
                    price = float(info.get('price', 0))
                    if price > 0:
                        all_results[mint] = price
                        success = True
            
            time.sleep(0.2) # Light throttle within Tier 1
            
        return all_results if success else {}

    def _fetch_tier2(self, mints: list) -> dict:
        """Fetch from DexScreener (Fallback)."""
        all_results = {}
        chunk_size = 28 # DexScreener limit is 30, keep it safe
        chunks = [mints[i:i + chunk_size] for i in range(0, len(mints), chunk_size)]
        
        for chunk in chunks:
            try:
                ids = ",".join(chunk)
                url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
                resp = requests.get(url, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get('pairs', [])
                    for pair in pairs:
                        base_mint = pair.get('baseToken', {}).get('address')
                        price = float(pair.get('priceUsd', 0) or 0)
                        
                        # V12.1: Cache liquidity data from DexScreener
                        liquidity = pair.get('liquidity', {}).get('usd', 0)
                        if base_mint and liquidity:
                            self._cache_liquidity(base_mint, liquidity)
                        
                        # DexScreener returns multiple pairs per token. Take the first/most liquid one.
                        if base_mint and base_mint in chunk and base_mint not in all_results and price > 0:
                            all_results[base_mint] = price
            except Exception as e:
                Logger.warning(f"      ⚠️ DSM Tier 2 Error: {str(e)[:30]}")
                
            time.sleep(0.1)
            
        return all_results
    
    # ═══════════════════════════════════════════════════════════════════
    # V12.1: Liquidity and Slippage Analysis
    # ═══════════════════════════════════════════════════════════════════
    
    # Slippage thresholds
    SLIPPAGE_HARD_REJECT = 2.0   # >2% = reject token
    SLIPPAGE_SOFT_FILTER = 1.0   # >1% = halve position size
    REFERENCE_TRADE_USD = 50     # $50 reference for slippage calculation
    
    def __init_liquidity_cache(self):
        """Initialize liquidity cache if not exists."""
        if not hasattr(self, '_liquidity_cache'):
            self._liquidity_cache = {}   # {mint: liquidity_usd}
            self._slippage_cache = {}    # {mint: slippage_pct}
            self._cache_time = {}        # {mint: timestamp}
            self._cache_ttl = 60         # 60 second cache (respects Jupiter 60 req/min limit)
    
    def _cache_liquidity(self, mint: str, liquidity: float):
        """V12.1: Cache liquidity data from DexScreener."""
        self.__init_liquidity_cache()
        self._liquidity_cache[mint] = liquidity
        self._cache_time[mint] = time.time()
    
    def get_liquidity(self, mint: str) -> float:
        """V12.1: Get cached liquidity (TVL) for a token in USD."""
        self.__init_liquidity_cache()
        
        # Check cache validity
        cache_time = self._cache_time.get(mint, 0)
        if time.time() - cache_time < self._cache_ttl:
            return self._liquidity_cache.get(mint, 0)
        
        return 0
    
    def get_slippage(self, mint: str, amount_usd: float = None) -> float:
        """
        V12.1: Get estimated slippage for a trade.
        
        Uses Jupiter /quote API to estimate price impact for a $50 reference trade.
        Returns slippage as a percentage (e.g., 0.5 = 0.5%).
        """
        self.__init_liquidity_cache()
        
        if amount_usd is None:
            amount_usd = self.REFERENCE_TRADE_USD
        
        # Check cache
        cache_time = self._cache_time.get(f"slip_{mint}", 0)
        if time.time() - cache_time < self._cache_ttl:
            return self._slippage_cache.get(mint, 0)
        
        try:
            # Jupiter /quote endpoint
            # Convert $50 to USDC lamports (USDC has 6 decimals)
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            amount_lamports = int(amount_usd * 1_000_000)  # $50 = 50,000,000 lamports
            
            url = f"https://quote-api.jup.ag/v6/quote?inputMint={usdc_mint}&outputMint={mint}&amount={amount_lamports}&slippageBps=100"
            
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                
                # Price impact is provided directly
                price_impact = float(data.get('priceImpactPct', 0))
                
                # Cache the result
                self._slippage_cache[mint] = price_impact
                self._cache_time[f"slip_{mint}"] = time.time()
                
                return price_impact
            
        except Exception as e:
            Logger.debug(f"   ⚠️ Slippage check failed for {mint[:8]}: {str(e)[:30]}")
        
        return 0
    
    def check_slippage_filter(self, mint: str) -> tuple:
        """
        V12.1: Check if token passes slippage filters.
        
        Returns: (passes: bool, slippage: float, action: str)
        - passes: True if token is tradeable
        - slippage: The slippage percentage
        - action: 'OK', 'HALF_SIZE', or 'REJECT'
        """
        slippage = self.get_slippage(mint)
        
        if slippage > self.SLIPPAGE_HARD_REJECT:
            return (False, slippage, 'REJECT')
        elif slippage > self.SLIPPAGE_SOFT_FILTER:
            return (True, slippage, 'HALF_SIZE')
        else:
            return (True, slippage, 'OK')
    
    def get_metrics(self, mint: str) -> dict:
        """
        V12.1: Get all metrics for a token.
        
        Returns: {
            'liquidity': float (USD),
            'slippage': float (%),
            'slippage_action': str ('OK', 'HALF_SIZE', 'REJECT')
        }
        """
        self.__init_liquidity_cache()
        
        liquidity = self.get_liquidity(mint)
        passes, slippage, action = self.check_slippage_filter(mint)
        
        return {
            'liquidity': liquidity,
            'slippage': slippage,
            'slippage_action': action
        }
    
    # ═══════════════════════════════════════════════════════════════════
    # V12.0: Volatility Metrics (Realized Volatility)
    # ═══════════════════════════════════════════════════════════════════
    
    def get_volatility(self, symbol: str) -> float:
        """
        V12.0: Calculate Realized Volatility (RV) for a token.
        
        Calculates the annualized standard deviation of returns based on
        price history from SharedPriceCache (last ~1 hour of data).
        
        Args:
            symbol: Token symbol (e.g., "BONK")
            
        Returns:
            Volatility as a percentage (e.g., 2.5 = 2.5%)
        """
        self.__init_liquidity_cache()
        
        # Check cache
        cache_key = f"vol_{symbol}"
        cache_time = self._cache_time.get(cache_key, 0)
        if time.time() - cache_time < self._cache_ttl:
            return self._slippage_cache.get(cache_key, 0)
        
        try:
            from src.core.shared_cache import SharedPriceCache
            import math
            
            # Get price history
            prices = SharedPriceCache.get_price_history(symbol)
            
            if not prices or len(prices) < 10:
                return 0
            
            # Calculate returns (log returns are more accurate for volatility)
            returns = []
            for i in range(1, len(prices)):
                if prices[i-1] > 0 and prices[i] > 0:
                    ret = math.log(prices[i] / prices[i-1])
                    returns.append(ret)
            
            if len(returns) < 5:
                return 0
            
            # Calculate standard deviation
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance)
            
            # Convert to percentage (hourly volatility)
            volatility_pct = std_dev * 100
            
            # Cache the result
            self._slippage_cache[cache_key] = volatility_pct
            self._cache_time[cache_key] = time.time()
            
            return volatility_pct
            
        except Exception as e:
            Logger.debug(f"   ⚠️ Volatility calc failed for {symbol}: {str(e)[:30]}")
            return 0
    
    def get_full_metrics(self, mint: str, symbol: str) -> dict:
        """
        V12.0: Get ALL metrics for a token (liquidity, slippage, volatility).
        
        Returns: {
            'liquidity': float (USD),
            'slippage': float (%),
            'slippage_action': str,
            'volatility': float (%)
        }
        """
        metrics = self.get_metrics(mint)
        metrics['volatility'] = self.get_volatility(symbol)
        return metrics
