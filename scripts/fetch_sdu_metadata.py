import requests
import json
import time

URL = "https://galaxy.staratlas.com/nfts"

def fetch_metadata():
    print(f"Fetching {URL}...")
    try:
        response = requests.get(URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"Fetched {len(data)} items.")
        return data
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def find_sdu(data):
    sdu_items = []
    for item in data:
        # Check symbol or name for SDU / Scan Data
        symbol = item.get('symbol', '').upper()
        name = item.get('name', '').upper()
        
        if 'SDU' in symbol or 'SCAN' in name:
             sdu_items.append(item)
    
    return sdu_items

def main():
    data = fetch_metadata()
    matches = find_sdu(data)
    
    print(f"\nFound {len(matches)} potential SDU items:")
    for item in matches:
        print("-" * 40)
        print(f"Name: {item.get('name')}")
        print(f"Symbol: {item.get('symbol')}")
        print(f"Mint: {item.get('mint')}")
        print(f"Markets: {json.dumps(item.get('markets'), indent=2)}")
        print(f"Trade Settings: {json.dumps(item.get('tradeSettings'), indent=2)}")

if __name__ == "__main__":
    main()
