"""
Debug Coinbase Key Format
=========================
Quick diagnostic to check if your .env credentials are formatted correctly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

print("\n" + "=" * 60)
print("  COINBASE CREDENTIALS DIAGNOSTIC")
print("=" * 60)

# Check Key Name
key_name = os.getenv("COINBASE_CLIENT_API_KEY", "")
print(f"\n[1] COINBASE_CLIENT_API_KEY:")
if not key_name:
    print("    ❌ NOT SET")
elif key_name.startswith("organizations/"):
    # Show masked version
    parts = key_name.split("/")
    if len(parts) >= 4:
        org_id = parts[1][:8] + "..." if len(parts[1]) > 8 else parts[1]
        key_id = parts[3][:8] + "..." if len(parts[3]) > 8 else parts[3]
        print(f"    ✅ Format OK: organizations/{org_id}/apiKeys/{key_id}")
        print(f"    Length: {len(key_name)} chars")
    else:
        print(f"    ⚠️  Unexpected format: {key_name[:30]}...")
else:
    print(f"    ❌ WRONG FORMAT")
    print(f"       Expected: organizations/ORG_ID/apiKeys/KEY_ID")
    print(f"       Got: {key_name[:40]}...")

# Check Private Key
priv_key = os.getenv("COINBASE_API_PRIVATE_KEY", "")
print(f"\n[2] COINBASE_API_PRIVATE_KEY:")
if not priv_key:
    print("    ❌ NOT SET")
else:
    has_header = "-----BEGIN EC PRIVATE KEY-----" in priv_key
    has_footer = "-----END EC PRIVATE KEY-----" in priv_key
    has_literal_backslash_n = "\\n" in priv_key
    has_real_newlines = "\n" in priv_key
    
    if has_header and has_footer:
        print(f"    ✅ PEM Header/Footer: Present")
    else:
        print(f"    ❌ PEM Header/Footer: Missing or malformed")
        print(f"       First 40 chars: {priv_key[:40]}...")
    
    if has_real_newlines:
        lines = priv_key.count("\n")
        print(f"    ✅ Contains {lines} newline characters")
    elif has_literal_backslash_n:
        print("    ❌ Contains LITERAL '\\n' instead of real newlines")
        print("       Fix: Wrap entire value in double quotes in .env file")
    else:
        print("    ⚠️  No newlines detected - key might be broken")
    
    print(f"    Total length: {len(priv_key)} chars")

# Check Phantom Address
phantom = os.getenv("PHANTOM_SOLANA_ADDRESS", "")
print(f"\n[3] PHANTOM_SOLANA_ADDRESS:")
if not phantom:
    print("    ❌ NOT SET - Required for withdrawals")
elif len(phantom) >= 32 and len(phantom) <= 44:
    print(f"    ✅ Set: {phantom[:4]}...{phantom[-4:]} ({len(phantom)} chars)")
else:
    print(f"    ❌ Invalid length: {len(phantom)} (expected 32-44)")

print("\n" + "=" * 60)
print("  REQUIRED FORMAT IN .env:")
print("=" * 60)
print('''
COINBASE_CLIENT_API_KEY="organizations/abc123.../apiKeys/def456..."
COINBASE_API_PRIVATE_KEY="-----BEGIN EC PRIVATE KEY-----\\nMHQCAQEE...\\n-----END EC PRIVATE KEY-----\\n"
PHANTOM_SOLANA_ADDRESS="YourSolanaWalletAddressHere"
''')
print("=" * 60 + "\n")
