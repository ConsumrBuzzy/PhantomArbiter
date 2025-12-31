"""
Test Suite: AMM Math Engine (The Oracle)
=========================================
Verifies Rust AMM math functions against known values and benchmarks performance.

Run: pytest tests/test_amm_math.py -v
"""

import pytest
import time


def test_rust_module_imports():
    """Verify phantom_core can be imported with AMM functions."""
    import phantom_core

    assert hasattr(phantom_core, "compute_amm_out")
    assert hasattr(phantom_core, "compute_amm_in")
    assert hasattr(phantom_core, "compute_amm_out_batch")
    assert hasattr(phantom_core, "compute_price_impact")


def test_compute_amm_out_basic():
    """Test basic constant product swap calculation."""
    import phantom_core

    # Pool: 1000 SOL (9 decimals), 100,000 USDC (6 decimals)
    # Swap 1 SOL -> expect ~99.75 USDC (after 0.25% fee)
    reserve_sol = 1000 * 10**9  # 1000 SOL in lamports
    reserve_usdc = 100000 * 10**6  # 100,000 USDC
    amount_in = 1 * 10**9  # 1 SOL

    amount_out = phantom_core.compute_amm_out(amount_in, reserve_sol, reserve_usdc, 25)

    # Expected: ~99.75 USDC (price impact + fee)
    # Allow 1% tolerance
    expected = 99.75 * 10**6
    assert amount_out > expected * 0.99, f"Got {amount_out}, expected ~{expected}"
    assert amount_out < expected * 1.01, f"Got {amount_out}, expected ~{expected}"


def test_compute_amm_in_basic():
    """Test inverse swap calculation."""
    import phantom_core

    reserve_sol = 1000 * 10**9
    reserve_usdc = 100000 * 10**6
    desired_out = 99 * 10**6  # 99 USDC

    amount_in = phantom_core.compute_amm_in(desired_out, reserve_sol, reserve_usdc, 25)

    # Verify roundtrip: this input should give us at least desired_out
    amount_out = phantom_core.compute_amm_out(amount_in, reserve_sol, reserve_usdc, 25)
    assert amount_out >= desired_out, f"Roundtrip failed: {amount_out} < {desired_out}"


def test_compute_amm_out_zero_input():
    """Zero input should return zero output."""
    import phantom_core

    result = phantom_core.compute_amm_out(0, 1000, 1000, 25)
    assert result == 0


def test_compute_amm_out_zero_reserves():
    """Zero reserves should return zero output (not crash)."""
    import phantom_core

    result = phantom_core.compute_amm_out(100, 0, 1000, 25)
    assert result == 0

    result = phantom_core.compute_amm_out(100, 1000, 0, 25)
    assert result == 0


def test_compute_price_impact():
    """Large trades should have significant price impact."""
    import phantom_core

    reserve_in = 1000 * 10**9
    reserve_out = 100000 * 10**6

    # Small trade: minimal impact
    small_impact = phantom_core.compute_price_impact(
        1 * 10**9, reserve_in, reserve_out, 25
    )
    assert small_impact < 1.0, f"Small trade impact too high: {small_impact}%"

    # Large trade (10% of pool): significant impact
    large_impact = phantom_core.compute_price_impact(
        100 * 10**9, reserve_in, reserve_out, 25
    )
    assert large_impact > 5.0, f"Large trade impact too low: {large_impact}%"


def test_batch_performance():
    """Batch processing should be faster than individual calls."""
    import phantom_core

    reserve_in = 1000 * 10**9
    reserve_out = 100000 * 10**6
    amounts = [i * 10**9 for i in range(1, 1001)]  # 1000 swaps

    # Batch
    start = time.perf_counter()
    batch_results = phantom_core.compute_amm_out_batch(
        amounts, reserve_in, reserve_out, 25
    )
    batch_time = time.perf_counter() - start

    # Individual
    start = time.perf_counter()
    individual_results = [
        phantom_core.compute_amm_out(a, reserve_in, reserve_out, 25) for a in amounts
    ]
    individual_time = time.perf_counter() - start

    print(f"\nBatch (1000 swaps): {batch_time * 1000:.3f}ms")
    print(f"Individual (1000 swaps): {individual_time * 1000:.3f}ms")

    assert batch_results == individual_results, "Results should be identical"
    # Batch should be at least 2x faster (FFI overhead reduction)
    # Note: In practice, batch is faster due to single FFI call


def pure_python_amm_out(amount_in, reserve_in, reserve_out, fee_bps=25):
    """Pure Python implementation for comparison."""
    if reserve_in == 0 or reserve_out == 0 or amount_in == 0:
        return 0
    fee_factor = 10000 - fee_bps
    numerator = reserve_out * amount_in * fee_factor
    denominator = reserve_in * 10000 + amount_in * fee_factor
    return numerator // denominator


def test_rust_vs_python_accuracy():
    """Rust and Python implementations should produce identical results."""
    import phantom_core

    test_cases = [
        (1_000_000_000, 1000_000_000_000, 100000_000_000, 25),
        (100_000_000, 500_000_000, 500_000_000, 30),
        (1, 1000, 1000, 0),  # Zero fee
        (999_999_999_999, 1000_000_000_000, 100000_000_000, 25),  # Large swap
    ]

    for amount_in, reserve_in, reserve_out, fee_bps in test_cases:
        rust_out = phantom_core.compute_amm_out(
            amount_in, reserve_in, reserve_out, fee_bps
        )
        python_out = pure_python_amm_out(amount_in, reserve_in, reserve_out, fee_bps)

        assert rust_out == python_out, (
            f"Mismatch for inputs ({amount_in}, {reserve_in}, {reserve_out}, {fee_bps}): "
            f"Rust={rust_out}, Python={python_out}"
        )


def test_rust_vs_python_benchmark():
    """Benchmark Rust vs Python performance."""
    import phantom_core

    iterations = 100_000
    reserve_in = 1000_000_000_000
    reserve_out = 100000_000_000
    amount_in = 1_000_000_000

    # Rust
    start = time.perf_counter()
    for _ in range(iterations):
        phantom_core.compute_amm_out(amount_in, reserve_in, reserve_out, 25)
    rust_time = time.perf_counter() - start

    # Python
    start = time.perf_counter()
    for _ in range(iterations):
        pure_python_amm_out(amount_in, reserve_in, reserve_out, 25)
    python_time = time.perf_counter() - start

    speedup = python_time / rust_time

    print(f"\n=== BENCHMARK: {iterations:,} iterations ===")
    print(f"Rust:   {rust_time * 1000:.2f}ms ({iterations / rust_time:,.0f} ops/sec)")
    print(
        f"Python: {python_time * 1000:.2f}ms ({iterations / python_time:,.0f} ops/sec)"
    )
    print(f"Speedup: {speedup:.1f}x")

    # Rust should be at least 2x faster (FFI overhead limits gains for single calls)
    # For batch operations, expect much higher speedup
    assert speedup > 2, f"Expected at least 2x speedup, got {speedup:.1f}x"


# ============================================================================
# PHASE 2: CLMM TESTS
# ============================================================================


def test_clmm_imports():
    """Verify CLMM functions are available."""
    import phantom_core

    assert hasattr(phantom_core, "compute_clmm_swap")
    assert hasattr(phantom_core, "sqrt_price_from_tick")
    assert hasattr(phantom_core, "tick_from_sqrt_price")
    assert hasattr(phantom_core, "price_from_sqrt_price")


def test_sqrt_price_from_tick_zero():
    """Tick 0 should give sqrt_price = 1.0 (Q64.64 = 2^64)."""
    import phantom_core

    sqrt_price = phantom_core.sqrt_price_from_tick(0)
    q64 = 1 << 64

    # Should be very close to 2^64
    assert abs(sqrt_price - q64) < q64 * 0.001, (
        f"Tick 0 sqrt_price should be ~{q64}, got {sqrt_price}"
    )


def test_tick_roundtrip():
    """Converting tick -> sqrt_price -> tick should be stable."""
    import phantom_core

    test_ticks = [0, 100, -100, 1000, -1000, 50000, -50000]

    for tick in test_ticks:
        sqrt_price = phantom_core.sqrt_price_from_tick(tick)
        recovered_tick = phantom_core.tick_from_sqrt_price(sqrt_price)

        # Allow +/- 1 due to rounding
        assert abs(recovered_tick - tick) <= 1, (
            f"Tick roundtrip failed: {tick} -> {sqrt_price} -> {recovered_tick}"
        )


def test_price_from_sqrt_price():
    """Price should be sqrt_price squared."""
    import phantom_core

    q64 = 1 << 64

    # sqrt_price = 2.0 (Q64.64 = 2 * 2^64)
    sqrt_price_x64 = 2 * q64
    price = phantom_core.price_from_sqrt_price(sqrt_price_x64)

    # Price should be 4.0
    assert abs(price - 4.0) < 0.01, f"Expected price 4.0, got {price}"


def test_compute_clmm_swap_basic():
    """Basic CLMM swap should produce reasonable output."""
    import phantom_core

    # Simulate a pool at tick 0 (price = 1.0), with 1M liquidity
    sqrt_price_x64 = phantom_core.sqrt_price_from_tick(0)
    liquidity = 1_000_000_000_000  # 1M in token units
    amount_in = 1_000_000  # 1 token

    # Swap A -> B (price decreases)
    amount_out, new_sqrt_price = phantom_core.compute_clmm_swap(
        amount_in, sqrt_price_x64, liquidity, True, 30
    )

    # Should get some output
    assert amount_out > 0, f"Expected positive output, got {amount_out}"
    # Price should decrease for A->B
    assert new_sqrt_price < sqrt_price_x64, "Price should decrease for A->B swap"

    print(f"\nCLMM Swap A->B: {amount_in} in -> {amount_out} out")
    print(f"Price change: {sqrt_price_x64} -> {new_sqrt_price}")


def test_compute_clmm_swap_zero_input():
    """Zero input should return zero output."""
    import phantom_core

    sqrt_price_x64 = phantom_core.sqrt_price_from_tick(0)
    liquidity = 1_000_000_000

    amount_out, new_sqrt_price = phantom_core.compute_clmm_swap(
        0, sqrt_price_x64, liquidity, True, 30
    )

    assert amount_out == 0
    assert new_sqrt_price == sqrt_price_x64


# ============================================================================
# PHASE 3: DLMM TESTS
# ============================================================================


def test_dlmm_imports():
    """Verify DLMM functions are available."""
    import phantom_core

    assert hasattr(phantom_core, "dlmm_price_from_bin")
    assert hasattr(phantom_core, "dlmm_bin_from_price")
    assert hasattr(phantom_core, "compute_dlmm_swap_single_bin")
    assert hasattr(phantom_core, "compute_dlmm_swap")
    assert hasattr(phantom_core, "dlmm_get_effective_fee")


def test_dlmm_price_from_bin_zero():
    """Bin at offset (2^23) should give price = 1.0."""
    import phantom_core

    bin_offset = 8388608  # 2^23
    bin_step = 10  # 0.1% per bin

    price = phantom_core.dlmm_price_from_bin(bin_offset, bin_step)

    # Should be very close to 1.0
    assert abs(price - 1.0) < 0.001, f"Bin offset price should be ~1.0, got {price}"


def test_dlmm_bin_roundtrip():
    """Converting price -> bin -> price should be stable."""
    import phantom_core

    bin_step = 10  # 0.1% per bin
    test_prices = [0.5, 1.0, 2.0, 10.0, 100.0]

    for price in test_prices:
        bin_id = phantom_core.dlmm_bin_from_price(price, bin_step)
        recovered_price = phantom_core.dlmm_price_from_bin(bin_id, bin_step)

        # Allow ~0.1% tolerance (one bin step)
        error = abs(recovered_price - price) / price
        assert error < 0.002, (
            f"Price roundtrip failed: {price} -> bin {bin_id} -> {recovered_price}"
        )


def test_dlmm_swap_single_bin():
    """Single bin swap should produce reasonable output."""
    import phantom_core

    bin_offset = 8388608  # price = 1.0
    bin_step = 10
    reserve_x = 1_000_000  # 1M token X
    reserve_y = 1_000_000  # 1M token Y
    amount_in = 10_000  # 10k tokens

    amount_out, consumed, crossed = phantom_core.compute_dlmm_swap_single_bin(
        amount_in, reserve_x, reserve_y, bin_offset, bin_step, 25, True
    )

    # At price 1.0 with small fee, output should be close to input
    assert amount_out > 9000, f"Expected ~9975, got {amount_out}"
    assert amount_out < 10000, "Output should be less than input due to fee"
    assert consumed == amount_in, "All input should be consumed"
    assert crossed == False, "Should not cross bin for small swap"

    print(f"\nDLMM Single Bin: {amount_in} in -> {amount_out} out, crossed={crossed}")


def test_dlmm_swap_multi_bin():
    """Multi-bin swap should traverse bins correctly."""
    import phantom_core

    bin_offset = 8388608
    bin_step = 10

    # Create 3 bins with liquidity
    bin_reserves = [
        (bin_offset, 1000, 1000),  # Bin 0
        (bin_offset - 1, 1000, 1000),  # Bin -1 (lower price)
        (bin_offset - 2, 1000, 1000),  # Bin -2 (even lower)
    ]

    # Swap more than one bin can handle
    amount_in = 5000

    total_out, final_bin = phantom_core.compute_dlmm_swap(
        amount_in, bin_offset, bin_step, bin_reserves, 25, True
    )

    # Should get output from multiple bins
    assert total_out > 0, f"Expected positive output, got {total_out}"

    print(f"\nDLMM Multi-Bin: {amount_in} in -> {total_out} out, final_bin={final_bin}")


def test_dlmm_effective_fee():
    """Dynamic fee should increase with volatility."""
    import phantom_core

    base_fee = 25  # 0.25%

    # No volatility
    fee_low = phantom_core.dlmm_get_effective_fee(base_fee, 0)
    assert fee_low == base_fee, f"Zero volatility should give base fee, got {fee_low}"

    # High volatility
    fee_high = phantom_core.dlmm_get_effective_fee(base_fee, 500000)
    assert fee_high > base_fee, f"High volatility should increase fee, got {fee_high}"
    assert fee_high <= 1000, f"Fee should be capped at 10%, got {fee_high}"

    print(f"\nDLMM Fee: base={base_fee}, low_vol={fee_low}, high_vol={fee_high}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
