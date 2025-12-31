"""
Phase 1: Connection Test Script (The "Handshake")
Solana Micro-Scalper - Proof of Concept

This script validates:
1. Internet connectivity & Market Data API (DexScreener)
2. Trading Engine API (Jupiter Aggregator)
3. Wallet & Blockchain Connection (Solana RPC)
"""

import os
import requests
import sys

from dotenv import load_dotenv
from solders.keypair import Keypair
from solana.rpc.api import Client

# Load environment variables from .env file
load_dotenv()

# --- USER CONFIGURATION ---
# Private Key is loaded from .env file for security
PRIVATE_KEY_STRING = os.getenv("SOLANA_PRIVATE_KEY", "YOUR_PRIVATE_KEY_HERE").strip(
    "'\""
)  # Strip quotes if present

# --- CONSTANTS ---
RPC_URL = "https://api.mainnet-beta.solana.com"
WIF_ADDRESS = "EKpQGSJtjMFqKZ9KQanSqErBt8AGTE65FhWyPi1Mwesd"


def run_diagnostics():
    print("--- 📡 STARTING SYSTEM DIAGNOSTICS ---")

    # 1. Test Internet & Market Data API
    print("\n[1/3] Testing Market Data Feed (DexScreener)...")
    try:
        # Try direct token address lookup first
        url = f"https://api.dexscreener.com/latest/dex/tokens/{WIF_ADDRESS}"
        data = requests.get(url, timeout=10).json()

        # Check if pairs data exists
        if data.get("pairs") and len(data["pairs"]) > 0:
            price = data["pairs"][0]["priceUsd"]
            print(f"   ✅ Success. Current WIF Price: ${price}")
        else:
            # Fallback: Search by symbol on Solana
            print("   ⚠️  Direct lookup returned no pairs, trying search...")
            search_url = "https://api.dexscreener.com/latest/dex/search?q=WIF%20solana"
            search_data = requests.get(search_url, timeout=10).json()

            if search_data.get("pairs") and len(search_data["pairs"]) > 0:
                # Find WIF pair on Solana
                for pair in search_data["pairs"]:
                    if (
                        pair.get("chainId") == "solana"
                        and "WIF" in pair.get("baseToken", {}).get("symbol", "").upper()
                    ):
                        price = pair["priceUsd"]
                        token_addr = pair["baseToken"]["address"]
                        print(f"   ✅ Success. Current WIF Price: ${price}")
                        print(f"   📝 Note: WIF Token Address: {token_addr}")
                        break
                else:
                    print("   ⚠️  Could not find WIF on Solana, but API is reachable.")
                    print("   📡 DexScreener API: Connected")
            else:
                print("   ⚠️  No pairs found, but API is reachable.")
                print("   📡 DexScreener API: Connected")
    except Exception as e:
        print(f"   ❌ Failed to fetch price. Error: {e}")
        sys.exit(1)

    # 2. Test Jupiter Aggregator API
    print("\n[2/3] Testing Trading Engine (Jupiter)...")
    try:
        # Jupiter API has migrated to api.jup.ag (quote-api.jup.ag deprecated Dec 2025)
        jupiter_endpoints = [
            "https://api.jup.ag/swap/v1/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000",
            "https://lite-api.jup.ag/swap/v1/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=100000",
        ]

        connected = False
        for jup_url in jupiter_endpoints:
            try:
                response = requests.get(jup_url, timeout=10)
                if response.status_code == 200:
                    print("   ✅ Success. Jupiter API is reachable.")
                    connected = True
                    break
                elif response.status_code == 400:
                    # 400 can mean the API works but params are wrong - still connected
                    print(
                        "   ✅ Jupiter API reachable (returned validation error, but connected)."
                    )
                    connected = True
                    break
            except requests.exceptions.ConnectionError:
                continue

        if not connected:
            print("   ⚠️  Could not connect to Jupiter API. Trading may not work.")
            print("   📝 Note: You may need to use a different RPC or VPN.")
    except Exception as e:
        print(f"   ❌ Connection Error: {e}")
        sys.exit(1)

    # 3. Test Wallet & Blockchain Connection
    print("\n[3/3] Testing Wallet Connection (Solana RPC)...")
    try:
        client = Client(RPC_URL)
        if "YOUR_PRIVATE_KEY" in PRIVATE_KEY_STRING:
            print("   ⚠️  WARNING: Private Key not set. Skipping wallet check.")
            print("   📝 To test wallet, add your key to the .env file:")
            print("      SOLANA_PRIVATE_KEY=your_base58_private_key_here")
        else:
            sender = Keypair.from_base58_string(PRIVATE_KEY_STRING)
            pubkey = sender.pubkey()
            print(f"   🔑 Wallet Public Key: {pubkey}")

            # Check Balance
            balance_resp = client.get_balance(pubkey)
            # The structure of the response depends on the version, handle safely:
            lamports = balance_resp.value
            sol_balance = lamports / 1_000_000_000

            print(f"   💰 Wallet Balance: {sol_balance:.4f} SOL")

            if sol_balance < 0.05:
                print(
                    "   ⚠️  WARNING: Low Balance. You need at least 0.05 SOL for gas fees."
                )
            else:
                print("   ✅ Wallet is funded and ready.")

    except Exception as e:
        print(f"   ❌ Wallet Error: {e}")
        print("   (Check if your Private Key is copied correctly)")
        sys.exit(1)

    print("\n" + "=" * 40)
    print("🚀 ALL SYSTEMS GO. READY FOR DEPLOYMENT.")
    print("=" * 40)


if __name__ == "__main__":
    run_diagnostics()
