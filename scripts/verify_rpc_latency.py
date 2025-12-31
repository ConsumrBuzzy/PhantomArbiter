import sys
import os
import time
import requests
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.shared.infrastructure.rpc_manager import RpcConnectionManager


def test_latency_routing():
    print("🧪 Testing RPC Latency Routing...")

    # Mock requests.post to simulate latency
    original_post = requests.post

    def mock_post(url, json=None, timeout=5):
        # Simulate Latency
        if "fast" in url:
            time.sleep(0.01)  # 10ms
            print(f"   🏎️ Ping {url} (Fast)")
        elif "slow" in url:
            time.sleep(0.1)  # 100ms
            print(f"   🐢 Ping {url} (Slow)")
        else:
            time.sleep(0.05)  # 50ms

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    requests.post = mock_post

    try:
        # Setup Manager
        urls = ["https://slow-rpc.com", "https://fast-rpc.com", "https://mid-rpc.com"]

        # When initialized, it should auto-benchmark
        manager = RpcConnectionManager(urls)

        # Verify active URL is the fast one
        active = manager.get_active_url()
        print(f"\n👉 Winner: {active}")

        if active == "https://fast-rpc.com":
            print("✅ PASS: Selected Fastest RPC")
        else:
            print(f"❌ FAIL: Selected {active}")

    finally:
        requests.post = original_post


if __name__ == "__main__":
    test_latency_routing()
