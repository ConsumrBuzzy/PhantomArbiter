"""
Status Reporter Tool
====================
Standalone tool to display current bot state (Portfolio, Positions, Prices).
Replaces legacy BotEngine display logic.
"""

from datetime import datetime
from config.settings import Settings
from src.core.shared_cache import SharedPriceCache
from src.tools.asset_manager import AssetManager
from src.shared.execution.wallet import WalletManager

class StatusReporter:
    def __init__(self):
        self.wallet = WalletManager()
        self.asset_manager = AssetManager()
        
    def report(self):
        """Print full status report."""
        print("\n🔎 PHANTOM TRADER STATUS REPORT")
        print("=" * 60)
        
        # 1. Wallet State
        sol_balance = self.wallet.get_sol_balance()
        usdc_balance = self.wallet.get_balance(Settings.USDC_MINT)
        
        # Get cached wallet state to see held bags
        wallet_state = SharedPriceCache.get_wallet_state(max_age=300)
        held_assets = wallet_state.get("held_assets", {})
        
        # 2. Asset Prices
        print(f"💰 WALLET: ${usdc_balance:.2f} USDC | {sol_balance:.4f} SOL")
        
        # 3. Positions
        total_value = usdc_balance
        if held_assets:
            print("\n💼 POSITIONS:")
            for symbol, data in held_assets.items():
                balance = data.get("balance", 0)
                val = data.get("value_usd", 0)
                total_value += val
                
                # Get current price
                price, _ = SharedPriceCache.get_price(symbol, max_age=600)
                price_str = f"${price:.4f}" if price else "???"
                
                print(f"   • {symbol}: {balance:.4f} tokens @ {price_str} = ${val:.2f}")
        else:
             print("\n   (No positions held)")

        print("-" * 60)
        print(f"📊 TOTAL EQUITY: ${total_value:.2f}")
        print("=" * 60)
        
        # 4. Watchlist Snapshot
        print("\n👀 WATCHLIST SNAPSHOT:")
        active = Settings.ACTIVE_ASSETS
        scout = Settings.SCOUT_ASSETS
        
        # Get all prices batch
        print(f"   Fetching prices for {len(active)} active assets...")
        
        for symbol in list(active.keys())[:5]: # Show top 5 active
            price, src = SharedPriceCache.get_price(symbol, max_age=3600)
            p_str = f"${price:.4f}" if price else "Wait..."
            print(f"   [A] {symbol}: {p_str}")
            
        print("   ...")
        print("✅ Report Complete")
