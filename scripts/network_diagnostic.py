"""
z.ink Network Diagnostic Tool
=============================
Pings available z.ink RPC endpoints to determine the best connection (lowest latency).
"""

import time
import requests
from typing import Dict, Tuple

# Official z.ink RPCs (Feb 2026)
RPCS = {
    "Primary (Gelato)": "https://rpc-gel.inkonchain.com",
    "Secondary (QuickNode)": "https://rpc-qnd.inkonchain.com",
    "Fallback (Public)": "https://mainnet.z.ink"
}

def check_rpc(name: str, url: str) -> Tuple[str, float, int]:
    """
    Check RPC health, latency, and block height.
    Returns: (status, latency_ms, block_height)
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBlockHeight",
        "params": []
    }
    
    start = time.time()
    try:
        response = requests.post(url, json=payload, timeout=5)
        latency = (time.time() - start) * 1000
        
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                return "ONLINE", latency, data["result"]
            else:
                return "ERROR (No Result)", latency, 0
        else:
            return f"HTTP {response.status_code}", latency, 0
            
    except Exception as e:
        return f"FAILED ({str(e)[:20]}...)", 9999, 0

def main():
    print(r"""
   ______     __        __ 
  |___  /    |_ |      | | 
     / /  _ __| | _____| | 
    / / || |__| |/ / _ \ | 
   / /__| |   |   <  __/_| 
  /_____|_|   |_|\_\___(_) 
                           
   NETWORK DIAGNOSTIC (z.ink)
    """)
    print(f"Target Chain ID: 57073")
    print("-" * 60)
    print(f"{'RPC NAME':<25} | {'STATUS':<15} | {'LATENCY':<10} | {'HEIGHT':<10}")
    print("-" * 60)
    
    best_rpc = None
    min_latency = 9999
    
    for name, url in RPCS.items():
        status, latency, height = check_rpc(name, url)
        print(f"{name:<25} | {status:<15} | {latency:.0f}ms      | {height:<10}")
        
        if status == "ONLINE" and latency < min_latency:
            min_latency = latency
            best_rpc = url
            
    print("-" * 60)
    
    if best_rpc:
        print(f"✅ Recommended RPC: {best_rpc}")
    else:
        print("❌ No healthy RPCs found. Check internet connection.")

if __name__ == "__main__":
    main()
