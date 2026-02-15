import psutil
import time
from solana.rpc.api import Client
from solders.pubkey import Pubkey

# Thresholds
MIN_SOL_BALANCE = 0.15
TARGET_PROCESS = "python.exe" # Simplified match, will check cmdline
SCRIPT_NAME = "star_atlas_bridge_and_run.py"

# Config
# Ideally load from .env, but for kill switch hardcoding the public key is safer than parsing errors
# Wallet: B5e2... (User's Wallet)
# We will use the Ironforge RPC to check balance
RPC_URL = "https://rpc.ironforge.network/mainnet?apiKey=01HZFJ18Q9E3QT62P67P52PC03"

def get_wallet_address():
    """Try to get wallet address from keypair file if possible."""
    try:
        # Assuming the path is correct relative to execution from root
        import sys
        sys.path.append('src') # Add src to path
        from shared.infrastructure.wallet_manager import WalletManager
        wm = WalletManager()
        return str(wm.keypair.pubkey())
    except Exception as e:
        print(f"⚠️  Wallet Load Error: {e}")
        return None

def kill_process():
    print(f"\n🚨 KILL SIGNAL ACTIVATED!")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == TARGET_PROCESS and SCRIPT_NAME in ' '.join(proc.info['cmdline'] or []):
                print(f"   Terminating PID {proc.info['pid']} ({SCRIPT_NAME})...")
                proc.terminate()
                print("   ✅ Process Terminated.")
                return
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    print("   ⚠️  Process not found.")

def monitor():
    print("=== 🛡️ STAR ATLAS KILL SWITCH ACTIVE ===")
    
    wallet = get_wallet_address()
    if not wallet:
        print("❌ Could not load wallet address. Exiting.")
        return

    print(f"   Monitoring Wallet: {wallet}")
    print(f"   Min Balance: {MIN_SOL_BALANCE} SOL")
    
    client = Client(RPC_URL)
    
    while True:
        try:
            balance_lamports = client.get_balance(Pubkey.from_string(wallet)).value
            balance_sol = balance_lamports / 1e9
            
            print(f"   Current Balance: {balance_sol:.4f} SOL", end='\r')
            
            if balance_sol < MIN_SOL_BALANCE:
                print(f"\n   ❌ BALANCE CRITICAL (< {MIN_SOL_BALANCE})")
                kill_process()
                break
                
            time.sleep(10) # Check every 10s
            
        except Exception as e:
            print(f"\n   ⚠️  RPC Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    monitor()
