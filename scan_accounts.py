from dotenv import load_dotenv
load_dotenv()
from src.execution.wallet import WalletManager
from src.system.rpc_pool import get_rpc_pool

manager = WalletManager()
pool = get_rpc_pool()

print(f"🔑 Wallet: {manager.get_public_key()}")

# Get all token accounts
result = pool.rpc_call("getTokenAccountsByOwner", [
    str(manager.keypair.pubkey()),
    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
    {"encoding": "jsonParsed"}
])

if result and "value" in result:
    accounts = result["value"]
    print(f"📦 Found {len(accounts)} Token Accounts:")
    
    for acc in accounts:
        pubkey = acc["pubkey"]
        info = acc["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        amount = float(info["tokenAmount"]["uiAmount"])
        decimals = info["tokenAmount"]["decimals"]
        
        state = acc["account"]["data"]["parsed"]["info"]["state"]
        
        # Identify known tokens
        name = "Unknown"
        if mint == "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": name = "BONK"
        if mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": name = "USDC"
        if mint == "So11111111111111111111111111111111111111112": name = "WSOL"
        
        status = "✅ KEEP"
        if amount == 0:
            status = "♻️  RECLAIMABLE (Rent ~0.002 SOL)"
            
        print(f"   • {name:<8} {amount:>12.4f} | {pubkey} | {status}")
else:
    print("❌ Failed to fetch accounts")
