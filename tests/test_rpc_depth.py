
import os
import requests
import json

# Setup
RPC_URL = "https://api.mainnet-beta.solana.com" # Default public, will use Helius if env set
HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if HELIUS_KEY:
    RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

print(f"🔗 RPC: {RPC_URL.split('?')[0]}...")

# 1. Target: SOL/USDC Market on Raydium or OpenBook
# Raydium LIQUIDITY POOL V4 for SOL/USDC: 58oQChx4yWmvKdwLLZzBi4ChoCcKTk3BitNX354Cs71G
# OpenBook Market: 8BnEgHoWFysVcuFFX7QztDmzuH8r5ZFvyP3sYwn1XTh6 (SOL/USDC)
MARKET_ID = "8BnEgHoWFysVcuFFX7QztDmzuH8r5ZFvyP3sYwn1XTh6" 

def rpc_call(method, params):
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    try:
        resp = requests.post(RPC_URL, headers=headers, json=payload, timeout=5)
        return resp.json()
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

print(f"\n🧪 Test 1: getOrderBook (Deprecated/Specific Node Only)")
# Try standard getOrderBook (unlikely to work on generic nodes)
res = rpc_call("getOrderBook", [MARKET_ID])
if res and "error" not in res:
    print("✅ SUCCESS: Found native getOrderBook support!")
    print(json.dumps(res, indent=2)[:500])
else:
    print(f"❌ Failed or Not Supported: {res.get('error', {}).get('message') if res else 'No Response'}")

print(f"\n🧪 Test 2: getAccountInfo (Raw Slab Data)")
# Fetch market account info - we would need to decode the slab manually (complex)
res = rpc_call("getAccountInfo", [MARKET_ID, {"encoding": "base64"}])
if res and "result" in res and res["result"]["value"]:
    data_len = len(res["result"]["value"]["data"][0])
    print(f"✅ SUCCESS: Fetched Market Account Data ({data_len} bytes)")
    print("ℹ️  (Requires manual Slab decoding - suitable for specialized parser)")
else:
    print("❌ Failed to fetch account info")
