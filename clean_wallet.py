"""
Direct Wallet Cleaner - Uses Jupiter API directly
"""
import asyncio
import os
import sys
import base64
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Use proper Jupiter endpoints
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "")
JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"

def get_keypair():
    pk = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk:
        return None
    return Keypair.from_base58_string(pk)

def get_quote(input_mint, output_mint, amount, slippage=100):
    headers = {}
    if JUPITER_API_KEY:
        headers["x-api-key"] = JUPITER_API_KEY
    
    resp = requests.get(JUPITER_QUOTE_URL, params={
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": slippage
    }, headers=headers, timeout=10)
    
    if resp.status_code == 200:
        return resp.json()
    print(f"   Quote error ({resp.status_code}): {resp.text[:100]}")
    return None

def get_swap_tx(quote, user_pubkey):
    headers = {"Content-Type": "application/json"}
    if JUPITER_API_KEY:
        headers["x-api-key"] = JUPITER_API_KEY
    
    resp = requests.post(JUPITER_SWAP_URL, json={
        "quoteResponse": quote,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": 100000
    }, headers=headers, timeout=10)
    
    if resp.status_code == 200:
        return resp.json()
    print(f"   Swap error ({resp.status_code}): {resp.text[:100]}")
    return None

def send_tx(signed_tx_b64, rpc_url):
    resp = requests.post(rpc_url, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [signed_tx_b64, {"encoding": "base64", "skipPreflight": False}]
    }, timeout=10)
    
    if resp.status_code == 200:
        result = resp.json()
        if "error" in result:
            print(f"   RPC error: {result['error']}")
            return None
        return result.get("result")
    print(f"   RPC error ({resp.status_code}): {resp.text[:100]}")
    return None

def main():
    print("=" * 50)
    print("🧹 DIRECT WALLET CLEANER")
    print("=" * 50)
    
    keypair = get_keypair()
    if not keypair:
        print("❌ No wallet key loaded!")
        return
    
    pubkey = str(keypair.pubkey())
    print(f"✅ Wallet: {pubkey[:16]}...")
    print(f"🔑 Jupiter API Key: {'SET' if JUPITER_API_KEY else 'MISSING'}")
    
    rpc_url = os.getenv("HELIUS_RPC_URL") or "https://api.mainnet-beta.solana.com"
    print(f"🌐 RPC: {rpc_url[:30]}...")
    
    # All tokens to clean (from wallet scan)
    tokens_to_clean = [
        # ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 473254072, "JUP"),  # Already cleaned
        ("E7d9wpesUUzVc4s7B9wpQnbf4xQeJeqEhD4Sh3Q39k6Z", 12000000, "E7d9"),  # 12 tokens (assuming 6 decimals)
        ("TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6", 2205, "TNSR"),  # 0.002 (9 decimals)
        ("6YUoZeiMfNhpDxbj9D3rMrDkP5H9wDEJv5fkCLfYfFCk", 10000000, "6YUo"),  # 10 tokens (assuming 6 decimals)
    ]
    
    for mint, amount, symbol in tokens_to_clean:
        print(f"\n🔄 Selling {symbol} ({amount / 1e6:.2f} tokens)...")
        
        # Get quote
        quote = get_quote(mint, USDC_MINT, amount, slippage=150)
        if not quote:
            print(f"   ❌ No quote for {symbol}")
            continue
        
        out_amount = int(quote.get('outAmount', 0)) / 1e6
        print(f"   📊 Quote: {amount/1e6:.2f} {symbol} → ${out_amount:.2f} USDC")
        
        # Get swap tx
        swap_data = get_swap_tx(quote, pubkey)
        if not swap_data or 'swapTransaction' not in swap_data:
            print(f"   ❌ No swap tx for {symbol}")
            continue
        
        # Sign and send
        try:
            tx_bytes = base64.b64decode(swap_data['swapTransaction'])
            tx = VersionedTransaction.from_bytes(tx_bytes)
            signed_tx = VersionedTransaction(tx.message, [keypair])
            signed_b64 = base64.b64encode(bytes(signed_tx)).decode()
            
            sig = send_tx(signed_b64, rpc_url)
            if sig:
                print(f"   ✅ Sent: {sig[:32]}...")
                print(f"   🔗 https://solscan.io/tx/{sig}")
            else:
                print(f"   ❌ Send failed")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        time.sleep(2)
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    main()
