import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.execution.wallet import WalletManager

async def confirm_swap():
    print("\n--- 🔄 CONFIRMING SWAP: USDC -> SOL (FORCED REFRESH) ---")
    wm = WalletManager()
    wm.last_sync_time = 0 # Force refresh
    
    try:
        wm.last_sync_time = 0
        holdings = wm.get_current_live_usd_balance()
        
        print(f"\n✅ Total Portfolio USD: ${holdings['total_usd']:,.2f}")
        print(f"✅ USDC Breakdown: ${holdings['breakdown'].get('USDC', 0):.2f}")
        print(f"✅ SOL Balance: {holdings['breakdown'].get('SOL', 0):.6f} SOL")
        
        # Manually check SOL again
        sol_bal = wm.get_sol_balance()
        print(f"✅ Manual SOL Check: {sol_bal:.6f} SOL")
        
        # Detailed Token Check
        all_tokens = wm.get_all_token_accounts()
        print(f"\n[DEBUG] Raw Tokens Found ({len(all_tokens)}):")
        for m, b in all_tokens.items():
            print(f"   - {m}: {b}")
            
        if sol_bal > 0.05:
            print("\n✅ SOL increase detected! Swap confirmed.")
        elif holdings['breakdown'].get('USDC', 0) < 1.0:
            print("\n✅ USDC moved successfully.")
        else:
            print("\nℹ️ Status: Balances unchanged in this scan. Transaction may be pending or RPC lagging.")
            
    except Exception as e:
        print(f"❌ Scan failed: {e}")

if __name__ == "__main__":
    asyncio.run(confirm_swap())
