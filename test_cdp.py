"""
Standalone Coinbase CDP Test
============================
Debugging script to isolate CCXT connection issues.
"""
import asyncio
import os
import ccxt.async_support as ccxt
from dotenv import load_dotenv

load_dotenv()

async def test_auth():
    print("--------------------------------------------------")
    print("Testing Coinbase CDP Authentication (Standalone)")
    print("--------------------------------------------------")
    
    api_key = os.getenv("COINBASE_CLIENT_API_KEY")
    private_key = os.getenv("COINBASE_API_PRIVATE_KEY")
    phantom = os.getenv("PHANTOM_SOLANA_ADDRESS")
    
    print(f"KEY: {api_key[:20]}..." if api_key else "KEY: NOT SET")
    print(f"PK:  {private_key[:30]}..." if private_key else "PK:  NOT SET")
    print(f"PHANTOM: {phantom[:10]}..." if phantom else "PHANTOM: NOT SET")
    
    if not api_key or not private_key:
        print("[!] Credentials missing in .env")
        return

    # Initialize CCXT with debug mode
    exchange = ccxt.coinbase({
        'apiKey': api_key,
        'secret': private_key,
        # 'verbose': True, # Disable verbose for cleaner output first
    })
    
    try:
        # fetch_time is a public endpoint - tests network
        print("\n[1] Testing Public Endpoint (Time)...")
        server_time = await exchange.fetch_time()
        print(f"[OK] Server Time: {server_time}")
        
        # fetch_accounts is private - tests auth
        print("\n[2] Testing Private Endpoint (Accounts)...")
        accounts = await exchange.fetch_accounts()
        print(f"[OK] Auth Success! Found {len(accounts)} accounts.")
        
        for acc in accounts:
            if float(acc.get('info', {}).get('available_balance', {}).get('value', 0)) > 0:
                print(f"   [+] {acc['code']}: {acc['info']['available_balance']['value']}")
                
    except ccxt.AuthenticationError as e:
        print(f"\n[X] AUTHENTICATION ERROR: {e}")
        print("   -> Check Key Permissions (View, Trade)")
        print("   -> Check Key Format")
    except Exception as e:
        print(f"\n[X] ERROR: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_auth())
