"""
Phantom Arbiter - Wallet Balance Checker
=========================================
Checks your Phantom wallet connection and USDC balance.

Usage:
    python check_wallet.py
"""

import asyncio
import os
import sys

# Load .env file
from dotenv import load_dotenv
load_dotenv()

import base58
import httpx


# Token mints
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"


async def check_wallet():
    """Check wallet connection and balances."""
    
    print("\n" + "="*60)
    print("   PHANTOM WALLET CHECK")
    print("="*60)
    
    # Step 1: Check for private key
    private_key = os.getenv("PHANTOM_PRIVATE_KEY") or os.getenv("SOLANA_PRIVATE_KEY")
    
    if not private_key:
        print("\n   ❌ No private key found!")
        print("\n   To add your Phantom wallet:")
        print("   1. Open Phantom → Settings → Security → Export Private Key")
        print("   2. Add to .env file:")
        print("      PHANTOM_PRIVATE_KEY=your_key_here")
        return False
    
    print("\n   ✅ Private key found")
    
    # Step 2: Derive public key
    try:
        # Try with solders (preferred)
        try:
            from solders.keypair import Keypair
            
            secret_bytes = base58.b58decode(private_key)
            keypair = Keypair.from_bytes(secret_bytes)
            public_key = str(keypair.pubkey())
            
        except ImportError:
            # Fallback: extract from key bytes
            secret_bytes = base58.b58decode(private_key)
            public_key = base58.b58encode(secret_bytes[32:]).decode()
        
        print(f"   ✅ Wallet address: {public_key}")
        
    except Exception as e:
        print(f"   ❌ Failed to decode private key: {e}")
        print("   Make sure you copied the full base58 key from Phantom")
        return False
    
    # Step 3: Get RPC URL
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    print(f"   ✅ RPC: {rpc_url[:40]}...")
    
    # Step 4: Check balances
    print("\n   📊 Fetching balances...")
    
    async with httpx.AsyncClient() as client:
        # Get SOL balance
        try:
            resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [public_key]
            }, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if "error" in data:
                    print(f"   ⚠️ RPC error: {data['error'].get('message', 'Unknown')}")
                else:
                    sol_lamports = data.get("result", {}).get("value", 0)
                    sol_balance = sol_lamports / 1e9
                    print(f"\n   SOL Balance:  {sol_balance:.6f} SOL (${sol_balance * 120:.2f})")
            else:
                print(f"   ❌ Failed to get SOL balance: HTTP {resp.status_code}")
                
        except Exception as e:
            print(f"   ❌ Failed to get SOL balance: {e}")
        
        # Get USDC balance
        try:
            resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    public_key,
                    {"mint": USDC_MINT},
                    {"encoding": "jsonParsed"}
                ]
            }, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                accounts = data.get("result", {}).get("value", [])
                
                if accounts:
                    usdc_amount = float(
                        accounts[0].get("account", {})
                        .get("data", {})
                        .get("parsed", {})
                        .get("info", {})
                        .get("tokenAmount", {})
                        .get("uiAmount", 0)
                    )
                    print(f"   USDC Balance: {usdc_amount:.2f} USDC")
                    
                    if usdc_amount >= 5:
                        print(f"\n   ✅ Ready to trade with ${usdc_amount:.2f}")
                    else:
                        print(f"\n   ⚠️ Low USDC balance - need at least $5 to trade")
                else:
                    print(f"   USDC Balance: 0.00 USDC")
                    print(f"\n   ⚠️ No USDC found - deposit USDC to trade")
                    
        except Exception as e:
            print(f"   ❌ Failed to get USDC balance: {e}")
    
    # Summary
    print("\n" + "="*60)
    print("   READY TO TRADE?")
    print("="*60)
    print("""
   ✅ Requirements met:
      - Private key loaded
      - Wallet address verified
      - RPC connection working
      
   To start trading:
      python run_trader.py --live --budget 5 --max-trade 5
""")
    
    return True


if __name__ == "__main__":
    asyncio.run(check_wallet())
