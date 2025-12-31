import requests
import json

mint = "dezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"

print(f"Fetching {url}...")
try:
    resp = requests.get(url, timeout=10)
    data = resp.json()

    print("Status:", resp.status_code)
    pairs = data.get("pairs", [])
    print(f"Pairs found: {len(pairs)}")

    if pairs:
        print("First Pair:", json.dumps(pairs[0], indent=2))
        base = pairs[0].get("baseToken", {}).get("address")
        print(f"Base Token Match: {base == mint}")
    else:
        print("Response:", json.dumps(data, indent=2))

except Exception as e:
    print("Error:", e)
