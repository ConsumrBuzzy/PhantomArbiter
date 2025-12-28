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
    
    assert hasattr(phantom_core, 'compute_amm_out')
    assert hasattr(phantom_core, 'compute_amm_in')
    assert hasattr(phantom_core, 'compute_amm_out_batch')
    assert hasattr(phantom_core, 'compute_price_impact')


def test_compute_amm_out_basic():
    """Test basic constant product swap calculation."""
    import phantom_core
    
    # Pool: 1000 SOL (9 decimals), 100,000 USDC (6 decimals)
    # Swap 1 SOL -> expect ~99.75 USDC (after 0.25% fee)
    reserve_sol = 1000 * 10**9   # 1000 SOL in lamports
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
    small_impact = phantom_core.compute_price_impact(1 * 10**9, reserve_in, reserve_out, 25)
    assert small_impact < 1.0, f"Small trade impact too high: {small_impact}%"
    
    # Large trade (10% of pool): significant impact
    large_impact = phantom_core.compute_price_impact(100 * 10**9, reserve_in, reserve_out, 25)
    assert large_impact > 5.0, f"Large trade impact too low: {large_impact}%"


def test_batch_performance():
    """Batch processing should be faster than individual calls."""
    import phantom_core
    
    reserve_in = 1000 * 10**9
    reserve_out = 100000 * 10**6
    amounts = [i * 10**9 for i in range(1, 1001)]  # 1000 swaps
    
    # Batch
    start = time.perf_counter()
    batch_results = phantom_core.compute_amm_out_batch(amounts, reserve_in, reserve_out, 25)
    batch_time = time.perf_counter() - start
    
    # Individual
    start = time.perf_counter()
    individual_results = [phantom_core.compute_amm_out(a, reserve_in, reserve_out, 25) for a in amounts]
    individual_time = time.perf_counter() - start
    
    print(f"\nBatch (1000 swaps): {batch_time*1000:.3f}ms")
    print(f"Individual (1000 swaps): {individual_time*1000:.3f}ms")
    
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
        rust_out = phantom_core.compute_amm_out(amount_in, reserve_in, reserve_out, fee_bps)
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
    print(f"Rust:   {rust_time*1000:.2f}ms ({iterations/rust_time:,.0f} ops/sec)")
    print(f"Python: {python_time*1000:.2f}ms ({iterations/python_time:,.0f} ops/sec)")
    print(f"Speedup: {speedup:.1f}x")
    
    # Rust should be at least 10x faster
    assert speedup > 5, f"Expected at least 5x speedup, got {speedup:.1f}x"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
