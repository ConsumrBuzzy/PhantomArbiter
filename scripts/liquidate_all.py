import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from src.execution.wallet import WalletManager
from src.execution.swapper import JupiterSwapper

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
    # Define tokens to check/liquidate
    HOLDINGS = [
        ("WIF", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),
        ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),
        ("JUP", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYkKedZNsDvCN"),
        ("RAY", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"),
        ("JTO", "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL"),
        ("PYTH", "HZ1JovNiVvGrGNiiYvEozEVGZ58xaU3RKwX8eACQBCt3"),
        ("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"),
        ("DRIFT", "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7"),
        ("KMNO", "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS"),
        ("TNSR", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6"),
        ("RENDER", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof"),
    ]

    for symbol, mint in HOLDINGS:
        balance = wm.get_balance(mint)
        if balance > 0:
            print(f"   found {balance:.4f} {symbol}")

            # Estimates
            # We don't have price, but we assume it's > dust if it's visible
            # Just try to swap ALL to USDC
            print(f"   🔄 Swapping {symbol} -> USDC...")

            try:
                sig = swapper.execute_swap(
                    "SELL", 0, "Liquidation", target_mint=mint, priority_fee=10000
                )
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
