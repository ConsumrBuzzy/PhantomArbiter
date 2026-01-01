import sys
import os
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from src.interface.api_service import app

client = TestClient(app)

def test_api():
    print("🧪 Testing API Endpoints...")
    
    # 1. Test Static Helper
    # Usually testclient doesn't fully serve static files the same way uvicorn does if not configured, 
    # but we can check if route exists or if we can hit root.
    # Note: StaticFiles usually mounts at catch-all.
    
    # 2. Test Galaxy Endpoint
    response = client.get("/api/v1/galaxy")
    if response.status_code == 200:
        print("   ✅ GET /api/v1/galaxy: OK")
        print(f"      Payload: {len(response.json())} objects")
    else:
        print(f"   ❌ GET /api/v1/galaxy Failed: {response.status_code}")
        print(response.text)
        
    # 3. Test Websocket (Connect only)
    try:
        with client.websocket_connect("/ws/v1/stream") as websocket:
            print("   ✅ WS /ws/v1/stream: Connected")
            # If we had a way to trigger signal bus we could test receive
    except Exception as e:
         print(f"   ❌ WS Connection Failed: {e}")

if __name__ == "__main__":
    test_api()
