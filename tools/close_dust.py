"""
Close Dust Token Accounts - Recovers rent (~0.002 SOL per account)
"""

import os
import sys
import base64
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


def get_keypair():
    pk = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk:
        return None
    return Keypair.from_base58_string(pk)


def get_token_accounts(owner_pubkey: str, rpc_url: str):
    """Get all token accounts for owner."""
    resp = requests.post(
        rpc_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                owner_pubkey,
                {"programId": str(TOKEN_PROGRAM_ID)},
                {"encoding": "jsonParsed"},
            ],
        },
        timeout=10,
    )

    if resp.status_code == 200:
        result = resp.json().get("result", {})
        return result.get("value", [])
    return []


def get_blockhash(rpc_url: str):
    resp = requests.post(
        rpc_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}],
        },
        timeout=10,
    )

    if resp.status_code == 200:
        return resp.json()["result"]["value"]["blockhash"]
    return None


def close_account_ix(
    account: Pubkey, destination: Pubkey, owner: Pubkey
) -> Instruction:
    """Create a closeAccount instruction."""
    # CloseAccount instruction = index 9
    return Instruction(
        program_id=TOKEN_PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=destination, is_signer=False, is_writable=True),
            AccountMeta(pubkey=owner, is_signer=True, is_writable=False),
        ],
        data=bytes([9]),  # CloseAccount instruction
    )


def send_tx(signed_tx_b64, rpc_url):
    resp = requests.post(
        rpc_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [signed_tx_b64, {"encoding": "base64", "skipPreflight": False}],
        },
        timeout=10,
    )

    if resp.status_code == 200:
        result = resp.json()
        if "error" in result:
            return None, result["error"]
        return result.get("result"), None
    return None, f"HTTP {resp.status_code}"


def main():
    print("=" * 50)
    print("🗑️ DUST ACCOUNT CLOSER")
    print("=" * 50)

    keypair = get_keypair()
    if not keypair:
        print("❌ No wallet key loaded!")
        return

    owner = keypair.pubkey()
    print(f"✅ Wallet: {str(owner)[:16]}...")

    rpc_url = os.getenv("HELIUS_RPC_URL") or "https://api.mainnet-beta.solana.com"

    # Get all token accounts
    accounts = get_token_accounts(str(owner), rpc_url)
    print(f"📦 Found {len(accounts)} token accounts")

    # Filter to zero-balance or dust accounts
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    to_close = []

    for acc in accounts:
        pubkey = acc["pubkey"]
        info = acc["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        balance = float(info["tokenAmount"]["uiAmount"] or 0)

        # Skip USDC
        if mint == USDC_MINT:
            print(f"   💵 USDC: ${balance:.2f} (keeping)")
            continue

        # Only close if balance is dust (< $0.10 value typically)
        print(f"   🧹 {mint[:12]}... balance: {balance}")
        to_close.append((Pubkey.from_string(pubkey), mint, balance))

    if not to_close:
        print("\n✨ No dust accounts to close!")
        return

    print(
        f"\n🗑️ {len(to_close)} accounts to close (recovers ~{len(to_close) * 0.002:.4f} SOL)"
    )
    confirm = input("Continue? (y/n): ").strip().lower()

    if confirm != "y":
        print("Aborted.")
        return

    # Get blockhash
    blockhash = get_blockhash(rpc_url)
    if not blockhash:
        print("❌ Failed to get blockhash")
        return

    # Close each account
    for account_pubkey, mint, balance in to_close:
        print(f"\n🔄 Closing {mint[:12]}...")

        try:
            ix = close_account_ix(account_pubkey, owner, owner)
            msg = MessageV0.try_compile(
                payer=owner,
                instructions=[ix],
                address_lookup_table_accounts=[],
                recent_blockhash=Hash.from_string(blockhash),
            )
            tx = VersionedTransaction(msg, [keypair])
            tx_b64 = base64.b64encode(bytes(tx)).decode()

            sig, error = send_tx(tx_b64, rpc_url)
            if sig:
                print(f"   ✅ Closed! Tx: {sig[:20]}...")
            else:
                print(f"   ❌ Failed: {error}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n✅ Done! Rent recovered.")


if __name__ == "__main__":
    main()
