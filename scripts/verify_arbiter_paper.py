
import sys
import os
sys.path.append(os.getcwd())

import asyncio
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.shared.execution.paper_wallet import PaperWallet
from config.settings import Settings

async def main():
    print("🧪 Verifying Arbiter Paper Wallet Integration...")
    
    # Setup config
    config = ArbiterConfig(
        budget=100.0,
        live_mode=False
    )
    
    # Initialize Arbiter
    arbiter = PhantomArbiter(config)
    
    # Check 1: PaperWallet initialization
    if isinstance(arbiter.paper_wallet, PaperWallet):
        print("✅ PaperWallet initialized correctly.")
    else:
        print(f"❌ PaperWallet Missing or Invalid: {type(arbiter.paper_wallet)}")
        return

    # Check 2: Tracker removal
    if arbiter.tracker is None:
        print("✅ TradeTracker is None (Correctly removed).")
    else:
        print("❌ TradeTracker still present!")
        return
        
    # Check 3: Property Delegation
    try:
        balance = arbiter.current_balance
        print(f"💰 Current Balance from Property: ${balance:.2f}")
        
        # Verify it matches wallet
        if abs(balance - arbiter.paper_wallet.cash) < 0.01:
            print("✅ Property delegation works (Matches PaperWallet).")
        else:
            print(f"❌ Mismatch! Property: {balance}, Wallet: {arbiter.paper_wallet.cash}")
            
    except Exception as e:
        print(f"❌ Property verification failed: {e}")

    # Check 4: Engine Initialization
    arbiter._setup_paper_mode() # Setup executor
    # Try to init engine
    from src.arbiter.core.arbiter_engine import ArbiterEngine
    try:
        # Simulate run setup logic
        wallet = arbiter.paper_wallet
        engine = ArbiterEngine(arbiter, wallet)
        print("✅ ArbiterEngine initialized successfully with PaperWallet.")
    except Exception as e:
         print(f"❌ ArbiterEngine init failed: {e}")
         
    print("\n🎉 Verification Complete!")

if __name__ == "__main__":
    asyncio.run(main())
