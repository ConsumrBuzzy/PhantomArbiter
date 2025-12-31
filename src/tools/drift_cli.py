"""
Drift Transfer CLI
==================
CLI utility for depositing/withdrawing USDC to/from Drift Protocol.

Uses Drift's UI gateway for transactions (simpler than SDK, avoids platform issues).

Usage:
    python -m src.tools.drift_cli balance
    python -m src.tools.drift_cli deposit 10
    python -m src.tools.drift_cli withdraw 5

Or via main.py:
    python main.py drift balance
    python main.py drift deposit 10
    python main.py drift withdraw 5
"""

import os
import sys
import base64
import requests
from typing import Optional
from dataclasses import dataclass

# Add project root to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Load .env file
from dotenv import load_dotenv

load_dotenv(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
)

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client as SolanaClient
from src.shared.system.logging import Logger


# Constants
DRIFT_API_URL = "https://drift-gateway-api.mainnet.drift.trade"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6


@dataclass
class DriftBalance:
    """Drift account balance."""

    usdc: float
    free_collateral: float
    total_collateral: float


def load_wallet() -> Keypair:
    """Load wallet keypair from environment (same as wallet.py)."""
    pk = os.getenv("SOLANA_PRIVATE_KEY")
    if not pk:
        raise ValueError("SOLANA_PRIVATE_KEY environment variable not set")

    try:
        return Keypair.from_base58_string(pk)
    except Exception as e:
        raise ValueError(f"Invalid SOLANA_PRIVATE_KEY format: {e}")


def get_rpc_client() -> SolanaClient:
    """Get Solana RPC client."""
    rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
    return SolanaClient(rpc_url)


def get_drift_balance(wallet_pubkey: str) -> Optional[DriftBalance]:
    """Fetch Drift account balance via API."""
    try:
        # Drift API endpoint for user account
        url = f"{DRIFT_API_URL}/v1/user/{wallet_pubkey}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            Logger.warning(f"[DRIFT] API returned {response.status_code}")
            return None

        data = response.json()

        # Extract USDC balance from spot positions
        usdc_balance = 0.0
        for spot in data.get("spotPositions", []):
            if spot.get("marketIndex") == 0:  # USDC is market 0
                usdc_balance = float(spot.get("scaledBalance", 0)) / (10**USDC_DECIMALS)
                break

        free_collateral = float(data.get("freeCollateral", 0)) / (10**USDC_DECIMALS)
        total_collateral = float(data.get("totalCollateralValue", 0)) / (
            10**USDC_DECIMALS
        )

        return DriftBalance(
            usdc=usdc_balance,
            free_collateral=free_collateral,
            total_collateral=total_collateral,
        )

    except Exception as e:
        Logger.error(f"[DRIFT] Balance fetch failed: {e}")
        return None


def request_deposit_tx(wallet_pubkey: str, amount_usd: float) -> Optional[str]:
    """Request deposit transaction from Drift gateway."""
    try:
        url = f"{DRIFT_API_URL}/v1/deposit"
        payload = {
            "user": wallet_pubkey,
            "spotMarketIndex": 0,  # USDC
            "amount": int(amount_usd * (10**USDC_DECIMALS)),
        }

        response = requests.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            Logger.error(f"[DRIFT] Deposit API error: {response.text}")
            return None

        data = response.json()
        return data.get("transaction")  # Base64 encoded transaction

    except Exception as e:
        Logger.error(f"[DRIFT] Deposit request failed: {e}")
        return None


def request_withdraw_tx(wallet_pubkey: str, amount_usd: float) -> Optional[str]:
    """Request withdrawal transaction from Drift gateway."""
    try:
        url = f"{DRIFT_API_URL}/v1/withdraw"
        payload = {
            "user": wallet_pubkey,
            "spotMarketIndex": 0,  # USDC
            "amount": int(amount_usd * (10**USDC_DECIMALS)),
        }

        response = requests.post(url, json=payload, timeout=30)

        if response.status_code != 200:
            Logger.error(f"[DRIFT] Withdraw API error: {response.text}")
            return None

        data = response.json()
        return data.get("transaction")

    except Exception as e:
        Logger.error(f"[DRIFT] Withdraw request failed: {e}")
        return None


def sign_and_send_tx(
    tx_base64: str, keypair: Keypair, rpc: SolanaClient
) -> Optional[str]:
    """Sign and send a transaction."""
    try:
        # Decode transaction
        tx_bytes = base64.b64decode(tx_base64)
        tx = VersionedTransaction.from_bytes(tx_bytes)

        # Sign
        tx.sign([keypair])

        # Send
        result = rpc.send_transaction(tx)

        if result.value:
            return str(result.value)

        return None

    except Exception as e:
        Logger.error(f"[DRIFT] TX send failed: {e}")
        return None


def cmd_balance():
    """Show Drift balance."""
    keypair = load_wallet()
    wallet_pubkey = str(keypair.pubkey())

    print(f"\n📊 Fetching Drift balance for {wallet_pubkey[:8]}...")

    balance = get_drift_balance(wallet_pubkey)

    if balance:
        print("\n💰 Drift Account Balance:")
        print(f"   USDC Balance:     ${balance.usdc:.2f}")
        print(f"   Free Collateral:  ${balance.free_collateral:.2f}")
        print(f"   Total Collateral: ${balance.total_collateral:.2f}")
    else:
        print("❌ Could not fetch balance")


def cmd_deposit(amount: float):
    """Deposit USDC to Drift."""
    if amount <= 0:
        print("❌ Amount must be positive")
        return

    keypair = load_wallet()
    wallet_pubkey = str(keypair.pubkey())
    rpc = get_rpc_client()

    print(f"\n💰 Depositing ${amount:.2f} USDC to Drift...")

    tx_b64 = request_deposit_tx(wallet_pubkey, amount)
    if not tx_b64:
        print("❌ Failed to create deposit transaction")
        return

    tx_sig = sign_and_send_tx(tx_b64, keypair, rpc)
    if tx_sig:
        print("✅ Deposit successful!")
        print(f"   TX: https://solscan.io/tx/{tx_sig}")
    else:
        print("❌ Transaction failed")


def cmd_withdraw(amount: float):
    """Withdraw USDC from Drift."""
    if amount <= 0:
        print("❌ Amount must be positive")
        return

    keypair = load_wallet()
    wallet_pubkey = str(keypair.pubkey())
    rpc = get_rpc_client()

    print(f"\n💸 Withdrawing ${amount:.2f} USDC from Drift...")

    tx_b64 = request_withdraw_tx(wallet_pubkey, amount)
    if not tx_b64:
        print("❌ Failed to create withdrawal transaction")
        return

    tx_sig = sign_and_send_tx(tx_b64, keypair, rpc)
    if tx_sig:
        print("✅ Withdrawal successful!")
        print(f"   TX: https://solscan.io/tx/{tx_sig}")
    else:
        print("❌ Transaction failed")


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("""
Drift Transfer CLI
==================
Usage:
  drift_cli.py balance            Check Drift balance
  drift_cli.py deposit <amount>   Deposit USDC to Drift
  drift_cli.py withdraw <amount>  Withdraw USDC from Drift

Examples:
  python -m src.tools.drift_cli balance
  python -m src.tools.drift_cli deposit 10
  python -m src.tools.drift_cli withdraw 5
        """)
        return

    command = sys.argv[1].lower()
    amount = float(sys.argv[2]) if len(sys.argv) > 2 else 0

    if command == "balance":
        cmd_balance()
    elif command == "deposit":
        cmd_deposit(amount)
    elif command == "withdraw":
        cmd_withdraw(amount)
    else:
        print(f"❌ Unknown command: {command}")


if __name__ == "__main__":
    main()
