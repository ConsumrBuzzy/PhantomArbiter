import hashlib

def print_disc(name):
    h = hashlib.sha256(f"global:{name}".encode()).digest()[:8]
    print(f"{name}: {list(h)}")

print_disc("place_perp_order")
print_disc("place_order")
