"""
Diagnostic script to verify batch price fetching across all feeds.
"""
import sys
import time
sys.path.insert(0, '.')

from src.shared.system.logging import Logger
Logger.set_silent(False)

from src.shared.feeds.jupiter_feed import JupiterFeed
from src.shared.feeds.raydium_feed import RaydiumFeed
from src.shared.feeds.orca_feed import OrcaFeed

# Sample trending mints to test
TEST_MINTS = [
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",  # DRIFT
    "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS",   # KMNO
    "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6",  # TNSR
]

def test_feed(name, feed):
    print(f"\n--- Testing {name} ---")
    
    # Test batch fetch
    start = time.time()
    prices = feed.get_multiple_prices(TEST_MINTS)
    elapsed = time.time() - start
    
    print(f"   Batch Fetch: {len(prices)} / {len(TEST_MINTS)} prices in {elapsed:.2f}s")
    
    for mint, price in list(prices.items())[:3]:
        symbol = mint[:8]
        print(f"      {symbol}...: ${price:.6f}")
    
    return len(prices)

if __name__ == "__main__":
    print("PRICE FEED DIAGNOSTICS")
    print("=" * 50)
    
    results = {}
    
    # Test Jupiter
    jupiter = JupiterFeed()
    results['JUPITER'] = test_feed("JUPITER", jupiter)
    
    # Test Raydium
    raydium = RaydiumFeed()
    results['RAYDIUM'] = test_feed("RAYDIUM", raydium)
    
    # Test Orca
    orca = OrcaFeed(use_on_chain=False)
    results['ORCA'] = test_feed("ORCA", orca)
    
    print("\n" + "=" * 50)
    print("SUMMARY:")
    for name, count in results.items():
        status = "OK" if count > 0 else "FAIL"
        print(f"   {name}: {count}/{len(TEST_MINTS)} [{status}]")
