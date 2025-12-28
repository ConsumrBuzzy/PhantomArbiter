"""
Test Suite: Tick Array Manager (Phase 19)
==========================================
Verifies CLMM pool state parsing and tick array PDA derivation.

Run: pytest tests/test_tick_array_manager.py -v
"""

import pytest


def test_tick_array_imports():
    """Verify Tick Array Manager functions are available."""
    import phantom_core
    
    assert hasattr(phantom_core, 'ClmmPoolInfo')
    assert hasattr(phantom_core, 'parse_clmm_pool_state')
    assert hasattr(phantom_core, 'derive_tick_arrays')
    assert hasattr(phantom_core, 'derive_tick_arrays_extended')
    assert hasattr(phantom_core, 'sqrt_price_to_tick')
    assert hasattr(phantom_core, 'tick_to_sqrt_price')


def test_sqrt_price_to_tick():
    """Test sqrt_price → tick conversion."""
    import phantom_core
    
    # Q64.64 representation of sqrt(1.0) = 2^64
    sqrt_price_1_0 = 1 << 64
    tick = phantom_core.sqrt_price_to_tick(sqrt_price_1_0)
    
    # sqrt_price = 1.0 should give tick ≈ 0
    assert abs(tick) <= 1, f"Expected tick ≈ 0, got {tick}"
    
    print(f"\nsqrt_price=2^64 (price=1.0) → tick={tick}")


def test_tick_to_sqrt_price():
    """Test tick → sqrt_price conversion."""
    import phantom_core
    
    # Tick 0 should give sqrt_price ≈ 2^64
    sqrt_price = phantom_core.tick_to_sqrt_price(0)
    expected = 1 << 64
    
    # Allow 0.1% error
    error_pct = abs(sqrt_price - expected) / expected * 100
    assert error_pct < 0.1, f"Expected ~{expected}, got {sqrt_price} ({error_pct:.3f}% error)"
    
    print(f"\ntick=0 → sqrt_price={sqrt_price} (expected ~{expected})")


def test_tick_roundtrip():
    """Test tick → sqrt_price → tick roundtrip."""
    import phantom_core
    
    test_ticks = [-100000, -10000, -1000, 0, 1000, 10000, 100000]
    
    for original in test_ticks:
        sqrt_price = phantom_core.tick_to_sqrt_price(original)
        recovered = phantom_core.sqrt_price_to_tick(sqrt_price)
        
        # Allow +/- 1 due to rounding
        assert abs(recovered - original) <= 1, \
            f"Roundtrip failed: {original} → {sqrt_price} → {recovered}"
    
    print(f"\nRoundtrip test passed for ticks: {test_ticks}")


def test_derive_tick_arrays_a_to_b():
    """Test tick array derivation for A→B swap."""
    import phantom_core
    
    # Example pool (placeholder pubkey)
    pool_id = "11111111111111111111111111111111"
    tick_current = 1000
    tick_spacing = 10
    a_to_b = True
    
    lower, current, upper = phantom_core.derive_tick_arrays(
        pool_id, tick_current, tick_spacing, a_to_b
    )
    
    # All should be valid base58 pubkeys (32 bytes)
    assert len(lower) > 30
    assert len(current) > 30
    assert len(upper) > 30
    
    # Lower should be different from current
    # (current and upper may be same for A→B since we need lower coverage)
    assert lower != current
    
    print(f"\nA→B tick arrays:")
    print(f"  Lower:   {lower[:20]}...")
    print(f"  Current: {current[:20]}...")
    print(f"  Upper:   {upper[:20]}...")


def test_derive_tick_arrays_b_to_a():
    """Test tick array derivation for B→A swap."""
    import phantom_core
    
    pool_id = "11111111111111111111111111111111"
    tick_current = -500
    tick_spacing = 1
    a_to_b = False
    
    lower, current, upper = phantom_core.derive_tick_arrays(
        pool_id, tick_current, tick_spacing, a_to_b
    )
    
    assert len(lower) > 30
    assert len(current) > 30
    assert len(upper) > 30
    
    print(f"\nB→A tick arrays (negative tick):")
    print(f"  Lower:   {lower[:20]}...")
    print(f"  Current: {current[:20]}...")
    print(f"  Upper:   {upper[:20]}...")


def test_derive_tick_arrays_extended():
    """Test extended tick array derivation (5 arrays)."""
    import phantom_core
    
    pool_id = "11111111111111111111111111111111"
    tick_current = 5000
    tick_spacing = 60
    
    arrays = phantom_core.derive_tick_arrays_extended(
        pool_id, tick_current, tick_spacing
    )
    
    assert len(arrays) == 5
    
    # All unique
    assert len(set(arrays)) == 5
    
    print(f"\nExtended tick arrays (5 total):")
    for i, arr in enumerate(arrays):
        print(f"  [{i-2:+d}]: {arr[:20]}...")


def test_derive_tick_arrays_invalid_pool():
    """Invalid pool ID should raise ValueError."""
    import phantom_core
    
    with pytest.raises(ValueError):
        phantom_core.derive_tick_arrays(
            "invalid_pool_id",
            1000,
            10,
            True
        )


def test_legacy_clmm_discriminator():
    """Verify legacy CLMM swap discriminator is available."""
    import phantom_core
    
    # Build legacy swap data
    data = phantom_core.build_raydium_clmm_swap_legacy_data(
        amount=1000000,
        other_amount_threshold=900000,
        sqrt_price_limit_x64=0,
        by_amount_in=True
    )
    
    if isinstance(data, list):
        data = bytes(data)
    
    # Verify legacy discriminator
    expected_disc = bytes([248, 198, 244, 225, 115, 175, 175, 192])
    assert data[:8] == expected_disc
    
    print(f"\nLegacy CLMM swap data: {data[:16].hex()}...")


def test_dual_discriminator_support():
    """Verify both legacy and v2 discriminators work."""
    import phantom_core
    
    # Legacy (SPL-only)
    legacy = phantom_core.build_raydium_clmm_swap_legacy_data(1000, 900, 0)
    
    # V2 (SPL + Token-2022)
    v2 = phantom_core.build_raydium_clmm_swap_data(1000, 900, 0)
    
    if isinstance(legacy, list):
        legacy = bytes(legacy)
    if isinstance(v2, list):
        v2 = bytes(v2)
    
    # Different discriminators, same args
    assert legacy[:8] != v2[:8], "Discriminators should be different"
    assert legacy[8:] == v2[8:], "Args encoding should be identical"
    
    print(f"\nLegacy discriminator: {legacy[:8].hex()}")
    print(f"V2 discriminator:     {v2[:8].hex()}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
