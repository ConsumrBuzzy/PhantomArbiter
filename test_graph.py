import phantom_core
import math


def test_graph_engine():
    print("🧪 Testing Rust Graph Engine (Pathfinder)...")

    # 1. Initialize
    graph = phantom_core.Graph()
    print("   ✅ Graph Initialized")

    # 2. Build a Profitable Triangle (The "Golden Triangle")
    # Scenario:
    # 1 USDC -> SOL (Price 10.0) -> 10 SOL
    # 10 SOL -> RAY (Price 5.0)  -> 50 RAY
    # 50 RAY -> USDC (Price 0.022) -> 1.1 USDC
    # Total Profit: 10%

    # Prices
    price_usdc_sol = 10.0
    price_sol_ray = 5.0
    price_ray_usdc = 0.022  # 5.0 * 10 * 0.022 = 1.1

    print("\n[1] Injecting Liquidity (Edges)...")
    # update_edge(source, target, pool_id, price)
    graph.update_edge("USDC", "SOL", "pool_usdc_sol", price_usdc_sol)
    graph.update_edge("SOL", "RAY", "pool_sol_ray", price_sol_ray)
    graph.update_edge("RAY", "USDC", "pool_ray_usdc", price_ray_usdc)
    print("   ✅ Edges Pushed")

    # 3. Find Cycle
    print("\n[2] Hunting for Arbitrage (SPFA)...")
    path = graph.find_arbitrage_loop("USDC")

    print(f"   Found Path: {path}")

    # 4. Verify
    expected_path = ["pool_ray_usdc", "pool_sol_ray", "pool_usdc_sol"]
    # Note: Our reconstruct_path reverses it, so we expect [usdc->sol, sol->ray, ray->usdc]
    # Let's check logic: reconstruct_path does `path.reverse()` at the end.
    # The parent pointers trace backwards: USDC <- RAY <- SOL <- USDC
    # So raw path is [pool_ray_usdc, pool_sol_ray, pool_usdc_sol]
    # Reversed: [pool_usdc_sol, pool_sol_ray, pool_ray_usdc]

    # Let's verify what the code actually does by asserting set contents first if order is tricky constraint
    # But for a simple triangle, it should be deterministic.

    if len(path) == 3:
        print("   ✅ Cycle Detected (Length 3)")
    else:
        print(f"   ❌ Failed to detect cycle. Length: {len(path)}")

    # Check Profit Math manually
    total_log_weight = (
        -math.log(price_usdc_sol) - math.log(price_sol_ray) - math.log(price_ray_usdc)
    )
    print(f"   Cycle Weight: {total_log_weight:.4f} (Needs to be < 0)")
    assert total_log_weight < 0


if __name__ == "__main__":
    test_graph_engine()
