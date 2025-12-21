"""
PHANTOM TRADER SMART SCOUT
Secondary tool to find, validate, and manage tokens.
"""

import argparse
import json
import os
from config.settings import Settings
from src.shared.infrastructure.validator import TokenValidator
from src.strategy.portfolio import PortfolioManager
from src.execution.wallet import WalletManager

class SmartScout:
    def __init__(self):
        self.validator = TokenValidator()
        self.portfolio = PortfolioManager(WalletManager())
        # V9.7: Use data/watchlist.json (unified with settings.py)
        self.assets_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/watchlist.json"))
    
    def scan_candidate(self, symbol, mint):
        """Scan a candidate token and report safety."""
        print(f"🔍 SCANNING: {symbol} ({mint})")
        
        # Check if already blocked
        if symbol in self.portfolio.blocked_assets:
            print(f"   ⛔ {symbol} is currently BLOCKED.")
            return

        result = self.validator.validate(mint, symbol)
        
        if result.is_safe:
            print(f"   ✅ SAFE TO TRADE")
            print(f"      Liquidity: ${result.liquidity_usd:,.0f}")
            print(f"      Top 10: {result.top10_pct*100:.1f}%")
            
            # Prompt to add
            choice = input(f"   Add {symbol} to Watchlist? [y/N] > ").lower()
            if choice == 'y':
                self.add_asset(symbol, mint)
        else:
            print(f"   ❌ UNSAFE: {result.reason}")
            choice = input(f"   Block {symbol} permanently? [y/N] > ").lower()
            if choice == 'y':
                self.portfolio.block_token(symbol)
                print(f"   ⛔ {symbol} added to Blocklist.")

    def add_asset(self, symbol, mint):
        """Add to assets.json."""
        try:
            with open(self.assets_file, 'r') as f:
                data = json.load(f)
            
            data["assets"][symbol] = {
                "mint": mint,
                "category": "WATCH",
                "trading_enabled": False
            }
            
            with open(self.assets_file, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"   ✅ {symbol} added to assets.json (WATCH mode)")
            
        except Exception as e:
            print(f"   ❌ Failed to update assets.json: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gemini Smart Scout')
    parser.add_argument('symbol', help='Token Symbol', nargs='?')
    parser.add_argument('mint', help='Token Mint Address', nargs='?')
    parser.add_argument('--scan-wallet', action='store_true', help='Scan wallet for untracked tokens')
    args = parser.parse_args()
    
    scout = SmartScout()
    
    if args.scan_wallet:
        print("🔍 Scanning wallet for new tokens...")
        # 1. Get Wallet Holdings
        holdings = scout.portfolio.wallet.get_all_token_accounts()
        
        # 2. Load Known Assets
        import json
        with open(scout.assets_file, 'r') as f:
            assets_data = json.load(f).get("assets", {})
        known_mints = {v["mint"]: k for k, v in assets_data.items()}
        
        found_new = False
        for mint, bal in holdings.items():
            if bal > 0.01 and mint not in known_mints:
                # Untracked!
                print(f"   🔭 Found UNTRACKED: {mint[:8]}... Bal: {bal:.4f}")
                # Try to resolve symbol
                symbol = scout.portfolio._fetch_token_symbol(mint) # Use helper from portfolio
                if symbol == "UNKNOWN":
                    symbol = input(f"      ❓ Enter symbol for {mint[:8]}... > ").upper()
                else:
                    print(f"      🌍 Identified as {symbol}")
                
                scout.scan_candidate(symbol, mint)
                found_new = True
                
        if not found_new:
            print("   ✅ No new untracked tokens found.")

    elif args.symbol and args.mint:
        scout.scan_candidate(args.symbol, args.mint)
    else:
        print("Usage: python -m v2.scout <SYMBOL> <MINT> or --scan-wallet")
