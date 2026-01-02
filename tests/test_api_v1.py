import requests
import json
import time

URL = "http://localhost:8001/api/v1/events"

payload = {
    "type": "MARKET_UPDATE",
    "source": "TEST_SCRIPT",
    "data": {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "SOL",
        "price": 150.0,
        "category": "INFRA"
    }
}

try:
    print(f"📡 Sending POST to {URL}...")
    response = requests.post(URL, json=payload, timeout=2)
    print(f"Response Code: {response.status_code}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 200:
        print("✅ API Endpoint functional!")
    elif response.status_code == 405:
        print("❌ Method Not Allowed (405) - Old Server Version Running")
    else:
        print(f"⚠️ Unexpected status: {response.status_code}")
        
except Exception as e:
    print(f"❌ Connection Error: {e}")
    print("ℹ️  Server might not be running or port is different.")
