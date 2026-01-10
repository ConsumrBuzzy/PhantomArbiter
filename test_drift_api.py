"""Quick test of Drift API"""
import httpx
import asyncio
import json

async def test():
    url = "https://data.api.drift.trade/fundingRates?marketName=SOL"
    print(f"Fetching: {url}")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Type: {type(data)}")
                
                if isinstance(data, dict):
                    print(f"Keys: {list(data.keys())}")
                    records = data.get("data", data.get("records", [data]))
                else:
                    records = data
                
                if isinstance(records, list):
                    print(f"Records count: {len(records)}")
                    if records:
                        latest = records[-1]
                        print(f"Latest record keys: {list(latest.keys()) if isinstance(latest, dict) else 'not dict'}")
                else:
                    latest = records
                    print(f"Single record keys: {list(latest.keys()) if isinstance(latest, dict) else 'not dict'}")
                
                print(f"Records: {len(records)}")
                
                if records and len(records) > 0:
                    latest = records[-1] if isinstance(records, list) else records
                    rate = float(latest.get("fundingRate", 0))
                    twap = float(latest.get("oraclePriceTwap", 1))
                    pct = (rate / twap) * 100
                    print(f"Latest funding rate: {pct:.6f}%")
            else:
                print(f"Error: {response.text}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
