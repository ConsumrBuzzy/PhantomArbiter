"""
Test Suite: Raydium CLMM Instruction Builder (Phase 4)
======================================================
Verifies Rust CLMM instruction building for Raydium Concentrated Liquidity.

Run: pytest tests/test_raydium_clmm.py -v
"""

import pytest


def test_raydium_clmm_imports():
    """Verify Raydium CLMM functions are available."""
    import phantom_core
    
    assert hasattr(phantom_core, 'build_raydium_clmm_swap_ix')
    assert hasattr(phantom_core, 'build_raydium_clmm_swap_data')


def test_raydium_clmm_program_id():
    """Verify CLMM program ID is exposed."""
    import phantom_core
    
    program_ids = dict(phantom_core.get_dex_program_ids())
    
    assert "RAYDIUM_CLMM" in program_ids
    assert program_ids["RAYDIUM_CLMM"] == "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
    
    # Also verify new Token-2022 and Memo programs are exposed
    assert "TOKEN_2022_PROGRAM" in program_ids
    assert "MEMO_PROGRAM" in program_ids


def test_build_raydium_clmm_swap_data():
    """Test CLMM swap instruction data generation."""
    import phantom_core
    
    amount = 1_000_000_000  # 1 SOL
    threshold = 99_000_000  # 99 USDC min
    sqrt_price_limit = 0    # No limit
    
    data = phantom_core.build_raydium_clmm_swap_data(
        amount, threshold, sqrt_price_limit, True
    )
    
    # Convert to bytes if list
    if isinstance(data, list):
        data = bytes(data)
    
    # Structure: [discriminator (8)] + [amount (8)] + [threshold (8)] + [sqrt_price (16)] + [by_amount_in (1)]
    assert len(data) == 8 + 8 + 8 + 16 + 1  # 41 bytes
    
    # Verify discriminator (sha256("global:swap_v2")[0..8])
    expected_disc = bytes([0x2b, 0x04, 0xed, 0x0b, 0x1a, 0xc9, 0x1e, 0xb8])
    assert data[:8] == expected_disc, f"Expected {expected_disc.hex()}, got {data[:8].hex()}"
    
    # Verify amount encoding
    decoded_amount = int.from_bytes(data[8:16], 'little')
    assert decoded_amount == amount
    
    # Verify threshold encoding
    decoded_threshold = int.from_bytes(data[16:24], 'little')
    assert decoded_threshold == threshold
    
    # Verify sqrt_price_limit encoding (16 bytes LE)
    decoded_sqrt_price = int.from_bytes(data[24:40], 'little')
    assert decoded_sqrt_price == sqrt_price_limit
    
    # Verify by_amount_in flag
    assert data[40] == 1  # True
    
    print(f"\nRaydium CLMM Swap Data: {data.hex()}")


def test_build_raydium_clmm_swap_data_exact_out():
    """Test CLMM swap data with ExactOut mode."""
    import phantom_core
    
    amount = 100_000_000  # Desired 100 USDC out
    max_input = 1_100_000_000  # Max 1.1 SOL input
    sqrt_price_limit = 0
    
    data = phantom_core.build_raydium_clmm_swap_data(
        amount, max_input, sqrt_price_limit, False  # by_amount_in = False
    )
    
    if isinstance(data, list):
        data = bytes(data)
    
    # Verify by_amount_in is False (0)
    assert data[40] == 0
    
    print(f"\nRaydium CLMM ExactOut Data: {data.hex()}")


def test_build_raydium_clmm_swap_ix_valid():
    """Valid pubkeys should produce serialized instruction."""
    import phantom_core
    
    placeholder = "11111111111111111111111111111111"
    
    result = phantom_core.build_raydium_clmm_swap_ix(
        payer=placeholder,
        amm_config=placeholder,
        pool_state=placeholder,
        input_token_account=placeholder,
        output_token_account=placeholder,
        input_vault=placeholder,
        output_vault=placeholder,
        observation_state=placeholder,
        tick_array_lower=placeholder,
        tick_array_current=placeholder,
        tick_array_upper=placeholder,
        input_token_mint=placeholder,
        output_token_mint=placeholder,
        amount=1000,
        other_amount_threshold=900,
        sqrt_price_limit_x64=0,
        by_amount_in=True,
    )
    
    if isinstance(result, list):
        result = bytes(result)
    
    assert isinstance(result, bytes)
    assert len(result) > 0
    
    print(f"\nRaydium CLMM Full IX Size: {len(result)} bytes")


def test_build_raydium_clmm_swap_ix_invalid_pubkey():
    """Invalid pubkeys should raise ValueError."""
    import phantom_core
    
    placeholder = "11111111111111111111111111111111"
    
    with pytest.raises(ValueError):
        phantom_core.build_raydium_clmm_swap_ix(
            payer="invalid_pubkey",  # Invalid!
            amm_config=placeholder,
            pool_state=placeholder,
            input_token_account=placeholder,
            output_token_account=placeholder,
            input_vault=placeholder,
            output_vault=placeholder,
            observation_state=placeholder,
            tick_array_lower=placeholder,
            tick_array_current=placeholder,
            tick_array_upper=placeholder,
            input_token_mint=placeholder,
            output_token_mint=placeholder,
            amount=1000,
            other_amount_threshold=900,
            sqrt_price_limit_x64=0,
        )


def test_build_raydium_clmm_with_price_limit():
    """Test instruction building with a sqrt_price_limit."""
    import phantom_core
    
    # Use a realistic sqrt_price_limit (2^64 is price = 1.0)
    q64 = 1 << 64
    sqrt_price_limit = int(q64 * 0.9)  # 10% below current price
    
    data = phantom_core.build_raydium_clmm_swap_data(
        amount=1_000_000,
        other_amount_threshold=900_000,
        sqrt_price_limit_x64=sqrt_price_limit,
        by_amount_in=True,
    )
    
    if isinstance(data, list):
        data = bytes(data)
    
    # Verify sqrt_price_limit is correctly encoded
    decoded_limit = int.from_bytes(data[24:40], 'little')
    assert decoded_limit == sqrt_price_limit
    
    print(f"\nSqrt price limit: {sqrt_price_limit} -> encoded in data correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
