import asyncio
import os
import sys
import json
import httpx
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.shared.execution.wallet import WalletManager
from src.shared.execution.swapper import JupiterSwapper
from src.shared.system.logging import Logger
from config.settings import Settings

load_dotenv()
Settings.ENABLE_TRADING = True # Force trading for cleanup
Settings.SILENT_MODE = False   # Show swap progress

async def get_price(mint):
    """Fetch price from Jupiter."""
    try:
        url = f"https://api.jup.ag/price/v2?ids={mint}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return float(data.get("data", {}).get(mint, {}).get("price", 0))
    except:
        pass
    return 0.0

async def main():
    print("\n" + "="*60)
    print("   🚀 PHANTOM ARBITER - SMART SWEEP")
    print("="*60)
    
    wm = WalletManager()
    swapper = JupiterSwapper(wm)
    
    public_key = wm.get_public_key()
    print(f"\n   Wallet: {public_key}")
    
    # 1. Survey SOL and USDC
    sol_bal = wm.get_sol_balance()
    usdc_bal = wm.get_balance(Settings.USDC_MINT)
    
    sol_price = await get_price("So11111111111111111111111111111111111111112")
    if sol_price == 0: sol_price = 140.0 # Fallback
    
    print(f"\n   📊 Primary Balances:")
    print(f"      USDC: ${usdc_bal:.2f}")
    print(f"      SOL:  {sol_bal:.4f} SOL (~${sol_bal * sol_price:.2f})")
    
    # 2. Scan for "Strays"
    print("\n   🔍 Scanning for stray tokens...")
    all_tokens = wm.get_all_token_accounts()
    
    strays = []
    total_stray_usd = 0.0
    
    for mint, amount in all_tokens.items():
        if mint == Settings.USDC_MINT: continue
        
        price = await get_price(mint)
        usd_val = amount * price
        
        if usd_val > 0.01: # Filter absolute dust
            strays.append({
                "mint": mint,
                "amount": amount,
                "usd_val": usd_val
            })
            total_stray_usd += usd_val
            print(f"      Found: {amount:.4f} tokens ({mint[:6]}...) - ${usd_val:.2f}")

    if not strays:
        print("      No stray tokens found.")
    else:
        print(f"\n   Total stray value: ${total_stray_usd:.2f}")
        
    # 3. Decision Logic
    print("\n" + "-"*40)
    
    # A. Sweep strays back to USDC
    for stray in strays:
        if stray['usd_val'] > 0.20: # Worth the gas?
            print(f"   🔄 Swapping {stray['mint'][:6]}... -> USDC (${stray['usd_val']:.2f})")
            # We use SELL mode which sells the token_mint to USDC
            result = swapper.execute_swap(
                direction="SELL", 
                amount_usd=0, # 0 means sell all
                reason="SWEEP", 
                target_mint=stray['mint']
            )
            if result and result.get('success'):
                print(f"      ✅ Success: {result['signature'][:16]}...")
            else:
                print(f"      ❌ Failed: {result.get('error', 'Unknown') if result else 'No result'}")

    # B. Balance SOL (Target ~0.1 SOL)
    target_sol = 0.1
    if sol_bal > (target_sol + 0.05):
        surplus_sol = sol_bal - target_sol
        surplus_usd = surplus_sol * sol_price
        if surplus_usd > 5.0:
            print(f"   🔄 High SOL detected. Swapping {surplus_sol:.4f} SOL surplus to USDC...")
            # Selling SOL (target_mint) to USDC
            result = swapper.execute_swap(
                direction="SELL", 
                amount_usd=surplus_usd,
                reason="BALANCE_SOL",
                target_mint="So11111111111111111111111111111111111111112",
                override_atomic_amount=int(surplus_sol * 1_000_000_000)
            )
            if result and result.get('success'):
                print(f"      ✅ Success: {result['signature'][:16]}...")
            else:
                 print(f"      ❌ Failed: {result.get('error', 'Unknown') if result else 'No result'}")
    
    elif sol_bal < 0.05:
        refill_usd = 10.0
        print(f"   🔄 Low SOL detected. Swapping ${refill_usd} USDC to SOL for gas...")
        # Buying SOL (target_mint) from USDC
        result = swapper.execute_swap(
            direction="BUY",
            amount_usd=refill_usd,
            reason="REFILL_GAS",
            target_mint="So11111111111111111111111111111111111111112"
        )
        if result and result.get('success'):
            print(f"      ✅ Success: {result['signature'][:16]}...")

    print("\n✨ Wallet cleanup complete.")
    print("="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
