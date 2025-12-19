from dotenv import load_dotenv
load_dotenv()
from src.execution.wallet import WalletManager

manager = WalletManager()
if not manager.keypair:
    print("❌ Wallet not loaded")
    exit()

print(f"🔑 Wallet: {manager.get_public_key()}")
sol = manager.get_sol_balance()
print(f"⛽ SOL Balance: {sol:.6f} SOL")

BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
bonk = manager.get_balance(BONK)
print(f"🐕 BONK Balance: {bonk:,.2f}")
