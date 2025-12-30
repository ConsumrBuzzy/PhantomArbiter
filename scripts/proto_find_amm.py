import requests
import struct
import base64
from solders.pubkey import Pubkey

RPC_URL = "https://api.mainnet-beta.solana.com"
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

def find_raydium_amm_pool(mint_a: str, mint_b: str):
    """
    Find Raydium Standard AMM pool address for a pair.
    Raydium AMM pools don't use PDA for address derivation in a simple way (salted),
    so we typically use getProgramAccounts with memcmp filter for the mints.
    """
    # Layout offset for mints in Raydium AMM (LIQUIDITY_STATE_LAYOUT_V4)
    # coinMint is at offset 400
    # pcMint is at offset 432
    # status is at offset 0 (u64)
    
    # We'll try both permutations (A/B and B/A)
    # Filter 1: coinMint = mint_a, pcMint = mint_b
    filters_1 = [
        {"dataSize": 752},  # Layout V4 size
        {"memcmp": {"offset": 400, "bytes": mint_a}},
        {"memcmp": {"offset": 432, "bytes": mint_b}}
    ]
    
    # Filter 2: coinMint = mint_b, pcMint = mint_a
    filters_2 = [
        {"dataSize": 752},
        {"memcmp": {"offset": 400, "bytes": mint_b}},
        {"memcmp": {"offset": 432, "bytes": mint_a}}
    ]
    
    print(f"🔍 Searching for Standard AMM pool for {mint_a} / {mint_b}...")
    
    for f in [filters_1, filters_2]:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts",
            "params": [
                RAYDIUM_AMM_PROGRAM,
                {"filters": f, "encoding": "base64"}
            ]
        }
        resp = requests.post(RPC_URL, json=payload).json()
        
        if "result" in resp and resp["result"]:
            pool_data = resp["result"][0]
            pubkey = pool_data["pubkey"]
            print(f"✅ Found Pool: {pubkey}")
            return pubkey
            
    print("❌ No Standard AMM pool found.")
    return None

# Test with SOL/USDC
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

find_raydium_amm_pool(SOL, USDC)
