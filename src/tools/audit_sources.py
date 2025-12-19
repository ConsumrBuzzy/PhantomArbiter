import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config.settings import Settings
from src.core.prices.jupiter import JupiterProvider
from src.core.prices.dexscreener import DexScreenerProvider

def run_audit():
    print("🔍 STARTING PRICE SOURCE AUDIT...")
    print("   Testing connectivity to Jupiter and DexScreener for all configured assets.")
    
    # Initialize Providers
    # Note: Providers might require init arguments? Checked files, no args needed for __init__.
    jupiter = JupiterProvider()
    dexscreener = DexScreenerProvider()
    
    # Collect all mints
    all_assets = {} # symbol -> mint
    
    # Helper to merge dicts
    def add_assets(source_dict):
        for s, m in source_dict.items():
            all_assets[s] = m
            
    add_assets(Settings.ACTIVE_ASSETS)
    add_assets(Settings.VOLATILE_ASSETS)
    add_assets(Settings.WATCH_ASSETS)
    add_assets(Settings.SCOUT_ASSETS)
    
    print(f"   Found {len(all_assets)} unique assets to check.")
    print("=" * 100)
    print(f"{'SYMBOL':<10} | {'MINT':<44} | {'JUPITER':<15} | {'DEXSCREENER':<15}")
    print("-" * 100)
    
    results = []
    
    for symbol, mint in all_assets.items():
        # Test Jupiter
        jup_price = 0.0
        jup_msg = "❌ FAIL"
        try:
            # Using list for single item fetch as per interface
            resp = jupiter.fetch_prices([mint])
            if resp and mint in resp:
                jup_price = resp[mint]
                jup_msg = f"✅ ${jup_price:.6f}"
            else:
                 jup_msg = "❌ NO DATA"
        except Exception as e:
            jup_msg = f"⚠️ ERR"

        # Test DexScreener
        dex_price = 0.0
        dex_msg = "❌ FAIL"
        try:
            resp = dexscreener.fetch_prices([mint])
            if resp and mint in resp:
                dex_price = resp[mint]
                dex_msg = f"✅ ${dex_price:.6f}"
            else:
                dex_msg = "❌ NO DATA"
        except Exception as e:
            dex_msg = f"⚠️ ERR"
            
        print(f"{symbol:<10} | {mint:<44} | {jup_msg:<15} | {dex_msg:<15}")
        
        results.append({
            "symbol": symbol,
            "mint": mint,
            "jupiter": jup_price > 0,
            "dexscreener": dex_price > 0
        })
        
        # Gentle rate limit
        time.sleep(0.1)
        
    print("=" * 100)
    print("📋 RECOMMENDATIONS:")
    
    issues_found = False
    for r in results:
        if not r['jupiter'] and r['dexscreener']:
            print(f"   ⚠️  {r['symbol']} ({r['mint']}): JUPITER FAILED. It works on DexScreener.")
            issues_found = True
        elif not r['jupiter'] and not r['dexscreener']:
            print(f"   🛑 {r['symbol']} ({r['mint']}): BOTH FAILED. Likely invalid mint or dead token.")
            issues_found = True
            
    if not issues_found:
        print("   ✅ All assets appear healthy on at least one provider (Jupiter preferred).")

    print("\n   DONE.")

if __name__ == "__main__":
    run_audit()
