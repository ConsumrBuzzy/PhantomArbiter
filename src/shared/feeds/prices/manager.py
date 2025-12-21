import time
from src.system.logging import Logger
from .jupiter import JupiterProvider
from .dexscreener import DexScreenerProvider

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

class PriceManager:
    """
    Orchestrates price fetching from multiple providers.
    Uses Circuit Breaker to manage primary provider health.
    """
    def __init__(self):
        self.jupiter = JupiterProvider()
        self.dexscreener = DexScreenerProvider()
        self.circuit = CircuitBreaker()
        
    def fetch_batch(self, mints: list) -> dict:
        """
        Fetch prices for a batch of mints.
        Automatically handles failover between Jupiter and DexScreener.
        """
        if not mints: return {}
        
        results = {}
        missing_mints = set(mints)
        
        # 1. Try Primary (Jupiter)
        if self.circuit.can_try_primary():
            try:
                # We attempt to fetch all. Jupiter handler does chunking internally.
                # However, for the circuit breaker to be accurate per-request, 
                # we might want to capture if *any* chunk failed?
                # The current provider implementation returns partial results.
                # We rely on specific failure signals.
                
                # To invoke circuit breaker correctly, we need to know if it 'failed'.
                # But fetch_prices returns a dict. 
                # Let's assess failure by coverage? No, tokens might just be missing.
                # We need the provider to raise or return success/fail status?
                # For now, let's treat the Jupiter Provider as robust-ish and rely on its internal retries.
                # If we want the circuit breaker to trip on HTTP errors, the provider should propagate them 
                # or we track them here.
                
                # Simplified: Data integrity check?
                # If Jupiter returns empty dict for a known good list?
                # Actually, implementing strict HTTP error propagation is better.
                # But to keep it simple and match previous logic:
                # Previous logic recorded failure if chunk failed.
                
                # Let's just run it. If it throws exception, we record failure.
                jp_prices = self.jupiter.fetch_prices(list(missing_mints))
                if jp_prices:
                    for m, p in jp_prices.items():
                        results[m] = {'price': p, 'source': 'Jupiter'}
                    missing_mints -= set(jp_prices.keys())
                    self.circuit.record_success()
                else:
                    # Empty result *might* be failure if we asked for many tokens.
                    # Or it might be just bad tokens.
                    # Let's assume neutral unless exception?
                    pass

            except Exception as e:
                Logger.warning(f"      ⚠️ Jupiter Batch Error: {e}")
                self.circuit.record_failure()
        
        # 2. Fallback to DexScreener (For any missing)
        # If circuit is open, we come straight here.
        if missing_mints:
            if self.circuit.is_open:
                 # Silent switch
                 pass
            elif len(missing_mints) == len(mints):
                 # We tried Jupiter and got nothing/failed
                 pass
            
            # If we have missing mints, try DexScreener
            ds_prices = self.dexscreener.fetch_prices(list(missing_mints))
            if ds_prices:
                for m, p in ds_prices.items():
                    results[m] = {'price': p, 'source': 'DexScreener'}
                
        return results

# Global Instance
PRICE_MANAGER = PriceManager()
