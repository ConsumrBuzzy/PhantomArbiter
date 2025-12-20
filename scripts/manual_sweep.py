"""
Manual Token Sweeper - Sell specific tokens to USDC
====================================================
Usage: python scripts/manual_sweep.py

Sells predefined stray tokens that smart_sweep.py might miss.
"""

import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from src.shared.system.logging import Logger
from config.settings import Settings

load_dotenv()
Settings.ENABLE_TRADING = True
Settings.SILENT_MODE = False

# ═══════════════════════════════════════════════════════════════════
# STRAY TOKENS TO SELL (Add mint addresses here)
# ═══════════════════════════════════════════════════════════════════
STRAY_TOKENS = [
    # (Symbol, Mint Address)
    ("PIPPIN", "Dfh5DzRgSvvCFDoYc2ciTkMrbDfRKybA4SoFbPmApump"),
    ("TNSR", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6"),
    # Add more tokens below as needed:
    # ("CASH", "...mint address..."),
]

async def get_price(mint: str) -> float:
    """Fetch price from Jupiter."""
    try:
        url = f"https://api.jup.ag/price/v2?ids={mint}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get("data", {}).get(mint, {}).get("price", 0))
    except Exception as e:
        print(f"   ⚠️ Price fetch failed: {e}")
    return 0.0


async def main():
    print("\n" + "="*60)
    print("   🧹 MANUAL TOKEN SWEEPER")
    print("="*60)
    
    wm = WalletManager()
    if not wm.keypair:
        print("   ❌ No wallet loaded. Check PHANTOM_PRIVATE_KEY in .env")
        return
    
    swapper = JupiterSwapper(wm)
    public_key = wm.get_public_key()
    print(f"\n   Wallet: {public_key}")
    
    # Show current balances
    sol_bal = wm.get_sol_balance()
    usdc_bal = wm.get_balance(Settings.USDC_MINT)
    print(f"   SOL:  {sol_bal:.4f}")
    print(f"   USDC: ${usdc_bal:.2f}")
    
    print("\n" + "-"*40)
    print("   Checking stray tokens...")
    
    sold_count = 0
    total_recovered = 0.0
    
    for symbol, mint in STRAY_TOKENS:
        info = wm.get_token_info(mint)
        
        if not info:
            print(f"   ⏭️  {symbol}: No balance (skip)")
            continue
        
        ui_amount = float(info.get("uiAmount", 0))
        
        if ui_amount <= 0:
            print(f"   ⏭️  {symbol}: Zero balance (skip)")
            continue
        
        # Get price
        price = await get_price(mint)
        usd_value = ui_amount * price if price > 0 else 0
        
        print(f"\n   📦 Found {symbol}:")
        print(f"      Amount:  {ui_amount:.6f}")
        print(f"      Price:   ${price:.8f}")
        print(f"      Value:   ${usd_value:.4f}")
        
        # Force sell regardless of value (user explicitly requested cleanup)
        if ui_amount <= 0:
            print(f"      ⏭️  Zero amount, skipping")
            continue
        
        # Execute sell
        print(f"      🔄 Selling {symbol} → USDC...")
        result = swapper.execute_swap(
            direction="SELL",
            amount_usd=0,  # 0 = sell entire balance
            reason="SWEEP",
            target_mint=mint
        )
        
        if result and result.get("success"):
            sig = result.get("signature", "")[:16]
            print(f"      ✅ Success: {sig}...")
            sold_count += 1
            total_recovered += usd_value
        else:
            error = result.get("error", "Unknown") if result else "No result"
            print(f"      ❌ Failed: {error}")
        
        # Rate limit
        await asyncio.sleep(1.0)
    
    print("\n" + "-"*40)
    print(f"   📊 Summary:")
    print(f"      Tokens sold:     {sold_count}")
    print(f"      Est. recovered:  ${total_recovered:.2f}")
    
    # Show new balances
    sol_bal = wm.get_sol_balance()
    usdc_bal = wm.get_balance(Settings.USDC_MINT)
    print(f"\n   New USDC: ${usdc_bal:.2f}")
    print(f"   SOL:      {sol_bal:.4f}")
    
    print("\n" + "="*60)
    print("   ✨ Sweep complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
