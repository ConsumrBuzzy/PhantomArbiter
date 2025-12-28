import time
import phantom_core

def python_calculate_net_profit(spread_raw: float, trade_size: float, jito_tip: float, route_friction: float) -> float:
    """Pure Python implementation for comparison."""
    gross = trade_size * (spread_raw / 100.0)
    net = gross - jito_tip - route_friction
    return net

def benchmark():
    ITERATIONS = 10_000_000
    spread = 1.5
    size = 1000.0
    tip = 0.05
    friction = 0.01

    print(f"🚀 Benchmarking {ITERATIONS:,} iterations...")

    # Python Benchmark
    start_py = time.perf_counter()
    for _ in range(ITERATIONS):
        python_calculate_net_profit(spread, size, tip, friction)
    end_py = time.perf_counter()
    time_py = end_py - start_py

    print(f"🐍 Python Time: {time_py:.4f}s")

    # Rust Benchmark
    start_rs = time.perf_counter()
    for _ in range(ITERATIONS):
        phantom_core.calculate_net_profit(spread, size, tip, friction)
    end_rs = time.perf_counter()
    time_rs = end_rs - start_rs

    print(f"🦀 Rust Time:   {time_rs:.4f}s")
    
    if time_rs > 0:
        print(f"⚡ Speedup:     {time_py / time_rs:.2f}x")
    else:
        print("⚡ Speedup:     Infinite (Rust was too fast to measure!)")

if __name__ == "__main__":
    benchmark()
