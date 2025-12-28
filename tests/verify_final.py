import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.provider_pool import ProviderType, PROVIDER_CONFIGS, ProviderPool

def test_flexible_loading():
    print("--- Testing Flexible URL Loading ---")
    pool = ProviderPool()
    
    # Mock some env vars matching the user's "URL vs Endpoint" naming
    os.environ["HELIUS_RPC_URL"] = "https://mock-helius.com/rpc"
    os.environ["ALCHEMY_ENDPOINT"] = "https://mock-alchemy.com/v2/key"
    os.environ["CHAINSTACK_RPC_URL"] = "https://user:pass@mock-chainstack.com/key"
    os.environ["ANKR_ENDPOINT"] = "https://mock-ankr.com/sol"
    
    count = pool.load_from_env()
    print(f"Loaded {count} endpoints")
    
    for ep in pool._endpoints:
        print(f"Provider: {ep.provider.name}")
        print(f"  HTTP: {ep.http_url}")
        print(f"  WSS:  {ep.wss_url}")
        print(f"  Auth Context: {'Basic Auth Detected' if '@' in ep.http_url else 'API Key Only'}")

if __name__ == "__main__":
    test_flexible_loading()
