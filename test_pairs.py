import sys
import os
import time

# Add src to path
sys.path.append(os.getcwd())

from src.arbiter.core.spread_detector import SpreadDetector
from src.arbiter.arbiter import POD_OG_B, _build_pairs_from_pods
from src.arbiter.core.feeds.jupiter_feed import JupiterFeed
from src.arbiter.core.feeds.raydium_feed import RaydiumFeed
# from src.arbiter.core.feeds.orchestrator_feed import OrchestratorFeed # Optional

def test_og_b():
# ...
    # 2. Initialize Detector
    print("\n[+] Initializing SpreadDetector with Feeds...")
    try:
        feeds = [JupiterFeed(), RaydiumFeed()]
        detector = SpreadDetector(feeds=feeds)
        print("    Detector initialized with Jupiter & Raydium.")
    except Exception as e:
        print(f"    ❌ Failed to init detector: {e}")
        return

    # 3. Scan Pairs
    print("\n[+] Scanning Pairs (via scan_all_pairs)...")
    start = time.time()
    
    # scan_all_pairs fetches prices internally
    opps = detector.scan_all_pairs(pairs, trade_size=100)
    
    duration = time.time() - start
    print(f"    Done in {duration:.2f}s")
    
    # 4. Results
    print(f"\n[+] Found {len(opps)} opportunities:")
    for opp in opps:
        print(f"    ✅ {opp.pair:<12}: Spread {opp.spread_pct:.2f}% | Net ${opp.net_profit_usd:.4f}")

    if not opps:
        print("\n❌ NO OPPORTUNITIES FOUND.")
        print("    If scan completed quickly, price fetch might have failed completely.")
        print("    Checking feeds...")
        for name, feed in detector.feeds.items():
            print(f"    - Feed: {name} ({feed.__class__.__name__})")
            
        # Try to manually fetch one price from Jupiter Feed if possible
        # Assuming we can access feed methods
        try:
             first_pair = pairs[0]
             base_mint = first_pair[1]
             print(f"\n    Attempting manual Jupiter fetch for {first_pair[0]} ({base_mint})...")
             if 'jupiter' in detector.feeds:
                 jup = detector.feeds['jupiter']
                 # Check if get_price exists
                 if hasattr(jup, 'get_price'):
                     p = jup.get_price(base_mint)
                     print(f"    Jupiter Price: {p}")
                 else:
                     print("    Jupiter feed has no get_price method")
        except Exception as e:
            print(f"    Manual check failed: {e}")

if __name__ == "__main__":
    test_og_b()
