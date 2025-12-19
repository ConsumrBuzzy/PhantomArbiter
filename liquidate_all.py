
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from src.execution.wallet import WalletManager
from src.execution.swapper import JupiterSwapper
from src.system.logging import Logger

# Load Env
load_dotenv()

async def main():
    print("🧹 Starting Portfolio Liquidator...")
    
    # Setup
    wm = WalletManager()
    swapper = JupiterSwapper(wm)
    
    # 1. Check Holdings
    print("\n🔍 Scanning Portfolio...")
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    holdings = [
        ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),
        ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),
        ("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"),
    ]
    
    for symbol, mint in holdings:
        balance = wm.get_balance(mint)
        if balance > 0:
            print(f"   found {balance:.4f} {symbol}")
            
            # Estimates
            # We don't have price, but we assume it's > dust if it's visible
            # Just try to swap ALL to USDC
            print(f"   🔄 Swapping {symbol} -> USDC...")
            
            try:
                sig = swapper.execute_swap("SELL", 0, "Liquidation", target_mint=mint, priority_fee=10000)
                if sig:
                    print(f"   ✅ Liquidated: {sig}")
                else:
                    print(f"   ❌ Failed to sell {symbol}")
            except Exception as e:
                print(f"   ❌ Error: {e}")
                
        else:
            print(f"   {symbol}: Empty")
            
    print("\n✨ Done. Check USDC Balance.")

if __name__ == "__main__":
    asyncio.run(main())
