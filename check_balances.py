from dotenv import load_dotenv
load_dotenv()
from src.execution.wallet import WalletManager

manager = WalletManager()
if not manager.keypair:
    print("❌ Wallet not loaded")
    exit()

print(f"🔑 Wallet: {manager.get_public_key()}")
sol_balance = manager.get_sol_balance()
print(f"⛽ Gas: {sol_balance:.6f} SOL")
    
# Check Common Tokens specifically
usdc_bal = manager.get_balance("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
print(f"💵 USDC: {usdc_bal:.6f}")

bonk_bal = manager.get_balance("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
print(f"🐕 BONK: {bonk_bal:.6f}")

wif_bal = manager.get_balance("EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm")
print(f"🎩 WIF:  {wif_bal:.6f}")

# Generic Scan for others
print("\n� Scanning for OTHER tokens...")
# (Using the scan logic from run_trader/wallet)
try:
    import requests
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [
            str(manager.keypair.pubkey()),
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }
    res = requests.post("https://api.mainnet-beta.solana.com", json=payload).json()
    if "result" in res:
        for acc in res["result"]["value"]:
            info = acc["account"]["data"]["parsed"]["info"]
            mint = info["mint"]
            amount = float(info["tokenAmount"]["uiAmount"])
            if amount > 0:
                print(f"   - {mint[:4]}...{mint[-4:]}: {amount}")
except Exception as e:
    print(f"Scan error: {e}")
