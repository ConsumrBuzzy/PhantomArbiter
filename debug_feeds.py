import sys
import os
sys.path.append(os.getcwd())
try:
    from dotenv import load_dotenv
    load_dotenv()
except: pass

from src.arbitrage.feeds.jupiter_feed import JupiterFeed
from src.arbitrage.feeds.raydium_feed import RaydiumFeed
from src.arbitrage.feeds.orca_feed import OrcaFeed

def test():
    print("Test Start")
    try:
        jup = JupiterFeed()
        print("Jupiter Feed Initialized")
    except Exception as e:
        print(f"Jupiter Init Error: {e}")
        jup = None

    try:
        ray = RaydiumFeed()
        print("Raydium Feed Initialized")
    except Exception as e:
        print(f"Raydium Init Error: {e}")
        ray = None

    try:
        orca = OrcaFeed(use_on_chain=False)
        print("Orca Feed Initialized")
    except Exception as e:
        print(f"Orca Init Error: {e}")
        orca = None
    
    tokens = [
        ("DRIFT", "DriFtupWBXJK85kqq6PHJ7JISrguybIbY6bWHq9K51b"),
        ("KMNO", "KMNOxwnvJN6hCpuK4VVznMcKp3IV876WAroqCyGBTEp"),
        ("TNSR", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnC6Mio"),
        ("RENDER", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4kuzv95K"),
        ("RAY", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R") # Control
    ]
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    print("\nScanning Prices...")
    for name, mint in tokens:
        print(f"\n--- {name} ---")
        
        # Jupiter
        if jup:
            try:
                q = jup.get_quote(USDC, mint, 10.0)
                if q: print(f"  Jupiter: ${q.price:.4f}")
                else: print(f"  Jupiter: None")
            except Exception as e:
                print(f"  Jupiter: Error {e}")

        # Raydium (Uses DexScreener)
        if ray:
            try:
                q = ray.get_quote(USDC, mint, 10.0)
                if q: print(f"  Raydium: ${q.price:.4f}")
                else: print(f"  Raydium: None")
            except Exception as e: print(f"  Raydium: Error {e}")
            
        # Orca
        if orca:
            try:
                q = orca.get_quote(USDC, mint, 10.0)
                if q: print(f"  Orca:    ${q.price:.4f}")
                else: print(f"  Orca:    None")
            except Exception as e: print(f"  Orca:    Error {e}")

if __name__ == "__main__":
    test()
