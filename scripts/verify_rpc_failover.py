import sys
import os
import requests
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.shared.infrastructure.rpc_manager import RpcConnectionManager


def test_failover():
    print("🧪 Testing RPC Failover Logic...")

    # Setup Manager with 2 Mock URLs
    manager = RpcConnectionManager(["https://mock-rpc-1.com", "https://mock-rpc-2.com"])

    # Mock requests.post
    original_post = requests.post

    def mock_post(url, json=None, timeout=5):
        print(f"   📞 Call to {url}")
        if url == "https://mock-rpc-1.com":
            print("   ❌ Simulating 500 Error")
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            return mock_resp
        else:
            print("   ✅ Simulating Success (200)")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

    requests.post = mock_post

    try:
        # First Call - Should hit RPC 1, see 500, log error
        # Note: Manager doesn't auto-switch on 500 return, but it degrades score.
        # Wait, my implementation said: "auto-switch on connection failure" (exception)
        # but 500 logic was: "Simple heuristic... rely on explicit switch".
        # Let's adjust the test to force a switch or check strict behavior.

        # Actually, let's verify what I implemented:
        # "On connection error... switch_provider... raise e"
        # "If response.status_code >= 500... record_error"

        # Test Connection Error (Simulated)
        def mock_connection_error(url, json=None, timeout=5):
            print(f"   📞 Call to {url}")
            if url == "https://mock-rpc-1.com":
                print("   💥 Simulating Connection Error")
                raise requests.ConnectionError("Connection Refused")
            return mock_post(url, json, timeout)

        requests.post = mock_connection_error

        print("\n--- Request 1 (Should Fail & Switch) ---")
        try:
            manager.post({})
        except requests.ConnectionError:
            print("   ✅ Caught expected ConnectionError")

        # Verify Switch
        current = manager.get_active_url()
        print(f"   👉 Current active RPC: {current}")

        if current == "https://mock-rpc-2.com":
            print("✅ PASS: Switched to Failover RPC")
        else:
            print(f"❌ FAIL: Did not switch (Still {current})")

    finally:
        requests.post = original_post


if __name__ == "__main__":
    test_failover()
