"""
Test Phantom Configuration
==========================
Verify the bot's internal Solana wallet (Signer) is working.
"""
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

def test_wallet_load():
    print("--------------------------------------------------")
    print("Testing Bot Wallet (Signer)")
    print("--------------------------------------------------")
    
    # Check env var existence (masked)
    pk = os.getenv("SOLANA_PRIVATE_KEY", "")
    if not pk:
        print("❌ SOLANA_PRIVATE_KEY is missing in .env")
        return
        
    print(f"Key Length: {len(pk)} chars")
    
    try:
        from src.drivers.wallet_manager import WalletManager
        wm = WalletManager()
        
        if wm.keypair:
            pubkey = wm.get_public_key()
            print(f"✅ Wallet Loaded Successfully!")
            print(f"🔑 Public Address: {pubkey}")
            
            # Check if this matches the Configured Receiver
            receiver = os.getenv("PHANTOM_SOLANA_ADDRESS", "")
            print(f"\nChecking Bridge Receiver Config...")
            if receiver == pubkey:
                print("✅ PHANTOM_SOLANA_ADDRESS matches Bot Wallet.")
            else:
                print(f"⚠️  PHANTOM_SOLANA_ADDRESS ({receiver[:10]}...) does NOT match Bot Wallet ({pubkey[:10]}...).")
                print("   (This is OK if you want to bridge to a different cold wallet, but usually they are the same)")
                
                if len(receiver) > 50:
                    print("❌ Receiver address is too long! Did you paste a Private Key here?")
        else:
            print("❌ Failed to load Keypair (Unknown error)")
            
    except Exception as e:
        print(f"❌ Error loading WalletManager: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_wallet_load()
