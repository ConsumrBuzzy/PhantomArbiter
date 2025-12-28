import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.execution.wallet import WalletManager
from src.core.capital_manager import CapitalManager
from config.settings import Settings

async def test_wallet_check():
    print("--- Wallet & Budget Verification ---")
    
    # 1. Real Wallet Check
    wm = WalletManager()
    pubkey = wm.get_public_key()
    if pubkey:
        print(f"✓ Real Wallet Loaded: {pubkey}")
    else:
        print("✗ Real Wallet Not Loaded (Check .env)")

    # 2. Paper Wallet / Capital Manager Check
    # Wipe state for clean test if exists
    if os.path.exists(CapitalManager.STATE_FILE):
        os.remove(CapitalManager.STATE_FILE)
    
    cm = CapitalManager(default_capital=50.0, mode="MONITOR")
    engine_state = cm.get_engine_state("MERCHANT")
    
    cash = engine_state.get("cash_balance", 0)
    sol = engine_state.get("sol_balance", 0)
    
    print(f"Paper Balance: ${cash:.2f}")
    if abs(cash - 50.0) < 0.01:
        print("✓ Paper Budget Set to $50")
    else:
        print(f"✗ Paper Budget Error: {cash}")
        
    print(f"Paper Gas: {sol:.4f} SOL")
    if sol >= 0.06:
        print("✓ Paper Gas Floor Set to ~$10")
    else:
        print(f"✗ Paper Gas Error: {sol}")

    # 3. Settings Check
    print(f"Settings Gas Floor: {Settings.GAS_FLOOR_SOL} SOL")
    if Settings.GAS_FLOOR_SOL == 0.06:
         print("✓ Settings Gas Floor Verified")

if __name__ == "__main__":
    asyncio.run(test_wallet_check())
