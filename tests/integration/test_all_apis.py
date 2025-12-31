"""
API Key Verification Script
============================
Tests all configured API endpoints to verify credentials are working.

Run: python test_all_apis.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def test_result(name: str, success: bool, details: str = ""):
    """Print formatted test result."""
    status = f"{GREEN}✓ PASS{RESET}" if success else f"{RED}✗ FAIL{RESET}"
    print(f"  {status} {name}")
    if details:
        print(f"         {details}")


def test_quicknode():
    """Test QuickNode RPC endpoint."""
    print(f"\n{YELLOW}1. QuickNode RPC{RESET}")

    url = os.getenv("QUICKNODE_RPC_URL")
    if not url:
        test_result(
            "QuickNode",
            False,
            "No QUICKNODE_RPC_URL in .env (DevNet endpoints won't work for mainnet)",
        )
        return False

    # Check if it's a devnet URL
    if "devnet" in url.lower():
        test_result("QuickNode", False, "DevNet endpoint - need mainnet for trading")
        return False

    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if "result" in data and data["result"] == "ok":
            test_result("QuickNode", True, f"Health: OK | Endpoint: ...{url[-30:]}")
            return True
        else:
            test_result("QuickNode", False, f"Response: {data}")
            return False
    except Exception as e:
        test_result("QuickNode", False, str(e))
        return False


def test_ankr():
    """Test Ankr RPC endpoint."""
    print(f"\n{YELLOW}2. Ankr RPC{RESET}")

    url = os.getenv("ANKR_RPC_URL")

    # Auto-construct URL from API key if not set
    if not url:
        api_key = os.getenv("ANKR_API_KEY")
        if api_key:
            url = f"https://rpc.ankr.com/solana/{api_key}"
            print("         (Auto-constructed URL from ANKR_API_KEY)")
        else:
            test_result("Ankr", False, "No ANKR_RPC_URL or ANKR_API_KEY in .env")
            return False

    # Check if it's a devnet URL
    if "devnet" in url.lower():
        test_result("Ankr", False, "DevNet endpoint - need mainnet for trading")
        return False

    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        # Handle error response (string format from Ankr)
        if isinstance(data, dict) and "error" in data:
            error = data["error"]
            if isinstance(error, str):
                if "not allowed" in error.lower():
                    test_result("Ankr", False, "API key not enabled for Solana mainnet")
                else:
                    test_result("Ankr", False, error[:60])
            else:
                test_result("Ankr", False, error.get("message", "Unknown error")[:60])
            return False

        if isinstance(data, dict) and "result" in data:
            test_result("Ankr", True, f"Health: {data.get('result', 'ok')}")
            return True

        test_result("Ankr", False, "Unexpected response")
        return False
    except Exception as e:
        test_result("Ankr", False, str(e)[:60])
        return False


def test_helius():
    """Test Helius RPC/API endpoint."""
    print(f"\n{YELLOW}3. Helius RPC{RESET}")

    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        test_result("Helius", False, "No HELIUS_API_KEY in .env")
        return False

    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if "result" in data:
            test_result("Helius", True, f"Health: {data.get('result', 'ok')}")
            return True
        else:
            test_result("Helius", False, f"Response: {data}")
            return False
    except Exception as e:
        test_result("Helius", False, str(e))
        return False


def test_moralis():
    """Test Moralis API endpoint."""
    print(f"\n{YELLOW}4. Moralis API{RESET}")

    api_key = os.getenv("MORALIS_API_KEY")
    if not api_key:
        test_result("Moralis", False, "No MORALIS_API_KEY in .env")
        return False

    try:
        # Test with a simple endpoint
        url = "https://solana-gateway.moralis.io/account/mainnet/vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg/balance"
        headers = {"Accept": "application/json", "X-API-Key": api_key}
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            test_result("Moralis", True, "Balance endpoint working")
            return True
        elif resp.status_code == 401:
            test_result("Moralis", False, "Invalid API key (401 Unauthorized)")
            return False
        else:
            test_result("Moralis", False, f"Status: {resp.status_code}")
            return False
    except Exception as e:
        test_result("Moralis", False, str(e))
        return False


def test_jupiter():
    """Test Jupiter API endpoint (no auth required)."""
    print(f"\n{YELLOW}5. Jupiter API{RESET}")

    try:
        # Test quote API
        url = "https://quote-api.jup.ag/v6/quote"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",  # SOL
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "amount": "1000000000",  # 1 SOL
        }
        resp = requests.get(url, params=params, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if "outAmount" in data:
                out_usdc = int(data["outAmount"]) / 1e6
                test_result("Jupiter", True, f"1 SOL = ${out_usdc:.2f} USDC")
                return True

        test_result("Jupiter", False, f"Status: {resp.status_code}")
        return False
    except Exception as e:
        test_result("Jupiter", False, str(e))
        return False


def test_dexscreener():
    """Test DexScreener API endpoint (no auth required)."""
    print(f"\n{YELLOW}6. DexScreener API{RESET}")

    try:
        # Test with SOL token
        url = "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                price = float(pairs[0].get("priceUsd", 0))
                test_result("DexScreener", True, f"SOL = ${price:.2f}")
                return True

        test_result("DexScreener", False, f"Status: {resp.status_code}")
        return False
    except Exception as e:
        test_result("DexScreener", False, str(e))
        return False


def test_pyth():
    """Test Pyth Network Hermes API (no auth required)."""
    print(f"\n{YELLOW}7. Pyth Network (Hermes){RESET}")

    try:
        # SOL/USD feed ID
        feed_id = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
        url = f"https://hermes.pyth.network/v2/updates/price/latest?ids[]={feed_id}"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            parsed = data.get("parsed", [])
            if parsed:
                price_data = parsed[0].get("price", {})
                raw_price = int(price_data.get("price", 0))
                expo = int(price_data.get("expo", 0))
                price = raw_price * (10**expo)
                test_result("Pyth", True, f"SOL = ${price:.2f}")
                return True

        test_result("Pyth", False, f"Status: {resp.status_code}")
        return False
    except Exception as e:
        test_result("Pyth", False, str(e))
        return False


def test_coingecko():
    """Test CoinGecko API endpoint."""
    print(f"\n{YELLOW}8. CoinGecko API{RESET}")

    api_key = os.getenv("COINGECKO_API_KEY")

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "solana", "vs_currencies": "usd"}
        headers = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        resp = requests.get(url, params=params, headers=headers, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            sol_price = data.get("solana", {}).get("usd", 0)
            auth_status = "with API key" if api_key else "public (rate limited)"
            test_result("CoinGecko", True, f"SOL = ${sol_price:.2f} ({auth_status})")
            return True
        elif resp.status_code == 429:
            test_result("CoinGecko", False, "Rate limited (429)")
            return False

        test_result("CoinGecko", False, f"Status: {resp.status_code}")
        return False
    except Exception as e:
        test_result("CoinGecko", False, str(e))
        return False


def test_bigquery():
    """Test BigQuery connection (requires google-cloud-bigquery)."""
    print(f"\n{YELLOW}9. Google BigQuery{RESET}")

    creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_file:
        test_result("BigQuery", False, "No GOOGLE_APPLICATION_CREDENTIALS in .env")
        return False

    if not os.path.exists(creds_file):
        test_result("BigQuery", False, f"Credentials file not found: {creds_file}")
        return False

    try:
        from google.cloud import bigquery

        client = bigquery.Client()
        query = "SELECT 1 as test"
        result = client.query(query).result()

        for row in result:
            if row.test == 1:
                test_result("BigQuery", True, "Query executed successfully")
                return True

        test_result("BigQuery", False, "Unexpected result")
        return False
    except ImportError:
        test_result("BigQuery", False, "google-cloud-bigquery not installed")
        return False
    except Exception as e:
        test_result("BigQuery", False, str(e))
        return False


def main():
    """Run all API tests."""
    print("=" * 60)
    print("PhantomTrader API Verification")
    print("=" * 60)

    results = []

    # Test all APIs
    results.append(("QuickNode", test_quicknode()))
    results.append(("Ankr", test_ankr()))
    results.append(("Helius", test_helius()))
    results.append(("Moralis", test_moralis()))
    results.append(("Jupiter", test_jupiter()))
    results.append(("DexScreener", test_dexscreener()))
    results.append(("Pyth", test_pyth()))
    results.append(("CoinGecko", test_coingecko()))
    results.append(("BigQuery", test_bigquery()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = f"{GREEN}PASS{RESET}" if success else f"{RED}FAIL{RESET}"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} APIs working")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
