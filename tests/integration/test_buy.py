
import os
import requests
import base64
import json
from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

# Load env variables
load_dotenv()
PRIVATE_KEY_STRING = os.getenv("SOLANA_PRIVATE_KEY", "").strip("'\"")
try:
    keypair = Keypair.from_base58_string(PRIVATE_KEY_STRING)
    print(f"✅ Wallet loaded: {keypair.pubkey()}")
except Exception as e:
    print(f"❌ Failed to load wallet: {e}")
    exit()

# Config
RPC_URL = "https://api.mainnet-beta.solana.com"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WIF_MINT = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
TEST_AMOUNT_USDC = 0.1  # $0.10 test buy
TEST_AMOUNT_LAMPORTS = int(TEST_AMOUNT_USDC * 1_000_000)

JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "").strip("'\"")
JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"
JUPITER_QUOTE_URL_PUBLIC = "https://public.jupiterapi.com/quote"
JUPITER_SWAP_URL_PUBLIC = "https://public.jupiterapi.com/swap"

def log(level, msg):
    print(f"[{level}] {msg}")

def execute_test_buy():
    # 1. Get Quote
    print("-" * 50)
    log("INFO", f"Getting quote for {TEST_AMOUNT_USDC} USDC -> WIF...")
    
    quote = None
    params = {
        "inputMint": USDC_MINT,
        "outputMint": WIF_MINT,
        "amount": str(TEST_AMOUNT_LAMPORTS),
        "slippageBps": "50"
    }

    # Try Authenticated API first
    try:
        headers = {"x-api-key": JUPITER_API_KEY}
        response = requests.get(JUPITER_QUOTE_URL, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            quote = response.json()
            log("INFO", "✅ Got quote from Auth API")
        else:
            log("WARN", f"Auth API failed ({response.status_code})")
    except Exception as e:
        log("WARN", f"Auth API error: {e}")

    # Fallback
    if not quote:
        try:
            log("INFO", "Trying Public API...")
            response = requests.get(JUPITER_QUOTE_URL_PUBLIC, params=params, timeout=10)
            if response.status_code == 200:
                quote = response.json()
                log("INFO", "✅ Got quote from Public API")
            else:
                log("ERROR", f"Public API failed: {response.text}")
                return
        except Exception as e:
            log("ERROR", f"Public API error: {e}")
            return

    if not quote:
        return

    log("INFO", f"Out Amount: {quote.get('outAmount')} WIF lamports")

    # 2. Get Swap Transaction
    swap_request = {
        "userPublicKey": str(keypair.pubkey()),
        "quoteResponse": quote,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto"
    }

    swap_data = None
    
    # Try Auth Swap
    try:
        response = requests.post(
            JUPITER_SWAP_URL,
            json=swap_request,
            headers={"Content-Type": "application/json", "x-api-key": JUPITER_API_KEY},
            timeout=30
        )
        if response.status_code == 200:
            swap_data = response.json()
            log("INFO", "✅ Got swap transaction from Auth API")
    except Exception as e:
        log("WARN", f"Auth Swap failed: {e}")

    # Fallback Swap
    if not swap_data:
        try:
            log("INFO", "Trying Public Swap API...")
            response = requests.post(
                JUPITER_SWAP_URL_PUBLIC,
                json=swap_request,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            if response.status_code == 200:
                swap_data = response.json()
                log("INFO", "✅ Got swap transaction from Public API")
            else:
                log("ERROR", f"Swap request failed: {response.text}")
                return
        except Exception as e:
            log("ERROR", f"Swap request error: {e}")
            return
            
    if not swap_data:
        return

    swap_transaction = swap_data.get("swapTransaction")
    if not swap_transaction:
        log("ERROR", "No swapTransaction in response")
        return

    # 3. Sign & Send
    try:
        tx_bytes = base64.b64decode(swap_transaction)
        transaction = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(transaction.message, [keypair])
        
        client = Client(RPC_URL)
        log("INFO", "🚀 Sending transaction to Solana...")
        
        # THIS IS THE KEY FIX: Using TxOpts()
        tx_sig = client.send_transaction(
            signed_tx,
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
        )
        
        if hasattr(tx_sig, 'value'):
            sig_str = str(tx_sig.value)
        else:
            sig_str = str(tx_sig)
            
        print("-" * 50)
        log("SUCCESS", f"Transaction submitted! Signature:")
        log("LINK", f"https://solscan.io/tx/{sig_str}")
        print("-" * 50)
        
    except Exception as e:
        log("ERROR", f"Transaction failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    execute_test_buy()
