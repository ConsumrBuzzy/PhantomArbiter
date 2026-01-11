"""
Coinbase API Connectivity Check
===============================
Verifies CDP/JWT authentication is working by fetching balance.

Usage:
    python check_api_connectivity.py

Expected Output (Success):
    ✅ Coinbase CDP API Connected
    💰 USDC Balance: $XX.XX

Expected Output (Failure):
    ❌ Connection failed: [error message]
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def main():
    print("=" * 60)
    print("Coinbase CDP/JWT Connectivity Check")
    print("=" * 60)
    
    try:
        from src.drivers.coinbase_driver import get_coinbase_driver
        
        driver = get_coinbase_driver()
        
        # Check configuration
        if not driver.is_configured:
            print("\n❌ Coinbase CDP credentials not configured!")
            print("\nPlease set in .env:")
            print("  COINBASE_CLIENT_API_KEY='organizations/.../apiKeys/...'")
            print("  COINBASE_API_PRIVATE_KEY='-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----'")
            return
        
        print(f"\n📡 API Key: {driver._api_key_name[:40]}...")
        print(f"🔐 Private Key: {'*' * 20} (configured)")
        print(f"🎯 Phantom Address: {driver.phantom_address}")
        
        # Test connectivity
        print("\n⏳ Testing API connection...")
        result = await driver.check_api_connectivity()
        
        if result['status'] == 'connected':
            print(f"\n✅ Coinbase CDP API Connected!")
            print(f"💰 USDC Balance: ${result['usdc_balance']:.2f}")
            print(f"🔑 Auth Method: {result['auth_method']}")
        else:
            print(f"\n❌ Connection failed: {result.get('error', 'Unknown error')}")
        
        # Cleanup
        await driver.close()
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("Make sure CCXT is installed: pip install ccxt>=4.1.0")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
