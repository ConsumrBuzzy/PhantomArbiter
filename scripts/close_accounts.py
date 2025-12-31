import asyncio
from dotenv import load_dotenv

load_dotenv()

from src.execution.wallet import WalletManager
from src.system.rpc_pool import get_rpc_pool
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.types import TxOpts
from spl.token.instructions import close_account, CloseAccountParams
from spl.token.constants import TOKEN_PROGRAM_ID


async def reclaim_rent():
    print("♻️  RENT RECLAIMER STARTED")

    manager = WalletManager()
    pool = get_rpc_pool()
    wallet_pubkey = manager.keypair.pubkey()

    print(f"🔑 Wallet: {wallet_pubkey}")

    # 1. Find Empty Accounts
    print("🔍 Scanning for empty accounts...")

    # Use RPC to find accounts again
    result = pool.rpc_call(
        "getTokenAccountsByOwner",
        [
            str(wallet_pubkey),
            {"programId": str(TOKEN_PROGRAM_ID)},
            {"encoding": "jsonParsed"},
        ],
    )

    if not result or "value" not in result:
        print("❌ Failed to scan accounts")
        return

    accounts_to_close = []
    for acc in result["value"]:
        pubkey_str = acc["pubkey"]
        info = acc["account"]["data"]["parsed"]["info"]
        amount = float(info["tokenAmount"]["uiAmount"])

        if amount == 0:
            accounts_to_close.append(Pubkey.from_string(pubkey_str))
            print(f"   found empty: {pubkey_str}")

    if not accounts_to_close:
        print("✅ No empty accounts found.")
        return

    print(f"📦 Found {len(accounts_to_close)} reclaimable accounts.")
    print(f"💰 Potential Recovery: ~{len(accounts_to_close) * 0.002:.4f} SOL")

    # 2. Build Close Instructions
    instructions = []

    # Limit to 5 at a time to fit in transaction
    batch = accounts_to_close[:5]

    for acc_pubkey in batch:
        # Create Close Account Instruction
        # close_account(params: CloseAccountParams) -> Instruction

        ix = close_account(
            CloseAccountParams(
                account=acc_pubkey,
                dest=wallet_pubkey,
                owner=wallet_pubkey,
                program_id=TOKEN_PROGRAM_ID,
                signers=[],
            )
        )
        instructions.append(ix)

    # 3. Send Transaction
    print("🚀 Sending Reclaim Transaction...")

    client = Client("https://api.mainnet-beta.solana.com")
    latest_blockhash = client.get_latest_blockhash().value.blockhash

    # Compile Message
    msg = MessageV0.try_compile(
        payer=wallet_pubkey,
        instructions=instructions,
        address_lookup_table_accounts=[],
        recent_blockhash=latest_blockhash,
    )

    tx = VersionedTransaction(msg, [manager.keypair])

    try:
        sig = client.send_transaction(tx, opts=TxOpts(skip_preflight=True)).value
        print(f"✅ SIG: {sig}")
        print("⏳ Waiting for confirmation...")
        await asyncio.sleep(10)
        print("🎉 Done! Check balance.")

    except Exception as e:
        print(f"❌ Failed: {e}")


if __name__ == "__main__":
    asyncio.run(reclaim_rent())
