import requests
import json
import time

RPCS = {
    "rpc-gel": "https://rpc-gel.inkonchain.com",
    "rpc-qnd": "https://rpc-qnd.inkonchain.com"
}

def probe(url, name):
    print(f"\n🔍 Probing {name} ({url})...")
    
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://play.staratlas.com"
    }

    methods = [
        {"jsonrpc": "2.0", "id": 1, "method": "getHealth"},        # SVM
        {"jsonrpc": "2.0", "id": 2, "method": "getVersion"},       # SVM
        {"jsonrpc": "2.0", "id": 3, "method": "getLatestBlockhash", "params": [{"commitment": "finalized"}]}, # SVM - Critical
        {"jsonrpc": "2.0", "id": 4, "method": "web3_clientVersion"}, # EVM
        {"jsonrpc": "2.0", "id": 5, "method": "eth_chainId"}        # EVM
    ]

    for m in methods:
        try:
            resp = requests.post(url, headers=headers, json=m, timeout=5)
            if resp.status_code == 200:
                print(f"   ✅ {m['method']}: {resp.json().get('result', 'No Result')} (200)")
            else:
                try:
                    err = resp.json().get('error', {}).get('message', 'Unknown Error')
                    print(f"   ❌ {m['method']}: {err} ({resp.status_code})")
                except:
                    print(f"   ❌ {m['method']}: {resp.status_code}")
        except Exception as e:
            print(f"   ⚠️  {m['method']}: Exception {e}")

if __name__ == "__main__":
    for name, url in RPCS.items():
        probe(url, name)
