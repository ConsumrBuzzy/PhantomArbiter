#!/usr/bin/env python3
"""
DIAGNOSTIC: Held Token Detection Test (ASCII Version)
======================================================
Isolates the exact failure point in token detection.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY", "")

SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def get_wallet_pubkey():
    try:
        from solders.keypair import Keypair
        if not PRIVATE_KEY or "YOUR" in PRIVATE_KEY.upper():
            print("[ERROR] SOLANA_PRIVATE_KEY not set in .env")
            return None
        kp = Keypair.from_base58_string(PRIVATE_KEY)
        return str(kp.pubkey())
    except Exception as e:
        print(f"[ERROR] Failed to load keypair: {e}")
        return None


def fetch_token_accounts(pubkey: str, program_id: str) -> dict:
    print(f"\n[RPC] Querying: {RPC_URL[:50]}...")
    print(f"[RPC] Program: {'SPL' if 'Tokenkeg' in program_id else 'Token2022'}")
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            pubkey,
            {"programId": program_id},
            {"encoding": "jsonParsed"}
        ]
    }
    
    try:
        resp = requests.post(RPC_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        data = resp.json()
        
        if "error" in data:
            print(f"[ERROR] RPC Error: {data['error']}")
            return {}
        
        tokens = {}
        accounts = data.get("result", {}).get("value", [])
        print(f"[RPC] Found {len(accounts)} token account(s)")
        
        for account in accounts:
            try:
                info = account["account"]["data"]["parsed"]["info"]
                mint = info["mint"]
                balance = float(info["tokenAmount"]["uiAmount"] or 0)
                if balance > 0:
                    tokens[mint] = balance
            except Exception as e:
                continue
        
        return tokens
        
    except requests.exceptions.Timeout:
        print(f"[ERROR] RPC Timeout (rate limited?)")
        return {}
    except Exception as e:
        print(f"[ERROR] RPC Error: {e}")
        return {}


def load_watchlist():
    watchlist_path = os.path.join(os.path.dirname(__file__), "data/watchlist.json")
    try:
        with open(watchlist_path, 'r') as f:
            data = json.load(f)
        mint_to_symbol = {}
        for symbol, info in data.get("assets", {}).items():
            mint = info.get("mint", "")
            if mint:
                mint_to_symbol[mint] = symbol
        return mint_to_symbol
    except Exception as e:
        print(f"[WARN] Failed to load watchlist: {e}")
        return {}


def check_broker_cache():
    print("\n" + "="*60)
    print("BROKER CACHE STATUS")
    print("="*60)
    
    try:
        from src.core.shared_cache import is_broker_alive, SharedPriceCache
        
        alive = is_broker_alive()
        print(f"Broker Alive: {'YES' if alive else 'NO'}")
        
        if alive:
            wallet_state = SharedPriceCache.get_wallet_state(max_age=300)
            if wallet_state:
                print(f"Wallet State: FOUND")
                print(f"USDC Balance: ${wallet_state.get('usdc', 0):.2f}")
                print(f"SOL Balance:  {wallet_state.get('sol', 0):.4f}")
                
                held = wallet_state.get("held_assets", {})
                print(f"Held Assets:  {len(held)} tokens")
                
                if held:
                    for sym, data in held.items():
                        bal = data.get("balance", 0) if isinstance(data, dict) else data
                        print(f"  - {sym}: {bal:.4f}")
                else:
                    print("  [WARN] EMPTY! This may prevent detection.")
            else:
                print(f"Wallet State: NOT FOUND or STALE")
        else:
            print("[INFO] Broker not running - bot will use direct RPC")
            
    except ImportError:
        print("[WARN] Could not import shared_cache module")
    except Exception as e:
        print(f"[ERROR] Error checking broker: {e}")


def main():
    print("="*60)
    print("HELD TOKEN DETECTION DIAGNOSTIC")
    print("="*60)
    
    pubkey = get_wallet_pubkey()
    if not pubkey:
        return 1
    
    print(f"\nWallet: {pubkey[:8]}...{pubkey[-8:]}")
    
    print("\n" + "="*60)
    print("WATCHLIST MAPPINGS")
    print("="*60)
    mint_to_symbol = load_watchlist()
    print(f"Loaded {len(mint_to_symbol)} asset mappings")
    
    check_broker_cache()
    
    print("\n" + "="*60)
    print("BLOCKCHAIN QUERY (SPL Token)")
    print("="*60)
    spl_tokens = fetch_token_accounts(pubkey, SPL_TOKEN_PROGRAM)
    
    print("\n" + "="*60)
    print("BLOCKCHAIN QUERY (Token2022)")
    print("="*60)
    token2022_tokens = fetch_token_accounts(pubkey, TOKEN_2022_PROGRAM)
    
    all_tokens = {**spl_tokens, **token2022_tokens}
    
    print("\n" + "="*60)
    print("DETECTION RESULTS")
    print("="*60)
    
    if not all_tokens:
        print("\n[WARN] NO TOKENS DETECTED!")
        print("Possible causes:")
        print("1. Wallet has no token holdings")
        print("2. RPC is rate-limited (try different endpoint)")
        print("3. Private key is incorrect")
        return 1
    
    tracked = []
    untracked = []
    
    for mint, balance in all_tokens.items():
        symbol = mint_to_symbol.get(mint, None)
        if symbol:
            tracked.append((symbol, mint, balance))
        else:
            untracked.append((mint, balance))
    
    print(f"\n[OK] TRACKED TOKENS ({len(tracked)}):")
    if tracked:
        for sym, mint, bal in tracked:
            print(f"  {sym}: {bal:.4f} tokens (Mint: {mint[:16]}...)")
    else:
        print("  (none)")
    
    print(f"\n[WARN] UNTRACKED TOKENS ({len(untracked)}):")
    if untracked:
        print("These tokens are NOT in watchlist.json!")
        for mint, bal in untracked:
            print(f"  UNKNOWN: {bal:.4f} tokens")
            print(f"    Mint: {mint}")
    else:
        print("  (none - all tokens are mapped)")
    
    print("\n" + "="*60)
    print("DIAGNOSIS SUMMARY")
    print("="*60)
    
    if tracked:
        print(f"[OK] {len(tracked)} token(s) should be detected by the bot")
    
    if untracked:
        print(f"[ACTION] {len(untracked)} token(s) need to be added to watchlist.json")
    
    if token2022_tokens:
        print(f"[ACTION] {len(token2022_tokens)} Token2022 tokens found!")
        print("  Current bot only queries SPL Token program.")
        print("  FIX: Update execution.py to also query Token2022.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
