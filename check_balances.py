from dotenv import load_dotenv
load_dotenv()
from src.execution.wallet import WalletManager

manager = WalletManager()
if not manager.keypair:
    print("❌ Wallet not loaded")
    exit()

print(f"🔑 Wallet: {manager.get_public_key()}")
sol = manager.get_sol_balance()
print(f"⛽ Gas: {sol:.6f} SOL")

BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
bonk_info = manager.get_token_info(BONK)
if bonk_info:
    print(f"🐕 BONK: {bonk_info['uiAmount']}")

WSOL = "So11111111111111111111111111111111111111112"
wsol_info = manager.get_token_info(WSOL)
if wsol_info:
    print(f"◎ WSOL Account Found! Balance: {wsol_info['uiAmount']}")
else:
    print("❌ No open WSOL account found.")
    
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
usdc_info = manager.get_token_info(USDC)
if usdc_info:
    print(f"wb USDC: {usdc_info['uiAmount']}")
