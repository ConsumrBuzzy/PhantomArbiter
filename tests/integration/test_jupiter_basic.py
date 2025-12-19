import requests
import time

api_key = '***REDACTED***'

# Endpoints associated with "Basic" tier
urls = [
    "https://api.jup.ag/swap/v1/quote",
    "https://api.jup.ag/v6/quote",
    "https://quote-api.jup.ag/v6/quote"
]

params = {
    "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 
    "outputMint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 
    "amount": "12000000", 
    "slippageBps": "50"
}
headers = {
    "x-api-key": api_key
}

print(f"Testing Key: {api_key}")
print("-" * 50)

for url in urls:
    try:
        print(f"Testing: {url}")
        r = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print("SUCCESS! Valid Quote received.")
            print(r.text[:200])
        else:
            print(f"Failed: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 50)
    time.sleep(1)
