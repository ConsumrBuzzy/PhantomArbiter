"""
Send SOL Payment for Tensor API Access
=======================================
Sends 19873 lamports (~0.000019873 SOL) to Tensor API payment address.
"""

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

import time
from dotenv import load_dotenv
from solders.keypair import Keypair

# Load environment variables
load_dotenv()
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.api import Client
from solana.rpc.types import TxOpts

# Configuration
TENSOR_PAYMENT_ADDRESS = "7NWgPbshWRR1jxhN9mXkhDS4kzKBhp8rSFFYDkVWU9bb"
PAYMENT_AMOUNT_LAMPORTS = 19873
RPC_ENDPOINT = "https://api.mainnet-beta.solana.com"

def main():
    print("=" * 70)
    print("TENSOR API ACCESS PAYMENT")
    print("=" * 70)
    print(f"Destination: {TENSOR_PAYMENT_ADDRESS}")
    print(f"Amount: {PAYMENT_AMOUNT_LAMPORTS} lamports (~{PAYMENT_AMOUNT_LAMPORTS / 1e9:.9f} SOL)")
    print("=" * 70)
    print()

    # Load wallet
    private_key = os.getenv("SOLANA_PRIVATE_KEY")
    if not private_key:
        print("[X] Error: SOLANA_PRIVATE_KEY environment variable not set")
        print("[!] Please set your private key:")
        print("    set SOLANA_PRIVATE_KEY=your_base58_private_key")
        return

    try:
        keypair = Keypair.from_base58_string(private_key)
        sender_pubkey = keypair.pubkey()
        print(f"[OK] Wallet loaded: {sender_pubkey}")
    except Exception as e:
        print(f"[X] Error loading wallet: {e}")
        return

    # Initialize RPC client
    client = Client(RPC_ENDPOINT)

    # Check balance
    try:
        balance_response = client.get_balance(sender_pubkey)
        balance_lamports = balance_response.value
        balance_sol = balance_lamports / 1e9

        print(f"[WALLET] Current balance: {balance_lamports:,} lamports ({balance_sol:.9f} SOL)")

        if balance_lamports < PAYMENT_AMOUNT_LAMPORTS + 5000:  # +5000 for fee
            print(f"[X] Insufficient balance. Need at least {(PAYMENT_AMOUNT_LAMPORTS + 5000) / 1e9:.9f} SOL")
            return
    except Exception as e:
        print(f"[X] Error checking balance: {e}")
        return

    # Confirm transaction
    print()
    print("[!] CONFIRM TRANSACTION:")
    print(f"    From: {sender_pubkey}")
    print(f"    To:   {TENSOR_PAYMENT_ADDRESS}")
    print(f"    Amount: {PAYMENT_AMOUNT_LAMPORTS} lamports")
    print()

    confirm = input("Proceed with payment? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("[X] Transaction cancelled")
        return

    # Build transaction
    try:
        recipient_pubkey = Pubkey.from_string(TENSOR_PAYMENT_ADDRESS)

        # Create transfer instruction
        transfer_ix = transfer(
            TransferParams(
                from_pubkey=sender_pubkey,
                to_pubkey=recipient_pubkey,
                lamports=PAYMENT_AMOUNT_LAMPORTS
            )
        )

        # Get recent blockhash
        latest_blockhash = client.get_latest_blockhash().value.blockhash

        # Compile message
        msg = MessageV0.try_compile(
            payer=sender_pubkey,
            instructions=[transfer_ix],
            address_lookup_table_accounts=[],
            recent_blockhash=latest_blockhash,
        )

        # Create and sign transaction
        tx = VersionedTransaction(msg, [keypair])

        print()
        print("[TX] Sending transaction...")

        # Send transaction
        response = client.send_transaction(
            tx,
            opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed")
        )

        signature = response.value
        print(f"[OK] Transaction sent!")
        print(f"     Signature: {signature}")
        print()
        print(f"[LINK] Solscan:")
        print(f"       https://solscan.io/tx/{signature}")
        print()

        # Wait for confirmation
        print("[...] Waiting for confirmation...")
        time.sleep(3)

        confirmation = client.get_signature_statuses([signature])
        if confirmation.value[0]:
            print("[OK] Transaction confirmed!")
        else:
            print("[!] Confirmation pending - check Solscan link above")

        # Check new balance
        new_balance = client.get_balance(sender_pubkey).value
        new_balance_sol = new_balance / 1e9
        print()
        print(f"[WALLET] New balance: {new_balance:,} lamports ({new_balance_sol:.9f} SOL)")
        print()
        print("=" * 70)
        print("NEXT STEP: Paste the Solscan link to Tensor to receive your API key")
        print("=" * 70)

    except Exception as e:
        print(f"[X] Transaction failed: {e}")
        import traceback
        traceback.print_exc()
        return

if __name__ == "__main__":
    main()
