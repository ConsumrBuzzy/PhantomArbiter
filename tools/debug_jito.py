"""
Jito Diagnostic Tool
====================
Tests Jito bundle simulation with a minimal transaction to isolate failure reasons.

Usage: python tools/debug_jito.py
"""

import asyncio
import os
import sys
import base58

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.hash import Hash

import httpx

# Jito endpoints
JITO_ENDPOINTS = [
    "https://mainnet.block-engine.jito.wtf/api/v1/bundles",
    "https://amsterdam.mainnet.block-engine.jito.wtf/api/v1/bundles",
    "https://tokyo.mainnet.block-engine.jito.wtf/api/v1/bundles",
    "https://frankfurt.mainnet.block-engine.jito.wtf/api/v1/bundles",
]

JITO_TIP_ACCOUNTS = [
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
]


async def get_recent_blockhash():
    """Get recent blockhash from RPC."""
    rpc_url = os.getenv("HELIUS_RPC_URL") or "https://api.mainnet-beta.solana.com"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getLatestBlockhash",
                "params": [{"commitment": "finalized"}],
            },
        )
        result = resp.json()
        return result["result"]["value"]["blockhash"]


async def build_tip_transaction(
    keypair: Keypair, blockhash: str, tip_lamports: int = 10000
):
    """Build a simple tip transaction for testing."""
    tip_account = Pubkey.from_string(JITO_TIP_ACCOUNTS[0])

    tip_ix = transfer(
        TransferParams(
            from_pubkey=keypair.pubkey(), to_pubkey=tip_account, lamports=tip_lamports
        )
    )

    msg = MessageV0.try_compile(
        payer=keypair.pubkey(),
        instructions=[tip_ix],
        address_lookup_table_accounts=[],
        recent_blockhash=Hash.from_string(blockhash),
    )

    tx = VersionedTransaction(msg, [keypair])
    return base58.b58encode(bytes(tx)).decode()


async def test_jito_simulation(tx_b58: str, endpoint: str):
    """Test simulation at a specific endpoint."""
    print(f"\n🔍 Testing: {endpoint.split('/')[2]}")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Test simulation
            sim_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "simulateBundle",
                "params": [
                    {
                        "encodedTransactions": [tx_b58],
                        "skipSigVerify": True,
                        "replaceRecentBlockhash": True,
                    }
                ],
            }

            resp = await client.post(endpoint, json=sim_payload)
            result = resp.json()

            if "result" in result:
                value = result["result"].get("value", {})
                summary = value.get("summary")

                if summary == "succeeded":
                    print("   ✅ Simulation: SUCCEEDED")
                    print(f"   📊 Units consumed: {value.get('unitsConsumed', 'N/A')}")
                    return True
                else:
                    print("   ❌ Simulation: FAILED")
                    print(f"   📋 Summary: {summary}")
                    if value.get("err"):
                        print(f"   📋 Error: {value.get('err')}")
                    if value.get("logs"):
                        print(f"   📋 Logs: {value.get('logs')[-3:]}")  # Last 3 logs
                    return False
            elif "error" in result:
                print(f"   ❌ RPC Error: {result['error']}")
                return False
            else:
                print(f"   ⚠️ Unknown response: {result}")
                return False

    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False


async def test_jito_availability():
    """Test if Jito endpoints are reachable."""
    print("\n" + "=" * 60)
    print("🔌 JITO ENDPOINT AVAILABILITY")
    print("=" * 60)

    for endpoint in JITO_ENDPOINTS:
        name = endpoint.split("/")[2].split(".")[0]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTipAccounts",
                        "params": [],
                    },
                )
                if resp.status_code == 200:
                    print(f"   ✅ {name}: OK")
                else:
                    print(f"   ❌ {name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"   ❌ {name}: {e}")


async def main():
    print("=" * 60)
    print("🔧 JITO DIAGNOSTIC TOOL")
    print("=" * 60)

    # Load wallet
    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    if not private_key:
        print("❌ SOLANA_PRIVATE_KEY not set in .env")
        return

    try:
        keypair = Keypair.from_base58_string(private_key)
        print(f"✅ Wallet loaded: {str(keypair.pubkey())[:12]}...")
    except Exception as e:
        print(f"❌ Failed to load wallet: {e}")
        return

    # Test endpoint availability
    await test_jito_availability()

    # Get blockhash
    print("\n" + "=" * 60)
    print("📦 BUILDING TEST TRANSACTION")
    print("=" * 60)

    try:
        blockhash = await get_recent_blockhash()
        print(f"   ✅ Blockhash: {blockhash[:16]}...")
    except Exception as e:
        print(f"   ❌ Failed to get blockhash: {e}")
        return

    # Build tip tx
    try:
        tx_b58 = await build_tip_transaction(keypair, blockhash, tip_lamports=10000)
        print(f"   ✅ Transaction built: {tx_b58[:20]}...")
    except Exception as e:
        print(f"   ❌ Failed to build transaction: {e}")
        import traceback

        traceback.print_exc()
        return

    # Test simulation on all endpoints
    print("\n" + "=" * 60)
    print("🧪 TESTING SIMULATION")
    print("=" * 60)

    results = {}
    for endpoint in JITO_ENDPOINTS:
        name = endpoint.split("/")[2].split(".")[0]
        success = await test_jito_simulation(tx_b58, endpoint)
        results[name] = success

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    working = [name for name, ok in results.items() if ok]
    failing = [name for name, ok in results.items() if not ok]

    if working:
        print(f"   ✅ Working endpoints: {', '.join(working)}")
    if failing:
        print(f"   ❌ Failing endpoints: {', '.join(failing)}")

    if not working:
        print("\n   🔴 ALL ENDPOINTS FAILING!")
        print("   Possible causes:")
        print("     1. Wallet has insufficient SOL for tip")
        print("     2. Transaction serialization error")
        print("     3. Jito network-wide issue")
        print("     4. IP rate limited")


if __name__ == "__main__":
    asyncio.run(main())
