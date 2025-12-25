import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("JUPITER_API_KEY", "")
if not api_key:
    print("⚠️ JUPITER_API_KEY not set in .env - test will use public endpoint")

params = {
    "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
    "outputMint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", # WIF
    "amount": "12000000", # 12 USDC
    "slippageBps": "50"
}
headers = {
    "x-api-key": api_key
}

try:
    print(f"Testing key: {api_key}")
    print(f"URL: {url}")
    r = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print("SUCCESS! API Key is valid.")
        print(r.text[:200])
    else:
        print(f"FAILED: {r.text}")
except Exception as e:
    print(f"Error: {e}")
