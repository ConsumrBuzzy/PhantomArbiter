from solders.pubkey import Pubkey
import hashlib

def print_disc(name):
    h = hashlib.sha256(f"global:{name}".encode()).digest()[:8]
    print(f"{name}: {list(h)}")

print_disc("place_perp_order")
print_disc("place_order")
print_disc("place_orders")
print_disc("place_perp_orders")
print_disc("initialize_user")
print_disc("initialize_user_stats")

# Check State
DRIFT_PID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
state, _ = Pubkey.find_program_address([b"drift_state"], DRIFT_PID)
print(f"Derived State: {state}")
print(f"Hardcoded:     DfYCNezifxAEsQamrAH2R8CgqMKLb6VpfHEV6r9n4MCz")

import os
from dotenv import load_dotenv
from solders.keypair import Keypair

load_dotenv()
pk_str = os.getenv("SOLANA_PRIVATE_KEY")
if pk_str:
    try:
        if "[" in pk_str:
            import json
            kp = Keypair.from_bytes(json.loads(pk_str))
        else:
            kp = Keypair.from_base58_string(pk_str)
        wallet = kp.pubkey()
        print(f"Wallet: {wallet}")

        # Derive User
        user, _ = Pubkey.find_program_address([b"user", bytes(wallet), (0).to_bytes(2, "little")], DRIFT_PID)
        print(f"User PDA: {user}")

        # Derive UserStats
        stats, _ = Pubkey.find_program_address([b"user_stats", bytes(wallet)], DRIFT_PID)
        print(f"UserStats PDA: {stats}")
    except Exception as e:
        print(f"Wallet load error: {e}")
