import sys
import os
import requests
import json
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.infrastructure.token_registry import get_registry

load_dotenv()

def audit():
    pubkey = "99G8vXM4YjULWtmzshsVCJ7AJeb8Psr8dfWuHbwGxry3"
    rpc_url = os.getenv("HELIUS_RPC_URL") or os.getenv("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
    
    print(f"--- DIRECT AUDIT: {rpc_url[:50]}... ---")
    
    headers = {"Content-Type": "application/json"}
    
    # 1. SOL Balance
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]
    }
    resp = requests.post(rpc_url, json=payload, headers=headers).json()
    sol = resp.get("result", {}).get("value", 0) / 1e9
    print(f"SOL: {sol:.6f}")
    
    # 2. Token Accounts (Legacy)
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [pubkey, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}, {"encoding": "jsonParsed"}]
    }
    resp = requests.post(rpc_url, json=payload, headers=headers).json()
    print("\nTokens (Legacy):")
    registry = get_registry()
    for acc in resp.get("result", {}).get("value", []):
        info = acc["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        bal = info["tokenAmount"]["uiAmount"]
        if bal > 0:
            symbol = registry.get_symbol(mint)
            print(f"  {symbol:8} | {mint}: {bal}")
            
    # 3. Token Accounts (Token-2022)
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [pubkey, {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}, {"encoding": "jsonParsed"}]
    }
    resp = requests.post(rpc_url, json=payload, headers=headers).json()
    print("\nTokens (Token-2022):")
    for acc in resp.get("result", {}).get("value", []):
        info = acc["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        bal = info["tokenAmount"]["uiAmount"]
        if bal > 0:
            symbol = registry.get_symbol(mint)
            print(f"  {symbol:8} | {mint}: {bal}")

if __name__ == "__main__":
    audit()
