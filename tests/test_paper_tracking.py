import sys
import os
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.capital_manager import CapitalManager

async def test_paper_tracking():
    print("\n--- 🧪 PAPER TRACKING TEST ---")
    cm = CapitalManager(mode="MONITOR")
    
    # Simulate a buy of 'WIF'
    symbol = "WIF"
    mint = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    price = 3.50
    size_usd = 10.0
    
    print(f"Executing simulated Paper BUY for ${size_usd} of {symbol}...")
    success, msg = cm.execute_buy(
        engine_name="MERCHANT",
        symbol=symbol,
        mint=mint,
        price=price,
        size_usd=size_usd
    )
    
    if success:
        print(f"✅ {msg}")
        
        # Verify tracking
        engine_state = cm.get_engine_state("MERCHANT")
        positions = engine_state.get("positions", {})
        
        if symbol in positions:
            pos = positions[symbol]
            print(f"✅ Position Tracked: {pos['balance']:.4f} {symbol}")
            print(f"✅ Entry Time: {pos['entry_time']}")
            print(f"✅ Remaining Cash: ${engine_state['cash_balance']:.2f}")
            print(f"✅ Remaining Gas: {engine_state['sol_balance']:.4f} SOL")
        else:
            print(f"❌ Position for {symbol} NOT found in state!")
    else:
        print(f"❌ BUY Failed: {msg}")

if __name__ == "__main__":
    asyncio.run(test_paper_tracking())
