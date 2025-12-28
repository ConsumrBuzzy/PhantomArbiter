import sys
import os
import asyncio
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.execution.wallet import WalletManager
from src.shared.infrastructure.token_registry import get_registry
from src.core.shared_cache import SharedPriceCache

async def run_final_audit():
    print("\n" + "="*50)
    print("🏁 FINAL WALLET AUDIT (TOKEN RECOGNITION SYSTEM)")
    print("="*50)
    
    wm = WalletManager()
    registry = get_registry()
    
    # 1. Force Refresh Holdings
    wm.last_sync_time = 0
    holdings = wm.get_current_live_usd_balance()
    
    print(f"\n✅ Total Portfolio USD: ${holdings['total_usd']:,.2f}")
    print(f"✅ SOL Balance: {holdings['breakdown'].get('SOL', 0):.6f} SOL")
    print(f"✅ USDC Balance: ${holdings['breakdown'].get('USDC', 0):.2f}")
    
    # 2. Deep Dive Discovery
    print("\n🔍 DISCOVERING ALL HELD ASSETS (BAGS)...")
    all_tokens = wm.get_all_token_accounts()
    
    found_any = False
    for mint, amount in all_tokens.items():
        # Identify using the "Strong Token Recognition System"
        symbol, confidence, source = registry.get_symbol_with_confidence(mint)
        
        # Get price if available
        # V300: Let's try to get a live price from Registry's batch if not in cache
        price = 0.0
        try:
            from src.core.shared_cache import get_cached_price
            price, _ = get_cached_price(symbol)
            if not price:
                # Fallback to a quick DexScreener lookup via Registry if needed?
                # For this script we just want to IDENTIFY the bags.
                pass
        except: pass
        
        usd_val = amount * price if price else 0.0
        
        print(f"   [+] {symbol:8} | {amount:>15.4f} | {mint[:12]}... | Conf: {confidence:.1f} ({source})")
        found_any = True
        
    if not found_any:
        print("   ℹ️ No token accounts found.")
    
    print("\n" + "="*50)
    print("🏆 STATUS: AUDIT COMPLETE")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_final_audit())
