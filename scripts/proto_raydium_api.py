import requests
import json

def check_raydium_api(mint):
    url = f"https://api-v3.raydium.io/pools/info/mint?mints={mint}&poolType=all&poolSortField=default&sortType=desc&pageSize=10&page=1"
    print(f"🌍 Checking Raydium V3 API for {mint[:6]}...")
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data"):
                pools = data["data"]["data"] # data.data.data structure
                print(f"✅ Found {len(pools)} pools:")
                for p in pools:
                    print(f"   - {p['type']} | {p['programId']} | Liquidity: ${p.get('tvl', 0)}")
            else:
                print("❌ No pools found in API.")
        else:
            print(f"❌ API Error: {resp.status_code}")
    except Exception as e:
        print(f"❌ Exception: {e}")

# Test with USDC (should have many)
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
check_raydium_api(USDC)

# Test with a Pump.fun token (if you have one, otherwise random)
