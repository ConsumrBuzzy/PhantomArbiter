import requests

# Test QuickNode public Jupiter API (free tier with 0.2% fee)
url = "https://public.jupiterapi.com/quote"
params = {
    "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "outputMint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 
    "amount": "12000000",
    "slippageBps": "50"
}

try:
    r = requests.get(url, params=params, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
