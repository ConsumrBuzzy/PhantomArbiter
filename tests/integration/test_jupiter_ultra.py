import requests

api_key = '***REDACTED***'
# Trying the Ultra endpoint mentioned by user
url = "https://api.jup.ag/ultra/v1/quote" 
params = {
    "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 
    "outputMint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 
    "amount": "12000000", 
    "slippageBps": "50"
}
headers = {
    "x-api-key": api_key
}

try:
    print(f"Testing key against Ultra: {url}")
    r = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
