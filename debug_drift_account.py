import asyncio
import base64
from solders.pubkey import Pubkey
from src.shared.system.rpc_pool import get_rpc_pool
from src.drivers.wallet_manager import WalletManager

async def debug_drift():
    print("🔍 Debugging Drift Account Data...")
    
    wm = WalletManager()
    pubkey_str = wm.get_public_key()
    print(f"🔑 Wallet: {pubkey_str}")
    
    if not pubkey_str:
        print("❌ No wallet configured!")
        return

    # Drift Program ID
    DRIFT_PROGRAM = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
    
    # Derive User Account
    wallet_pubkey = Pubkey.from_string(pubkey_str)
    user_account, _ = Pubkey.find_program_address(
        [b"user", bytes(wallet_pubkey), (0).to_bytes(2, 'little')],
        DRIFT_PROGRAM
    )
    print(f"🧾 Derived User Account: {user_account}")
    
    rpc_pool = get_rpc_pool()
    endpoint = rpc_pool.get_next_endpoint()
    print(f"📡 Using RPC: {endpoint}")
    
    from solders.rpc.requests import GetAccountInfo
    from solders.rpc.config import RpcAccountInfoConfig
    from solders.rpc.responses import GetAccountInfoResp
    import requests
    import json
    
    # Custom get_account_info using requests to avoid client mismatch
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            str(user_account),
            {"encoding": "base64"}
        ]
    }
    
    resp_raw = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"})
    resp = resp_raw.json()
    
    if "result" not in resp or not resp["result"]["value"]:
        print("❌ Account not found on-chain!")
        return

    data_b64 = resp["result"]["value"]["data"][0]
    data = base64.b64decode(data_b64)
    resp = None # Clear for flow match
    print(f"📦 Data Length: {len(data)} bytes")
    
    # Dump first 200 bytes in hex
    print("\n📝 Hex Dump (0-200):")
    print(data[:200].hex())
    
    # Scan for potential balance values
    # User had ~$4.97 = 4,970,000 atomic units
    import struct
    
    print("\n🔎 Scanning for reasonable USDC balances (int64 at 8-byte boundaries)...")
    for i in range(0, 200, 8):
        try:
            val = struct.unpack('<q', data[i:i+8])[0]
            if 0 < val < 1_000_000_000_000: # Reasonable range
                print(f"Offset {i}: {val} ({val/1e6:.2f} USDC?)")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(debug_drift())
