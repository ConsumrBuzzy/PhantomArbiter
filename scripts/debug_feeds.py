import sys
import os

sys.path.append(os.getcwd())
try:
    from dotenv import load_dotenv

    load_dotenv()
except:
    pass

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
        ("DRIFT", "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7"),
        ("KMNO", "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS"),
        ("TNSR", "TNSRxcUxoT9xBG3de7PiJyTDYu7kskLqcpddxnEJAS6"),
        ("RENDER", "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof"),
        ("RAY", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"),
    ]
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    print("\nScanning Prices...")
    for name, mint in tokens:
        print(f"\n--- {name} ---")

        # Jupiter
        if jup:
            try:
                # Debug V2 direct via requests (Bypass Router)
                import requests

                url = "https://api.jup.ag/price/v2"
                params = {"ids": mint, "vsToken": USDC}
                print(f"  Testing URL: {url}?ids={mint}&vsToken={USDC}")
                resp = requests.get(url, params=params, timeout=5)
                print(f"  Direct Resp: {resp.status_code}")
                if resp.status_code != 200:
                    print(f"  Body: {resp.text[:100]}")
                else:
                    print(f"  Body: {str(resp.json())[:100]}")

                q = jup.get_quote(USDC, mint, 10.0)
                if q:
                    print(f"  Jupiter: ${q.price:.4f}")
                else:
                    print("  Jupiter: None")
            except Exception as e:
                print(f"  Jupiter Error: {e}")

        # Raydium (Uses DexScreener)
        if ray:
            try:
                q = ray.get_quote(USDC, mint, 10.0)
                if q:
                    print(f"  Raydium: ${q.price:.4f}")
                else:
                    print("  Raydium: None")
            except Exception as e:
                print(f"  Raydium: Error {e}")

        # Orca
        if orca:
            try:
                q = orca.get_quote(USDC, mint, 10.0)
                if q:
                    print(f"  Orca:    ${q.price:.4f}")
                else:
                    print("  Orca:    None")
            except Exception as e:
                print(f"  Orca:    Error {e}")


if __name__ == "__main__":
    test()
