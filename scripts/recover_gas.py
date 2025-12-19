import asyncio
import os
import sys

# Load env before imports
from dotenv import load_dotenv
load_dotenv()

from config.settings import Settings
from src.execution.wallet import WalletManager
from src.execution.swapper import JupiterSwapper

async def recover_gas():
    print("\n🚨 EMERGENCY GAS RECOVERY 🚨")
    print("============================")
    
    # Force settings
    Settings.ENABLE_TRADING = True
    
    # 1. Load Wallet
    manager = WalletManager()
    if not manager.keypair:
        print("❌ No private key found in .env!")
        return
        
    pubkey = manager.get_public_key()
    print(f"🔑 Wallet: {pubkey}")
    
    sol_balance = manager.get_sol_balance()
    print(f"⛽ Current Gas: {sol_balance:.6f} SOL")
    
    # 2. Check BONK Balance
    BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    bonk_balance = manager.get_balance(BONK_MINT)
    print(f"🐕 BONK Balance: {bonk_balance:,.2f}")
    
    if bonk_balance < 1000:
        print("❌ Not enough BONK to swap.")
        return

    # 3. Swap ALL BONK for SOL
    print(f"\n🚀 Attempting to swap {bonk_balance:,.2f} BONK -> SOL...")
    
    swapper = JupiterSwapper(manager)
    
    # JupiterSwapper expects amount in USD usually, but let's check execute_swap
    # It takes amount_usd. We need to cheat and use the atomic amount logic or just guess price.
    # Actually, WalletManager has get_balance returns token amount. 
    # Swapper calculates atomic: amount_atomic = int(amount_usd * 1_000_000) for BUY
    # For SELL, it does: token_bal = self.wallet.get_balance(mint); amount_atomic = int(token_bal * 1_000_000) ???
    # Wait, swapper.py line 71: amount_atomic = int(token_bal * 1_000_000) - THIS IS WRONG for BONK (5 decimals) vs USDC (6)
    # JupiterSwapper seems hardcoded for USDC logic or needs checking.
    
    # Let's inspect swapper.py logic again to be safe before running.
    # But to be fast, let's just use the SmartRouter directly which gives us full control.
    
    from src.system.smart_router import SmartRouter
    router = SmartRouter()
    
    # BONK is 5 decimals
    amount_atomic = int(bonk_balance * 10**5) 
    
    quote = router.get_jupiter_quote(
        input_mint=BONK_MINT,
        output_mint=SOL_MINT,
        amount=amount_atomic,
        slippage_bps=200 # 2% slippage
    )
    
    if not quote:
        print("❌ Failed to get quote from Jupiter.")
        return
        
    print(f"✅ Quote received! Est. Output: {int(quote['outAmount']) / 10**9:.6f} SOL")
    
    payload = {
        "quoteResponse": quote,
        "userPublicKey": pubkey,
        "wrapAndUnwrapSol": True
    }
    
    swap_data = router.get_swap_transaction(payload)
    if not swap_data:
        print("❌ Failed to get swap transaction.")
        return
        
    import base64
    from solders.transaction import VersionedTransaction
    from solana.rpc.commitment import Confirmed
    from solana.rpc.types import TxOpts
    
    raw_tx = base64.b64decode(swap_data["swapTransaction"])
    tx = VersionedTransaction.from_bytes(raw_tx)
    signed_tx = VersionedTransaction(tx.message, [manager.keypair])
    
    print("🚀 Sending transaction...")
    try:
        # Use simple RPC call to avoid complex pool logic for recovery script
        import requests
        rpc_url = "https://api.mainnet-beta.solana.com"
        
        from solana.rpc.api import Client
        client = Client(rpc_url)
        
        # Send
        result = client.send_transaction(signed_tx, opts=TxOpts(skip_preflight=True))
        print(f"✅ Transaction Sent! Sig: {result.value}")
        print("PLEASE WAIT 30 SECONDS FOR CONFIRMATION...")
        
    except Exception as e:
        print(f"❌ Send failed: {e}")

if __name__ == "__main__":
    asyncio.run(recover_gas())
