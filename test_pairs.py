import sys
import os
import time

# Add src to path
sys.path.append(os.getcwd())

from src.arbiter.arbiter import POD_OG_B, _build_pairs_from_pods
from src.arbiter.core.spread_detector import SpreadDetector

def test_og_b():
    print("="*60)
    print("🔍 PAIR TESTER: OG_B POD")
    print("="*60)
    
    # 1. Build Pairs
    pairs = _build_pairs_from_pods([POD_OG_B])
    print(f"Generated {len(pairs)} pairs to scan:")
    for i, p in enumerate(pairs):
        print(f"  {i+1}. {p[0]} (Base: {p[1][:4]}... Quote: {p[2][:4]}...)")
    
    # 2. Initialize Detector
    print("\n[+] Initializing SpreadDetector...")
    try:
        detector = SpreadDetector()
        print("    Detector initialized.")
    except Exception as e:
        print(f"    ❌ Failed to init detector: {e}")
        return

    # 3. Update Prices
    print("\n[+] Fetching Prices (3s timeout)...")
    start = time.time()
    detector.update_prices()
    duration = time.time() - start
    print(f"    Done in {duration:.2f}s")
    
    # 4. Check Raw Prices
    print("\n[+] Checking Raw Feed Data:")
    
    found_any = False
    for p in pairs:
        base = p[1]
        quote = p[2] # USDC or SOL
        pair_name = p[0]
        
        # Check if base is in any feed
        present_in = []
        for feed_name, feed in detector.feeds.items():
            # How to check cache? 
            # SpreadDetector doesn't expose cache directly, 
            # but get_prices_for_pair uses self.latest_prices or feed.get_price logic?
            # Actually scan_all_pairs calls get_prices_for_pair
            pass
            
        # Call get_prices_for_pair
        prices = detector.get_prices_for_pair(base, "USDC" if "USDC" in pair_name else "SOL")
        
        if prices:
            found_any = True
            print(f"    ✅ {pair_name:<12}: Found {len(prices)} sources")
            for src, price in prices.items():
                print(f"       - {src:<10}: ${price:.6f}")
        else:
            print(f"    ❌ {pair_name:<12}: NO PRICES FOUND")
            
    if not found_any:
        print("\n❌ CRITICAL: No prices found for ANY pair in OG_B.")
        print("   Possible causes:")
        print("   1. Tokens not indexed by Jupiter/Raydium yet.")
        print("   2. API Rate limits or blocks.")
        print("   3. Network connectivity issues.")
    else:
        print("\n✅ Scan complete. If you see prices above, the bot should work.")

if __name__ == "__main__":
    test_og_b()
