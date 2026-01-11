"""
Fix .env Configuration
======================
Automatically detects and fixes common configuration errors:
1. Swaps Private Key if placed in Public Address field.
2. Ensures correct Coinbase Key formatting.
3. Restores missing variables.
"""
import os
import sys
from dotenv import dotenv_values

def fix_env_file():
    print("🔧 Analyzing .env configuration...")
    
    # Read raw values (no interpretation)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        print("❌ no .env file found!")
        return

    # Load current values
    config = dotenv_values(env_path)
    
    # New config builder
    new_config = {}
    
    # 1. Capture Coinbase Keys
    cb_key = config.get("COINBASE_CLIENT_API_KEY", "")
    cb_secret = config.get("COINBASE_API_PRIVATE_KEY", "")
    
    # Check for legacy swap (Key Name in Secret var?)
    if cb_secret.startswith("organizations/"):
        print("   -> Found Key Name in PRIVATE_KEY variable. Swapping...")
        temp = cb_key
        cb_key = cb_secret
        cb_secret = temp
        
    # Check for empty Key Name
    if not cb_key and config.get("COINBASE_API_KEY_NAME"):
         cb_key = config.get("COINBASE_API_KEY_NAME")

    new_config["COINBASE_CLIENT_API_KEY"] = cb_key
    new_config["COINBASE_API_PRIVATE_KEY"] = cb_secret
    
    # 2. Fix Phantom Keys
    sol_priv = config.get("SOLANA_PRIVATE_KEY", "")
    phantom_addr = config.get("PHANTOM_SOLANA_ADDRESS", "")
    
    # DETECT: Private Key inside Public Address field?
    if len(phantom_addr) > 60:
        print("   -> Detected PRIVATE KEY in 'PHANTOM_SOLANA_ADDRESS' field.")
        print("   -> Moving it to 'SOLANA_PRIVATE_KEY'.")
        sol_priv = phantom_addr  # Move it
        phantom_addr = ""        # Clear public field for now
        
    # DERIVE: If we have Private Key but no Public Address, derive it!
    if sol_priv and not phantom_addr:
        try:
            from solders.keypair import Keypair
            kp = Keypair.from_base58_string(sol_priv)
            pubkey = str(kp.pubkey())
            print(f"   -> Derived Public Address from Private Key: {pubkey}")
            phantom_addr = pubkey
        except ImportError:
            print("   ⚠️  Could not import 'solders' to derive key. Please run 'pip install solders'.")
        except Exception as e:
            print(f"   ⚠️  Could not derive public key: {e}")

    new_config["SOLANA_PRIVATE_KEY"] = sol_priv
    new_config["PHANTOM_SOLANA_ADDRESS"] = phantom_addr
    
    # 3. Preserve other standard settings
    defaults = {
        "MIN_BRIDGE_AMOUNT_USD": "5.00",
        "CEX_DUST_FLOOR_USD": "1.00",
        "TELEGRAM_BOT_TOKEN": config.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": config.get("TELEGRAM_CHAT_ID", ""),
        "RPC_URL": config.get("RPC_URL", "https://api.mainnet-beta.solana.com"),
    }
    
    for k, v in defaults.items():
        if k not in new_config: # Don't overwrite if likely already handled
             new_config[k] = config.get(k, v)

    # 4. Write back to .env
    print("💾 Writing fixed .env file...")
    with open(env_path, 'w') as f:
        for k, v in new_config.items():
            # Ensure proper quoting for multiline keys
            if "\n" in str(v) or "-----BEGIN" in str(v):
                # Ensure literal \n are preserved if read that way
                val = str(v).replace("\n", "\\n") if "\\n" not in str(v) else str(v)
                f.write(f'{k}="{val}"\n')
            else:
                f.write(f'{k}="{v}"\n')
                
    print("✅ .env file has been repaired.")
    print(f"   Public Address detected as: {phantom_addr}")

if __name__ == "__main__":
    fix_env_file()
