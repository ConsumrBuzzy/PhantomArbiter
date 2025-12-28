
import time
import os
import json
from collections import deque
# from .config import RiskConfig
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.system.smart_router import SmartRouter
import requests


class CircuitBreaker:
    """
    Manages API health state.
    If failures exceed threshold, opens circuit and forces fallback.
    """
    def __init__(self, failure_threshold=3, cooldown_seconds=300):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.last_failure_time = 0
        self.is_open = False
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold and not self.is_open:
            self.is_open = True
            Logger.warning(f"      ⚡ CIRCUIT BREAKER TRIPPED: Switching to DexScreener for {self.cooldown_seconds}s")
    
    def record_success(self):
        if self.is_open:
            Logger.success("      ⚡ CIRCUIT BREAKER RESET: Jupiter is healthy again.")
        self.failures = 0
        self.is_open = False
        
    def can_try_primary(self):
        if not self.is_open:
            return True
        # Half-open check
        if time.time() - self.last_failure_time > self.cooldown_seconds:
             return True # Try once
        return False

# Global Circuit Breaker Instance
jupiter_circuit = CircuitBreaker()

# V11.2a: CoinGecko Rate Limit Cooldown (5 minutes on 429)
CG_429_COOLDOWN_UNTIL = 0

def batch_fetch_jupiter_prices(mints):
    """
    Fetch prices for multiple mints in chunks.
    Uses Circuit Breaker to avoid hammering dead Jupiter API.
    """
    if not mints: return {}
    import time
    
    # 0. Check Circuit Breaker
    use_jupiter = jupiter_circuit.can_try_primary()
    
    CHUNK_SIZE = 30
    all_results = {}
    
    # Process in chunks (V10.7: Add delay to avoid rate limits)
    chunks = [mints[i:i + CHUNK_SIZE] for i in range(0, len(mints), CHUNK_SIZE)]
    
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(0.5) # Throttle 500ms between chunks

        ids = ",".join(chunk)
        chunk_success = False
        
        # 1. Try Jupiter (Only if circuit is closed or half-open)
        if use_jupiter:
            router = SmartRouter()
            data = router.get_jupiter_price(ids, Settings.USDC_MINT)
            
            if data:
                for mint, info in data.get('data', {}).items():
                    all_results[mint] = info.get('price', 0.0)
                chunk_success = True
                jupiter_circuit.record_success()
            else:
                 # Check if cooldown triggered?
                 # If router returns None, it might be 429 or error.
                 # We assume generic failure for circuit breaker purposes
                 jupiter_circuit.record_failure()
        
        # 2. Fallback to DexScreener (If Jupiter skipped OR failed)
        if not chunk_success:
            if use_jupiter: # Only warn if we actually tried Jupiter and it failed
                Logger.warning(f"      ⚠️ Jupiter Batch Failed ({len(chunk)}/30). Trying DexScreener...")
            # Else: Silent switch because circuit is open
            
            try:
                # DexScreener supports max 30 addresses per call
                ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
                ds_resp = requests.get(ds_url, timeout=5)
                if ds_resp.status_code == 200:
                    ds_data = ds_resp.json()
                    
                    # Store found prices
                    for pair in ds_data.get('pairs', []):
                        base_mint = pair.get('baseToken', {}).get('address')
                        price_usd = float(pair.get('priceUsd', 0) or 0)
                        
                        # Only take the first/best price for each mint in this chunk
                        if base_mint and base_mint in chunk and base_mint not in all_results:
                            all_results[base_mint] = price_usd
                    chunk_success = True
                            
            except Exception as ds_e:
                Logger.error(f"      ❌ DexScreener Fallback Failed: {ds_e}")
        
        # 3. V9.6 Tier 3: SmartRouter (Birdeye fallback for any missed mints)
        if not chunk_success:
            try:
                router = SmartRouter()  # Uses already-imported system.smart_router
                for mint in chunk:
                    if mint not in all_results:
                        # SmartRouter has get_jupiter_price which returns dict
                        # This is a last-ditch attempt via the existing router
                        ids = mint
                        data = router.get_jupiter_price(ids, Settings.USDC_MINT)
                        if data and 'data' in data:
                            price = data['data'].get(mint, {}).get('price', 0.0)
                            if price and price > 0:
                                all_results[mint] = price
            except Exception:
                pass  # SmartRouter fallback is optional

    return all_results

class DataFeed:
    """Manages Price Feeds, Virtual Candles, and Technical Indicators."""
    
    def __init__(self, mint=None, symbol=None, is_critical=False, lazy_init=False):
        self.mint = mint or Settings.TARGET_MINT  # Custom or default
        self.symbol = symbol or self.mint[:8]  # Short identifier for files
        self.is_critical = is_critical       # If True, retry hard. If False, fast fail.
        self.lazy_init = lazy_init           # V11.4: If True, skip blocking backfill
        self.raw_prices = deque(maxlen=100)  # Ticks
        self.raw_volumes = deque(maxlen=100) # V33.4: Ticks Volume
        self.candles = deque(maxlen=60)      # 1-min Virtual Candles
        
        # Current candle inputs
        self.current_candle = {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'ticks': 0}
        self.current_rsi = 50.0
        self.last_source = "None" # Track price source
        
        # V33.3: Infrastructure Upgrade
        self.liquidity_usd = 0.0
        self.volume_h1 = 0.0
        self.last_metadata_update = 0
        
        # V11.8: Cache file path moved to data/cache/
        cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        self.history_file = os.path.join(cache_dir, f"price_history_{self.symbol}.json")
        
        # V7.2b: Check if broker has sufficient history
        from src.core.shared_cache import SharedPriceCache, is_broker_alive
        broker_has_data = False
        
        if is_broker_alive():
            # Check if broker has at least 50 history points for this symbol
            history = SharedPriceCache.get_price_history(self.symbol, max_age=7200)
            if len(history) >= 50:
                broker_has_data = True
                self.raw_prices = deque(history[-100:], maxlen=100)
                Logger.info(f"   📡 {self.symbol}: Loaded {len(history)} points from broker cache")
        
        if broker_has_data:
            pass
        else:
            # Try to load persisted history
            loaded = self._load_history()
            if not loaded and not lazy_init:
                # V11.4: Only backfill if NOT lazy_init
                self.backfill_history()
    
    # V33.3: Metadata Fetching (Volume/Liquidity)
    def fetch_metadata(self):
        """Fetch Volume and Liquidity from DexScreener (Slow poll)."""
        import time
        if time.time() - self.last_metadata_update < 60: # Cooldown 60s
            return
            
        try:
            ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{self.mint}"
            ds_resp = requests.get(ds_url, timeout=5)
            if ds_resp.status_code == 200:
                data = ds_resp.json()
                pairs = data.get('pairs', [])
                if pairs:
                    # Take top pair
                    pair = pairs[0]
                    self.liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0.0))
                    self.volume_h1 = float(pair.get('volume', {}).get('h1', 0.0))
                    self.last_metadata_update = time.time()
                    # Logger.debug(f"   📊 {self.symbol} Metadata: Liq=${self.liquidity_usd/1000:.0f}k Vol(1h)=${self.volume_h1/1000:.0f}k")
        except Exception:
            pass

    def _fetch_jupiter_price(self, mint, vs_token):
        """Direct Jupiter Price API call with DexScreener Fallback."""
        try:
            url = f"https://price.jup.ag/v6/price?ids={mint}&vsToken={vs_token}"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            price = data.get('data', {}).get(mint, {}).get('price', 0.0)
            if price > 0:
                # V33.3: Opportunistic Metadata Fetch
                # If we're hitting API, might as well check metadata if stale
                self.fetch_metadata() 
                return price, "JUP"
        except Exception as e:
            pass # Fallback
            
        # Fallback to DexScreener
        try:
            ds_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            ds_resp = requests.get(ds_url, timeout=5)
            if ds_resp.status_code == 200:
                ds_data = ds_resp.json()
                pairs = ds_data.get('pairs', [])
                if pairs:
                    pair = pairs[0] 
                    price = float(pair.get('priceUsd', 0) or 0.0)
                    
                    # V33.3: Capture Metadata since we have the payload
                    self.liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0.0))
                    self.volume_h1 = float(pair.get('volume', {}).get('h1', 0.0))
                    self.last_metadata_update = time.time()
                    
                    if price > 0:
                         return price, "DEX"
        except Exception as e:
            pass  # DexScreener fallback failed, return 0.0
        return 0.0, "None"
    
    def resolve_coingecko_id(self, mint):
        """
        Dynamically find CoinGecko ID from contract address.
        Useful for tokens like JTO/PYTH where contract endpoint fails but ID endpoint works.
        """
        try:
            url = f"https://api.coingecko.com/api/v3/coins/solana/contract/{mint}"
            
            # V11.0: Injection via Header (Cleaner)
            headers = {}
            if Settings.COINGECKO_API_KEY:
                headers["x-cg-demo-api-key"] = Settings.COINGECKO_API_KEY
            
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                cg_id = data.get("id")
                if cg_id:
                    Logger.info(f"   🔍 Resolved CoinGecko ID for {self.symbol}: {cg_id}")
                    # Cache in Settings (Runtime only)
                    Settings.ASSET_METADATA[self.symbol] = {"coingecko_id": cg_id}
                    return cg_id
        except Exception:
            pass
        return None

    def _fetch_coingecko_history(self, mint):
        """Direct CoinGecko History API call with Retry Logic."""
        import time
        global CG_429_COOLDOWN_UNTIL
        
        # V11.2a: Check global 429 cooldown
        if time.time() < CG_429_COOLDOWN_UNTIL:
            remaining = int(CG_429_COOLDOWN_UNTIL - time.time())
            Logger.debug(f"      ⏳ CoinGecko in cooldown ({remaining}s remaining), skipping")
            return [], []
        
        # 1. Check Metadata
        cg_id = Settings.ASSET_METADATA.get(self.symbol, {}).get("coingecko_id")
        
        # 2. If missing, try to resolve it dynamically
        if not cg_id:
            cg_id = self.resolve_coingecko_id(mint)
        
        if cg_id:
            # Use ID-based endpoint (Reliable)
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days=1"
        else:
             # Fallback to contract address endpoint (Flaky)
            url = f"https://api.coingecko.com/api/v3/coins/solana/contract/{mint}/market_chart?vs_currency=usd&days=1"

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # V11.0: Injection via Header
        if Settings.COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = Settings.COINGECKO_API_KEY
        
        # Priority Logic: Only retry if critical (held asset)
        max_retries = 3 if self.is_critical else 0
        
        for attempt in range(max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    prices = [p[1] for p in data.get('prices', [])]
                    volumes = [v[1] for v in data.get('total_volumes', [])]
                    return prices, volumes
                elif resp.status_code == 429:
                    # V11.2a: Set global cooldown on 429
                    CG_429_COOLDOWN_UNTIL = time.time() + 300  # 5 minute cooldown
                    Logger.warning(f"      ⚠️ CG Rate Limit (429) - Cooldown 5min")
                    return [], []
                else:
                    Logger.warning(f"      ⚠️ CG Error: {resp.status_code}")
                    return [], []
            except Exception as e:
                Logger.warning(f"      ⚠️ CG Exception: {e}")
                return [], []
        
        Logger.error("      ❌ CG Failed after retries")
        return [], []

    def _load_history(self):
        """Load price history from disk if recent enough."""
        import json
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    
                # Check if data is recent (last 1 hour)
                last_ts = data.get("last_updated", 0)
                if time.time() - last_ts < 3600:  # 1 hour
                    prices = data.get("prices", [])
                    if len(prices) >= 15:
                        for p in prices[-100:]:
                            self.raw_prices.append(p)
                        self.current_rsi = self.calculate_rsi()
                        self.last_source = "CACHE"
                        Logger.info(f"   📂 Loaded {len(self.raw_prices)} prices from disk. RSI: {self.current_rsi}")
                        return True
                    else:
                        Logger.warning(f"   ⚠️ Cached history too short ({len(prices)} prices)")
                else:
                    Logger.warning(f"   ⚠️ Cached history stale (>{(time.time()-last_ts)/60:.0f}m old)")
        except Exception as e:
            Logger.error(f"   ⚠️ Load history failed: {e}")
        return False
    
    def _save_history(self):
        """
        Persist price history to local JSON cache.
        deprecated (V35.4): Disabled in favor of market_data.db
        """
        pass
        # try:
        #     data = {
        #         "prices": list(self.raw_prices),
        #         "last_updated": time.time()
        #     }
        #     with open(self.history_file, 'w') as f:
        #         json.dump(data, f)
        # except Exception as e:
        #     pass  # Silent fail, non-critical
        
    def backfill_history(self):
        """Fetch ~24h history from CoinGecko."""
        try:
            if self.is_critical:
                Logger.info(f"   ⏳ Fetching history from CoinGecko (CRITICAL)...")
            else:
                Logger.info(f"   ⏳ Fetching history from CoinGecko (Fast-Fail)...")
                
            prices, volumes = self._fetch_coingecko_history(self.mint)
            
            if prices:
                for price in prices:
                    self.raw_prices.append(price)
                
                # V33.4: Store Volume
                if volumes:
                     for vol in volumes:
                         self.raw_volumes.append(vol)
                else:
                    # Pad default
                    self.raw_volumes.extend([0.0]*len(prices))

                self.current_rsi = self.calculate_rsi()
                self.last_source = "CG"
                Logger.success(f"   ✅ Backfilled {len(prices)} points. Initial RSI: {self.current_rsi}")
                
                # V7.2b: Write back to SharedPriceCache so broker and other engines benefit
                try:
                    from src.core.shared_cache import SharedPriceCache
                    lock = SharedPriceCache._get_lock()
                    with lock:
                        cache_data = SharedPriceCache._read_raw()
                        
                        if self.symbol not in cache_data["prices"]:
                            cache_data["prices"][self.symbol] = {"price": 0, "source": "", "timestamp": 0, "history": []}
                        
                        # Build history array
                        history = [{"price": p, "ts": time.time()} for p in prices[-200:]]
                        cache_data["prices"][self.symbol]["history"] = history
                        cache_data["prices"][self.symbol]["price"] = prices[-1]
                        cache_data["prices"][self.symbol]["source"] = "CG-ENGINE"
                        cache_data["prices"][self.symbol]["timestamp"] = time.time()
                        
                        SharedPriceCache._write_raw(cache_data)
                    Logger.info(f"   📤 Shared {len(prices)} points to broker cache")
                except Exception as e:
                    pass  # Silent fail - sharing is optional
            else:
                Logger.warning(f"   ⚠️ CoinGecko returned no data")
        except Exception as e:
             Logger.error(f"   ⚠️ Backfill Failed: {e}")
        
    def get_last_price(self):
        """Return the last known price without fetching."""
        return self.raw_prices[-1] if self.raw_prices else 0.0

    def fetch_price(self):
        """Fetch price from cache first (WebSocket), fallback to HTTP."""
        from src.core.price_cache import price_cache
        
        # V6.1.1: Cache Priority with configurable timeout
        cache_timeout = getattr(Settings, 'CACHE_TIMEOUT_S', 15)
        
        # 1. Try WebSocket cache first (sub-10ms)
        cached_price = price_cache.get_price(self.mint, max_age_seconds=cache_timeout)
        if cached_price > 0:
            self.update(cached_price, source="WSS")
            return cached_price
        
        # 2. Fallback to HTTP (Jupiter/DexScreener)
        try:
            price, source = self._fetch_jupiter_price(self.mint, Settings.USDC_MINT)
            if price > 0:
                self.update(price, source=source)
                return price
            return self.get_last_price()
        except Exception as e:
            return self.get_last_price()

    def update(self, price: float, source: str = "UNK"):
        """Update internal state with new price."""
        self.raw_prices.append(price)
        # V33.4: Maintain volume sync (Live ticks have no volume)
        self.raw_volumes.append(0.0) 
        self.last_source = source
        self.current_rsi = self.calculate_rsi()
        
        # Virtual Candle Logic
        if self.current_candle['open'] == 0:
            self.current_candle['open'] = price
            self.current_candle['low'] = price
            self.current_candle['high'] = price
            
        self.current_candle['high'] = max(self.current_candle['high'], price)
        self.current_candle['low'] = min(self.current_candle['low'], price)
        self.current_candle['close'] = price
        self.current_candle['ticks'] += 1
        
        # Close Candle (Every 10 secs or 5 ticks for now)
        if self.current_candle['ticks'] >= 5: 
            self.candles.append(self.current_candle.copy())
            self.current_candle = {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'ticks': 0}
            self._save_history()  # Persist on candle close

    def calculate_rsi(self, period=14):
        if len(self.raw_prices) < period + 1: return 50.0
        
        prices = list(self.raw_prices)
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
                
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        # FLATLINE FIX: Prevent RSI 100 on dead markets
        if avg_loss == 0:
            if avg_gain == 0:
                return 50.0  # Completely flat = Neutral
            return 100.0     # Only gains = Overbought
        
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def get_rsi(self):
        return self.current_rsi

    def get_floor_ceiling(self, period=20):
        if len(self.raw_prices) < 20: return None, None
        data = list(self.raw_prices)[-period:]
        return min(data), max(data)
    
    def is_stale_price(self, current_price):
        """Check if price deviates too much from historical average (bad data guard)."""
        if len(self.raw_prices) < 15:
            return True  # Not enough data to validate
        
        # Calculate average of last 50 prices
        recent = list(self.raw_prices)[-50:]
        avg_price = sum(recent) / len(recent)
        
        if avg_price <= 0:
            return True  # No valid average
        
        # Check deviation
        deviation = abs(current_price - avg_price) / avg_price
        if deviation > Settings.MAX_PRICE_DEVIATION:
            return True  # Price too far from average = stale/bad data
        
        return False
    
    def calculate_atr(self, period: int = 14) -> float:
        """
        Calculate Average True Range from virtual candles.
        
        True Range = max(H-L, |H-PC|, |L-PC|)
        ATR = SMA of TR over `period` candles.
        
        Returns 0.0 if insufficient candle data.
        """
        if len(self.candles) < period + 1:
            return 0.0
        
        candles_list = list(self.candles)
        true_ranges = []
        
        for i in range(1, len(candles_list)):
            current = candles_list[i]
            prev_close = candles_list[i - 1]['close']
            
            high = current['high']
            low = current['low']
            
            # True Range: max of 3 values
            tr = max(
                high - low,                    # Current range
                abs(high - prev_close),        # Gap up
                abs(low - prev_close)          # Gap down
            )
            true_ranges.append(tr)
        
        # Use last `period` TRs for ATR (Simple Moving Average)
        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
        
        return sum(true_ranges[-period:]) / period
    
    def get_atr(self, period: int = 14) -> float:
        """Get current ATR value. Alias for calculate_atr()."""
        return self.calculate_atr(period)
