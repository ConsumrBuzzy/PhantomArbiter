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

# Full Watchlist (12 Tokens)
tokens = [
    ("BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"),
    ("WIF",  "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"),
    ("JUP",  "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"),
    ("RAY",  "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"),
    ("JTO",  "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL"),
    ("PYTH", "HZ1JovNiVvGrGNiiYvEozEVGZ58xaU3RKwX8eACQBCt3"),
    ("POPCAT", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"),
    ("DRIFT", "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7"),
    ("KMNO", "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS"),
    ("TNSR", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6"),
    ("RENDER", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof"),
]

for symbol, mint in tokens:
    bal = manager.get_balance(mint)
    icon = "🪙"
    if symbol == "BONK": icon = "🐕"
    elif symbol == "WIF": icon = "🎩"
    elif symbol == "RAY": icon = "Ray"
    
    print(f"{icon} {symbol:<6}: {bal:f}")

# Generic Scan for others
print("\n Scanning for OTHER tokens...")
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
