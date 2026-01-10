from solders.pubkey import Pubkey
import hashlib

def print_disc(name):
    h = hashlib.sha256(f"global:{name}".encode()).digest()[:8]
    print(f"{name}: {list(h)}")

# Calc discriminators
print_disc("place_perp_order")
print_disc("place_order")

# Check State PDA
DRIFT_PID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
state, bump = Pubkey.find_program_address([b"drift_state"], DRIFT_PID)
print(f"Derived State: {state}")
print(f"Hardcoded:     DfYCNezifxAEsQamrAH2R8CgqMKLb6VpfHEV6r9n4MCz")
