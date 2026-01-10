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
