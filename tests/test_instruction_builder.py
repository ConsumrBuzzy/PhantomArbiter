"""
Test Suite: Instruction Builder (The Forge)
============================================
Verifies Rust instruction building functions.

Run: pytest tests/test_instruction_builder.py -v
"""

import pytest


def test_forge_imports():
    """Verify instruction builder functions are available."""
    import phantom_core

    assert hasattr(phantom_core, "build_raydium_swap_ix")
    assert hasattr(phantom_core, "build_raydium_swap_data")
    assert hasattr(phantom_core, "build_whirlpool_swap_ix")
    assert hasattr(phantom_core, "build_whirlpool_swap_data")
    assert hasattr(phantom_core, "build_dlmm_swap_ix")
    assert hasattr(phantom_core, "build_dlmm_swap_data")
    assert hasattr(phantom_core, "get_dex_program_ids")


def test_get_dex_program_ids():
    """Verify DEX program IDs are correct."""
    import phantom_core

    program_ids = dict(phantom_core.get_dex_program_ids())

    assert "RAYDIUM_AMM_V4" in program_ids
    assert "ORCA_WHIRLPOOL" in program_ids
    assert "METEORA_DLMM" in program_ids
    assert "TOKEN_PROGRAM" in program_ids

    # Verify known program IDs
    assert (
        program_ids["RAYDIUM_AMM_V4"] == "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    )
    assert (
        program_ids["ORCA_WHIRLPOOL"] == "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
    )
    assert program_ids["TOKEN_PROGRAM"] == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def test_build_raydium_swap_data():
    """Test Raydium swap instruction data generation."""
    import phantom_core

    amount_in = 1_000_000_000  # 1 SOL
    min_out = 99_000_000  # 99 USDC

    data = phantom_core.build_raydium_swap_data(amount_in, min_out)

    # Convert to bytes if list
    if isinstance(data, list):
        data = bytes(data)

    # Verify structure: [discriminator (1 byte), amount_in (8 bytes LE), min_out (8 bytes LE)]
    assert len(data) == 17
    assert data[0] == 9  # Raydium swap discriminator

    # Verify amount encoding
    decoded_amount_in = int.from_bytes(data[1:9], "little")
    decoded_min_out = int.from_bytes(data[9:17], "little")

    assert decoded_amount_in == amount_in
    assert decoded_min_out == min_out

    print(f"\nRaydium Swap Data: {data.hex()}")


def test_build_whirlpool_swap_data():
    """Test Whirlpool swap instruction data generation."""
    import phantom_core

    amount = 1_000_000_000
    threshold = 99_000_000
    sqrt_price_limit = 0  # No limit

    data = phantom_core.build_whirlpool_swap_data(
        amount, threshold, sqrt_price_limit, True, True
    )

    # Convert to bytes if list
    if isinstance(data, list):
        data = bytes(data)

    # Verify structure: [discriminator (8 bytes), amount (8), threshold (8), sqrt_price (16), is_input (1), a_to_b (1)]
    assert len(data) == 8 + 8 + 8 + 16 + 1 + 1  # 42 bytes

    # Verify discriminator
    expected_disc = bytes([0xF8, 0xC6, 0x9E, 0x91, 0xE1, 0x75, 0x87, 0xC8])
    assert data[:8] == expected_disc

    print(f"\nWhirlpool Swap Data: {data.hex()}")


def test_build_dlmm_swap_data():
    """Test DLMM swap instruction data generation."""
    import phantom_core

    amount_in = 1_000_000_000
    min_out = 99_000_000

    data = phantom_core.build_dlmm_swap_data(amount_in, min_out)

    # Convert to bytes if list
    if isinstance(data, list):
        data = bytes(data)

    # Verify structure: [discriminator (8 bytes), amount_in (8), min_out (8)]
    assert len(data) == 24

    print(f"\nDLMM Swap Data: {data.hex()}")


def test_build_raydium_swap_ix_error_handling():
    """Invalid pubkeys should raise error."""
    import phantom_core

    # Try with invalid pubkey
    with pytest.raises(ValueError):
        phantom_core.build_raydium_swap_ix(
            "invalid_pubkey",  # Invalid
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            "11111111111111111111111111111111",
            1000,
            900,
        )


def test_build_raydium_swap_ix_valid():
    """Valid pubkeys should produce serialized instruction."""
    import phantom_core

    # Use placeholder pubkeys (all 1s)
    placeholder = "11111111111111111111111111111111"

    result = phantom_core.build_raydium_swap_ix(
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        1000,
        900,
    )

    # Convert to bytes if list
    if isinstance(result, list):
        result = bytes(result)

    # Should return bytes (serialized instruction)
    assert isinstance(result, bytes)
    assert len(result) > 0

    print(f"\nRaydium Full IX Size: {len(result)} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
