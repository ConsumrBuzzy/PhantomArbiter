#!/usr/bin/env python
"""
Multiverse Performance Benchmarks
==================================
V140: Narrow Path Infrastructure (Phase 16)

Benchmarks for the multi-hop arbitrage pipeline:
- Graph update latency
- Multiverse scan performance
- Bundle build time
- End-to-end signal latency

Usage:
    python scripts/bench_multiverse.py
"""

import time
import asyncio
import random
from typing import List, Tuple


def benchmark_graph_operations():
    """Benchmark HopGraph operations."""
    print("\n" + "=" * 60)
    print("🔬 GRAPH OPERATIONS BENCHMARK")
    print("=" * 60)
    
    try:
        from phantom_core import HopGraph, PoolEdge
    except ImportError:
        print("⚠️  Rust extension not found. Run: cd src_rust && maturin develop --release")
        return
    
    graph = HopGraph()
    SOL = "So11111111111111111111111111111111111111112"
    
    # Generate synthetic edges
    tokens = [f"Token{i}{'0' * (32 - len(str(i)))}" for i in range(100)]
    tokens = [SOL] + tokens
    
    edges = []
    for i in range(len(tokens)):
        for j in range(i + 1, min(i + 5, len(tokens))):
            edges.append(PoolEdge(
                pool_address=f"Pool{i}_{j}{'0' * 30}",
                token_a=tokens[i],
                token_b=tokens[j],
                reserve_a=10_000_000_000,
                reserve_b=10_000_000_000,
                fee_bps=30,
                dex="RAYDIUM",
                liquidity_usd=50_000,
            ))
    
    print(f"📊 Test dataset: {len(tokens)} tokens, {len(edges)} edges")
    
    # Benchmark edge insertion
    start = time.perf_counter()
    for edge in edges:
        graph.add_edge(edge)
    insert_time = (time.perf_counter() - start) * 1000
    
    print(f"\n📥 Edge insertion ({len(edges)} edges):")
    print(f"   Total: {insert_time:.2f}ms")
    print(f"   Per edge: {insert_time / len(edges):.3f}ms")
    print(f"   Target: <1ms per edge {'✅' if insert_time / len(edges) < 1 else '❌'}")
    
    # Benchmark edge update
    update_edges = random.sample(edges, min(100, len(edges)))
    start = time.perf_counter()
    for edge in update_edges:
        edge.reserve_a = random.randint(5_000_000_000, 15_000_000_000)
        graph.add_edge(edge)
    update_time = (time.perf_counter() - start) * 1000
    
    print(f"\n🔄 Edge updates ({len(update_edges)} edges):")
    print(f"   Total: {update_time:.2f}ms")
    print(f"   Per edge: {update_time / len(update_edges):.3f}ms")
    print(f"   Target: <1ms per edge {'✅' if update_time / len(update_edges) < 1 else '❌'}")
    
    return graph


def benchmark_multiverse_scan(graph=None):
    """Benchmark MultiverseScanner operations."""
    print("\n" + "=" * 60)
    print("🌌 MULTIVERSE SCAN BENCHMARK")
    print("=" * 60)
    
    try:
        from phantom_core import HopGraph, PoolEdge, MultiverseScanner
    except ImportError:
        print("⚠️  Rust extension not found.")
        return
    
    SOL = "So11111111111111111111111111111111111111112"
    
    if graph is None:
        # Create test graph
        graph = HopGraph()
        tokens = [f"Token{i}{'0' * (32 - len(str(i)))}" for i in range(50)]
        tokens = [SOL] + tokens
        
        for i in range(len(tokens)):
            for j in range(i + 1, min(i + 3, len(tokens))):
                graph.add_edge(PoolEdge(
                    pool_address=f"Pool{i}_{j}{'0' * 30}",
                    token_a=tokens[i],
                    token_b=tokens[j],
                    reserve_a=10_000_000_000,
                    reserve_b=10_000_000_000 * (1 + random.uniform(-0.01, 0.01)),
                    fee_bps=30,
                    dex=random.choice(["RAYDIUM", "ORCA", "METEORA"]),
                    liquidity_usd=random.randint(10_000, 500_000),
                ))
    
    stats = graph.get_stats()
    print(f"📊 Graph: {stats.get('node_count', 0)} nodes, {stats.get('edge_count', 0)} edges")
    
    scanner = MultiverseScanner(
        min_hops=2,
        max_hops=4,
        min_liquidity_usd=5_000,
    )
    
    # Benchmark scans at different hop depths
    for max_hops in [2, 3, 4]:
        scanner_temp = MultiverseScanner(min_hops=2, max_hops=max_hops)
        
        start = time.perf_counter()
        result = scanner_temp.scan(graph, SOL, min_profit_pct=0.05)
        scan_time = (time.perf_counter() - start) * 1000
        
        cycles_found = result.scan_stats.total_cycles_found if result else 0
        
        print(f"\n🔍 Scan (2-{max_hops} hops):")
        print(f"   Time: {scan_time:.2f}ms")
        print(f"   Cycles found: {cycles_found}")
        print(f"   Target: <100ms {'✅' if scan_time < 100 else '❌'}")


def benchmark_bundle_build():
    """Benchmark MultiHopBuilder operations."""
    print("\n" + "=" * 60)
    print("📦 BUNDLE BUILD BENCHMARK")
    print("=" * 60)
    
    try:
        from phantom_core import MultiHopBuilder, SwapLeg
    except ImportError:
        print("⚠️  Rust extension not found.")
        return
    
    # Create mock swap legs (instruction data would be from Jupiter)
    mock_ix_data = bytes([0] * 100)  # Placeholder instruction data
    
    legs = [
        SwapLeg(
            pool_address="Pool1" + "0" * 39,
            dex="RAYDIUM",
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="Token1" + "0" * 37,
            instruction_data=list(mock_ix_data),
        ),
        SwapLeg(
            pool_address="Pool2" + "0" * 39,
            dex="ORCA",
            input_mint="Token1" + "0" * 37,
            output_mint="Token2" + "0" * 37,
            instruction_data=list(mock_ix_data),
        ),
        SwapLeg(
            pool_address="Pool3" + "0" * 39,
            dex="METEORA",
            input_mint="Token2" + "0" * 37,
            output_mint="So11111111111111111111111111111111111111112",
            instruction_data=list(mock_ix_data),
        ),
    ]
    
    print(f"📊 Test: {len(legs)}-leg bundle build")
    print("⚠️  Note: Cannot benchmark without valid keypair")
    
    # Compute unit estimation benchmark (doesn't require keypair)
    print("\n📐 Compute Unit Estimation:")
    for leg_count in [2, 3, 4, 5]:
        # Formula: base_overhead + cu_per_leg * legs
        cu_estimate = 50_000 + 60_000 * leg_count
        print(f"   {leg_count}-leg: {cu_estimate:,} CU")
    
    # Tip calculation benchmark
    print("\n💰 Tip Calculation Logic:")
    base_tip = 10_000
    for legs, congestion in [(3, 0.0), (3, 0.5), (4, 0.0), (4, 1.0)]:
        complexity_factor = 1.0 + (legs - 2) * 0.25
        congestion_factor = 1.0 + congestion
        tip = int(base_tip * complexity_factor * congestion_factor)
        print(f"   {legs}-leg, congestion {congestion:.1f}: {tip:,} lamports")


def benchmark_jupiter_latency():
    """Benchmark Jupiter API latency (requires network)."""
    print("\n" + "=" * 60)
    print("🌐 JUPITER API LATENCY")
    print("=" * 60)
    
    async def run_quote_test():
        from src.engine.dex_builders import JupiterClient
        
        client = JupiterClient(slippage_bps=50)
        
        SOL = "So11111111111111111111111111111111111111112"
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        latencies = []
        
        print(f"\n🔍 Testing SOL → USDC quotes (5 samples)...")
        
        for i in range(5):
            start = time.perf_counter()
            quote = await client.get_quote(
                input_mint=SOL,
                output_mint=USDC,
                amount=1_000_000_000,  # 1 SOL
            )
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
            
            if quote:
                print(f"   Sample {i+1}: {latency:.0f}ms | Output: {quote.output_amount:,}")
            else:
                print(f"   Sample {i+1}: {latency:.0f}ms | Failed")
            
            await asyncio.sleep(0.5)  # Rate limit courtesy
        
        await client.close()
        
        if latencies:
            avg = sum(latencies) / len(latencies)
            print(f"\n📊 Average latency: {avg:.0f}ms")
            print(f"   Target: <500ms {'✅' if avg < 500 else '❌'}")
    
    try:
        asyncio.run(run_quote_test())
    except Exception as e:
        print(f"⚠️  Network test failed: {e}")


def benchmark_end_to_end():
    """Estimate end-to-end signal latency."""
    print("\n" + "=" * 60)
    print("⏱️  END-TO-END LATENCY ESTIMATE")
    print("=" * 60)
    
    # Estimated component latencies
    components = [
        ("Graph update (1 edge)", 0.5),
        ("Multiverse scan (3-hop)", 30.0),
        ("Signal routing", 1.0),
        ("Jupiter quote (cached)", 50.0),
        ("Bundle build", 2.0),
        ("Jito submission", 100.0),
    ]
    
    total = sum(c[1] for c in components)
    
    print("\n📊 Component Breakdown:")
    for name, latency in components:
        print(f"   {name}: {latency:.1f}ms")
    
    print(f"\n⏱️  Total estimated: {total:.0f}ms")
    print(f"   Target: <250ms for competitive execution")
    print(f"   Status: {'✅ GOOD' if total < 250 else '⚠️ NEEDS OPTIMIZATION'}")


def main():
    print("\n" + "=" * 60)
    print("🚀 PHANTOMARBITER MULTIVERSE BENCHMARKS")
    print("   V140: Narrow Path Infrastructure")
    print("=" * 60)
    
    # Run benchmarks
    graph = benchmark_graph_operations()
    benchmark_multiverse_scan(graph)
    benchmark_bundle_build()
    
    # Optional network test
    import sys
    if "--network" in sys.argv:
        benchmark_jupiter_latency()
    else:
        print("\n⚠️  Skipping network tests. Run with --network to include.")
    
    benchmark_end_to_end()
    
    print("\n" + "=" * 60)
    print("✅ BENCHMARKS COMPLETE")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
