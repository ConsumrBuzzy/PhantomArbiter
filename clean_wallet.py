"""
Wallet Cleaner - Sell all non-USDC tokens back to USDC
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from config.settings import Settings

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def main():
    print("=" * 50)
    print("🧹 WALLET CLEANER")
    print("=" * 50)
    
    # Enable live trading
    Settings.ENABLE_TRADING = True
    
    wallet = WalletManager()
    if not wallet.keypair:
        print("❌ No wallet key loaded!")
        return
    
    print(f"✅ Wallet: {str(wallet.get_public_key())[:16]}...")
    
    # Get all token accounts
    tokens = wallet.get_all_token_accounts()
    print(f"📦 Found {len(tokens)} token accounts")
    
    # Filter to non-USDC with balance
    to_clean = []
    for mint, balance in tokens.items():
        if mint == USDC_MINT:
            print(f"   💵 USDC: ${balance / 1e6:.2f}")
            continue
        if balance > 0:
            # Try to get symbol
            symbol = "?"
            for k, v in getattr(Settings, 'ASSETS', {}).items():
                if v == mint:
                    symbol = k
                    break
            to_clean.append((mint, balance, symbol))
            print(f"   🪙 {symbol}: {balance} ({mint[:12]}...)")
    
    if not to_clean:
        print("\n✨ Wallet is clean! No tokens to sell.")
        return
    
    print(f"\n🗑️ {len(to_clean)} tokens to clean")
    confirm = input("Continue? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("Aborted.")
        return
    
    swapper = JupiterSwapper(wallet)
    
    for mint, balance, symbol in to_clean:
        print(f"\n🔄 Selling {symbol}...")
        try:
            result = swapper.execute_swap(
                direction="SELL",
                amount_usd=0,  # 0 = sell all
                reason="CLEAN",
                target_mint=mint,
                priority_fee=100000
            )
            if result and result.get('success'):
                print(f"   ✅ Sold {symbol}")
            else:
                print(f"   ❌ Failed to sell {symbol}: {result.get('error') if result else 'Unknown'}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    main()
