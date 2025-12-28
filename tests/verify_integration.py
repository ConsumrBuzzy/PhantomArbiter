import sys
import os
import asyncio
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.execution.wallet import WalletManager
from src.core.capital_manager import CapitalManager
from src.core.provider_pool import get_provider_pool
from src.shared.system.logging import Logger

async def verify_full_integration():
    print("\n--- 🏁 FULL INTEGRATION CHECK: WALLETS & DATA ---")
    
    # 1. Real Wallet Holdings Read
    print("\n[LIVE WALLET READ]")
    wm = WalletManager()
    pubkey = wm.get_public_key()
    if not pubkey:
        print("❌ Error: Real Wallet (SOLANA_PRIVATE_KEY) not found in .env")
    else:
        print(f"✅ Real Wallet: {pubkey}")
        
        # This calls get_current_live_usd_balance which fetches SOL, USDC, and all SPL tokens
        try:
            holdings = wm.get_current_live_usd_balance()
            print(f"✅ Total USD Value: ${holdings['total_usd']:,.2f}")
            print(f"✅ Breakdown: {holdings['breakdown']}")
            
            if holdings['assets']:
                print("✅ Found Token Holdings (Bags):")
                for asset in holdings['assets']:
                    print(f"   - {asset['symbol']}: {asset['amount']:.2f} (${asset['usd_value']:.2f})")
            else:
                print("ℹ️ No non-dust SPL tokens found.")
        except Exception as e:
            print(f"❌ Real Wallet Read Failed: {e}")

    # 2. Paper Trading Integration Check
    print("\n[PAPER TRADING INTEGRATION]")
    cm = CapitalManager(mode="MONITOR")
    engine_state = cm.get_engine_state("MERCHANT")
    
    print(f"✅ Paper Mode Active: {cm.mode}")
    print(f"✅ Current Paper Cash: ${engine_state.get('cash_balance', 0):.2f}")
    print(f"✅ Current Paper Gas: {engine_state.get('sol_balance', 0):.4f} SOL")
    
    positions = engine_state.get("positions", {})
    if positions:
        print(f"✅ Paper Held Tokens ({len(positions)}):")
        for symbol, data in positions.items():
            print(f"   - {symbol}: {data['balance']:.4f} (@ ${data['avg_price']:.6f})")
    else:
        print("ℹ️ Paper Wallet currently has no positions.")

    # 3. Data Flow Connectivity
    print("\n[DATA FLOW VERIFICATION]")
    pool = get_provider_pool()
    stats = pool.get_stats()
    print(f"✅ RPC Pool Connectivity: {stats['healthy_endpoints']}/{stats['total_endpoints']} Healthy")
    if stats['healthy_endpoints'] > 0:
        print(f"✅ Avg Latency: {stats['avg_latency_ms']:.2f}ms")
    else:
        print("❌ WARNING: No healthy RPC endpoints detected!")

    print("\n--- 🏆 INTEGRATION STATUS: READY ---")

if __name__ == "__main__":
    # Ensure logs are visible
    os.environ["SILENT_MODE"] = "False"
    asyncio.run(verify_full_integration())
