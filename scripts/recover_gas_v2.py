import asyncio
import base64
from dotenv import load_dotenv

load_dotenv()

from config.settings import Settings
from src.execution.wallet import WalletManager
from src.system.smart_router import SmartRouter
from solana.rpc.api import Client
from solders.transaction import VersionedTransaction
from solana.rpc.types import TxOpts


async def recover():
    print("🚨 GAS RECOVERY V2 🚨")

    # 1. Setup
    manager = WalletManager()
    if not manager.keypair:
        print("❌ Keypair not found")
        return

    router = SmartRouter()

    BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    SOL = "So11111111111111111111111111111111111111112"

    # 2. Get Balance & Decimals
    info = manager.get_token_info(BONK)
    if not info or int(info["amount"]) == 0:
        print("❌ No BONK found to swap.")
        return

    amount_atomic = int(info["amount"])
    ui_amount = float(info["uiAmount"])
    print(f"💰 Found {ui_amount:,.2f} BONK ({amount_atomic} atomic)")

    # 3. Get Quote
    print("🔄 Getting Quote for BONK -> SOL (Aggressive)...")
    quote = router.get_jupiter_quote(
        BONK, SOL, amount_atomic, slippage_bps=500
    )  # 5% Slippage

    if not quote:
        print("❌ No quote found.")
        return

    out_sol = int(quote["outAmount"]) / 10**9
    print(f"✅ Quote: {out_sol:.6f} SOL")

    # 4. Build Tx
    payload = {
        "quoteResponse": quote,
        "userPublicKey": str(manager.keypair.pubkey()),
        "wrapAndUnwrapSol": True,
        "computeUnitPriceMicroLamports": 1000000,  # 1M MicroLamports (Aggressive)
    }

    print("🏗️ Building Transaction...")
    swap_data = router.get_swap_transaction(payload)
    if not swap_data:
        print("❌ Failed to build transaction")
        return

    # 5. Execute
    raw_tx = base64.b64decode(swap_data["swapTransaction"])
    tx = VersionedTransaction.from_bytes(raw_tx)
    signed_tx = VersionedTransaction(tx.message, [manager.keypair])

    print("🚀 Sending Transaction...")
    client = Client(Settings.RPC_URL)
    try:
        # Use simpler logic - just send and log.
        # Waiting for confirmation with modern solana-py can be tricky with async mixing.

        result = client.send_transaction(signed_tx, opts=TxOpts(skip_preflight=True))
        sig = result.value
        print(f"✅ SIG: {sig}")
        print("ℹ️ Check Solscan: https://solscan.io/tx/" + str(sig))
        print("⏳ Waiting 15s for confirmation...")
        await asyncio.sleep(15)

    except Exception as e:
        print(f"❌ Transaction failed: {e}")


if __name__ == "__main__":
    asyncio.run(recover())
