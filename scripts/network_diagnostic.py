"""
z.ink Network Diagnostic Tool
=============================
Pings available z.ink RPC endpoints to determine the best connection (lowest latency).
"""

import time
import requests
import json

RPCS = {
    "Ironforge (SVM)": "https://rpc.ironforge.network/mainnet?apiKey=01HZFJ18Q9E3QT62P67P52PC03"
}

def verify_svm_handshake():
    print("=== STAR ATLAS SVM CONNECTIVITY TEST ===")
    
    for name, url in RPCS.items():
        print(f"\n🔍 Testing {name} ({url})...")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getVersion" # Solana-native method
        }
        
        try:
            start_time = time.time()
            response = requests.post(url, json=payload, timeout=5)
            elapsed = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "solana-core" in data["result"]:
                    version = data["result"]["solana-core"]
                    print(f"   ✅ SUCCESS: Connected to SVM Node.")
                    print(f"   Version: {version}")
                    print(f"   Latency: {elapsed:.2f}ms")
                else:
                    print(f"   ⚠️  connected but unexpected response: {data}")
            else:
                print(f"   ❌ FAILED: Status {response.status_code}")
                print(f"   Response: {response.text[:100]}...")
        except Exception as e:
            print(f"   ❌ CONNECTION ERROR: {e}")

if __name__ == "__main__":
    verify_svm_handshake()
