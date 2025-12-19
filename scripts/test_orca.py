"""Test Orca Adapter PDA Derivation"""
import sys
sys.path.insert(0, ".")

from src.liquidity.orca_adapter import get_orca_adapter, SOL_MINT, USDC_MINT

print("\n🐋 Orca Adapter Test")
print("=" * 50)

adapter = get_orca_adapter()

# Test with known working pool address from Orca website
KNOWN_SOL_USDC_POOL = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"

print(f"\n🔍 Testing with known pool: {KNOWN_SOL_USDC_POOL[:16]}...")
state = adapter.get_whirlpool_state(KNOWN_SOL_USDC_POOL)

if state:
    print(f"\n✅ SUCCESS!")
    print(f"   Address: {state.address}")
    print(f"   Price: ${state.price:.4f}")
    print(f"   Tick: {state.tick_current}")
    print(f"   Fee: {state.fee_rate / 10000:.2f}%")
    print(f"   Liquidity: {state.liquidity:,}")
    print(f"   Token A: {state.token_mint_a[:16]}...")
    print(f"   Token B: {state.token_mint_b[:16]}...")
else:
    print("\n❌ No pool found")
