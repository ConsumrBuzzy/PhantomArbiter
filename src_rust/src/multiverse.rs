// ------------------------------------------------------------------------
// MULTIVERSE MODULE - Multi-Range Hop Scanner
// V140: Token Hopping Infrastructure (Phase 2)
// ------------------------------------------------------------------------
//
// This module implements "Multiverse Traversal" - efficient parallel
// scanning across multiple hop ranges (2-5) using Tiered DFS with
// Memoization to avoid redundant sub-path calculations.
//
// Key Insight: A 4-hop path SOL→A→B→C→SOL contains the 2-hop sub-path
// SOL→A→SOL. By memoizing intermediate results, we can efficiently
// explore all hop ranges without exponential blowup.
//
// Computational Complexity:
// - 2-Hops: O(E) - Very Low
// - 3-Hops: O(E * avg_degree) - Low
// - 4-Hops: O(E * avg_degree²) - Moderate
// - 5-Hops: O(E * avg_degree³) - High (with pruning)
// ------------------------------------------------------------------------

use crate::graph::HopGraph;
use pyo3::prelude::*;
use std::collections::HashMap;

/// Result of a multiverse scan - grouped by hop count
#[pyclass]
#[derive(Clone, Debug)]
pub struct MultiverseResult {
    /// Cycles found at each hop level
    #[pyo3(get)]
    pub cycles_by_hops: HashMap<usize, Vec<MultiverseCycle>>,

    /// Best cycle across all hop levels
    #[pyo3(get)]
    pub best_cycle: Option<MultiverseCycle>,

    /// Scan statistics
    #[pyo3(get)]
    pub scan_stats: ScanStats,
}

#[pyclass]
#[derive(Clone, Debug, Default)]
pub struct ScanStats {
    #[pyo3(get)]
    pub total_cycles_found: usize,
    #[pyo3(get)]
    pub scan_time_ms: f64,
    #[pyo3(get)]
    pub paths_explored: usize,
    #[pyo3(get)]
    pub paths_pruned: usize,
    #[pyo3(get)]
    pub memoization_hits: usize,
}

/// A cycle detected at a specific hop level
#[pyclass]
#[derive(Clone, Debug)]
pub struct MultiverseCycle {
    /// Token mints in order
    #[pyo3(get)]
    pub path: Vec<String>,

    /// Pool addresses to traverse
    #[pyo3(get)]
    pub pool_addresses: Vec<String>,

    /// Number of hops
    #[pyo3(get)]
    pub hop_count: usize,

    /// Theoretical profit percentage
    #[pyo3(get)]
    pub profit_pct: f64,

    /// Minimum liquidity across path (bottleneck)
    #[pyo3(get)]
    pub min_liquidity_usd: u64,

    /// Total fees in basis points
    #[pyo3(get)]
    pub total_fee_bps: u16,

    /// DEXes involved in this path
    #[pyo3(get)]
    pub dexes: Vec<String>,

    /// Estimated gas cost in lamports
    #[pyo3(get)]
    pub estimated_gas_lamports: u64,
}

#[pymethods]
impl MultiverseCycle {
    /// Check if profitable after fees and gas
    pub fn net_profitable(&self, gas_price_lamports: u64) -> bool {
        // Rough calculation: profit must exceed fees + gas
        let fee_impact = (self.total_fee_bps as f64) / 10000.0 * 100.0;
        let gas_impact_pct = (gas_price_lamports as f64 / 1_000_000.0) * 0.01; // Rough USD estimate
        self.profit_pct > (fee_impact + gas_impact_pct)
    }

    pub fn __repr__(&self) -> String {
        let path_short: Vec<String> = self
            .path
            .iter()
            .map(|p| p[..8.min(p.len())].to_string())
            .collect();
        format!(
            "MultiverseCycle({}-hop: {} | +{:.3}% | liq=${} | dexes={})",
            self.hop_count,
            path_short.join("→"),
            self.profit_pct,
            self.min_liquidity_usd,
            self.dexes.join(",")
        )
    }
}

/// The Multiverse Scanner - explores all profitable paths across hop ranges
#[pyclass]
pub struct MultiverseScanner {
    /// Minimum hops to consider (default: 2)
    min_hops: usize,

    /// Maximum hops to consider (default: 5)
    max_hops: usize,

    /// Minimum profit threshold per hop level (indexed by hop count)
    /// e.g., thresholds[3] = 0.1 means 3-hop needs 0.1% profit
    min_profit_thresholds: HashMap<usize, f64>,

    /// Minimum liquidity threshold in USD
    min_liquidity_usd: u64,

    /// Maximum cycles to return per hop level
    max_cycles_per_level: usize,

    /// Memoization cache for sub-path profitability
    /// Key: (start_mint, end_mint, hops) -> best_weight
    memo_cache: HashMap<(String, String, usize), f64>,
}

#[pymethods]
impl MultiverseScanner {
    #[new]
    #[pyo3(signature = (
        min_hops = 2,
        max_hops = 5,
        min_liquidity_usd = 5000,
        max_cycles_per_level = 50
    ))]
    pub fn new(
        min_hops: usize,
        max_hops: usize,
        min_liquidity_usd: u64,
        max_cycles_per_level: usize,
    ) -> Self {
        // Default profit thresholds (higher hops = lower threshold since more fee accumulation)
        let mut thresholds = HashMap::new();
        thresholds.insert(2, 0.20); // 2-hop: need 0.20% (high competition)
        thresholds.insert(3, 0.15); // 3-hop: need 0.15%
        thresholds.insert(4, 0.10); // 4-hop: need 0.10% (the alpha zone)
        thresholds.insert(5, 0.08); // 5-hop: need 0.08% (deep path exploration)

        Self {
            min_hops: min_hops.clamp(2, 5),
            max_hops: max_hops.clamp(2, 5),
            min_profit_thresholds: thresholds,
            min_liquidity_usd,
            max_cycles_per_level,
            memo_cache: HashMap::new(),
        }
    }

    /// Set custom profit threshold for a specific hop count
    pub fn set_threshold(&mut self, hop_count: usize, min_profit_pct: f64) {
        if (2..=5).contains(&hop_count) {
            self.min_profit_thresholds
                .insert(hop_count, min_profit_pct / 100.0);
        }
    }

    /// Scan the graph for all profitable cycles across all hop levels
    pub fn scan_multiverse(&mut self, graph: &HopGraph, start_mint: &str) -> MultiverseResult {
        use std::time::Instant;
        let start_time = Instant::now();

        // Clear memo cache for fresh scan
        self.memo_cache.clear();

        let mut all_cycles: HashMap<usize, Vec<MultiverseCycle>> = HashMap::new();
        let mut stats = ScanStats::default();

        // Early exit if start node doesn't exist
        if !graph.has_node(start_mint) {
            return MultiverseResult {
                cycles_by_hops: all_cycles,
                best_cycle: None,
                scan_stats: stats,
            };
        }

        // Tiered DFS for each hop level
        for hop_level in self.min_hops..=self.max_hops {
            let threshold = self
                .min_profit_thresholds
                .get(&hop_level)
                .copied()
                .unwrap_or(0.10);

            let cycles =
                self.find_cycles_at_level(graph, start_mint, hop_level, threshold, &mut stats);

            if !cycles.is_empty() {
                all_cycles.insert(hop_level, cycles);
            }
        }

        // Find best cycle across all levels
        let best_cycle = all_cycles
            .values()
            .flatten()
            .max_by(|a, b| a.profit_pct.partial_cmp(&b.profit_pct).unwrap())
            .cloned();

        stats.total_cycles_found = all_cycles.values().map(|v| v.len()).sum();
        stats.scan_time_ms = start_time.elapsed().as_secs_f64() * 1000.0;
        stats.memoization_hits = self.memo_cache.len();

        MultiverseResult {
            cycles_by_hops: all_cycles,
            best_cycle,
            scan_stats: stats,
        }
    }

    /// Get scanner configuration
    pub fn get_config(&self) -> HashMap<String, f64> {
        let mut config = HashMap::new();
        config.insert("min_hops".to_string(), self.min_hops as f64);
        config.insert("max_hops".to_string(), self.max_hops as f64);
        config.insert(
            "min_liquidity_usd".to_string(),
            self.min_liquidity_usd as f64,
        );
        config
    }

    /// Clear the memoization cache
    pub fn clear_cache(&mut self) {
        self.memo_cache.clear();
    }
}

impl MultiverseScanner {
    /// Find cycles at a specific hop level
    fn find_cycles_at_level(
        &mut self,
        graph: &HopGraph,
        start_mint: &str,
        target_hops: usize,
        min_profit: f64,
        stats: &mut ScanStats,
    ) -> Vec<MultiverseCycle> {
        let mut cycles = Vec::new();

        let initial_edges = graph.get_outbound(start_mint);

        for edge in initial_edges {
            if edge.liquidity_usd < self.min_liquidity_usd {
                stats.paths_pruned += 1;
                continue;
            }

            self.dfs_exact_hops(
                graph,
                start_mint,
                &edge.target_mint,
                vec![start_mint.to_string(), edge.target_mint.clone()],
                vec![edge.pool_address.clone()],
                vec![edge.dex.clone()],
                edge.weight,
                edge.liquidity_usd,
                edge.fee_bps as u32,
                1, // current depth
                target_hops,
                min_profit,
                &mut cycles,
                stats,
            );
        }

        // Sort by profit and limit
        cycles.sort_by(|a, b| b.profit_pct.partial_cmp(&a.profit_pct).unwrap());
        cycles.truncate(self.max_cycles_per_level);

        cycles
    }

    /// DFS that finds cycles at EXACTLY target_hops depth
    #[allow(clippy::too_many_arguments)]
    fn dfs_exact_hops(
        &mut self,
        graph: &HopGraph,
        start_mint: &str,
        current_mint: &str,
        path: Vec<String>,
        pools: Vec<String>,
        dexes: Vec<String>,
        total_weight: f64,
        min_liquidity: u64,
        total_fees: u32,
        depth: usize,
        target_hops: usize,
        min_profit: f64,
        results: &mut Vec<MultiverseCycle>,
        stats: &mut ScanStats,
    ) {
        stats.paths_explored += 1;

        // Check memoization for sub-path pruning
        let memo_key = (start_mint.to_string(), current_mint.to_string(), depth);
        if let Some(&cached_weight) = self.memo_cache.get(&memo_key) {
            // If we've seen a better path to this point, prune
            if total_weight > cached_weight {
                stats.paths_pruned += 1;
                return;
            }
        }
        self.memo_cache.insert(memo_key, total_weight);

        let edges = graph.get_outbound(current_mint);

        for edge in edges {
            // Liquidity pruning
            if edge.liquidity_usd < self.min_liquidity_usd {
                stats.paths_pruned += 1;
                continue;
            }

            // Cycle detection for intermediate nodes (not start)
            if path[1..].contains(&edge.target_mint) && edge.target_mint != start_mint {
                continue;
            }

            let new_weight = total_weight + edge.weight;
            let new_liquidity = min_liquidity.min(edge.liquidity_usd);
            let new_fees = total_fees + edge.fee_bps as u32;

            // Check if we've completed a cycle at exactly target_hops
            if edge.target_mint == start_mint && depth + 1 == target_hops {
                // Calculate profit: negative weight = profit
                let profit_pct = ((-new_weight).exp() - 1.0) * 100.0;

                if profit_pct >= min_profit * 100.0 {
                    let mut cycle_path = path.clone();
                    cycle_path.push(start_mint.to_string());

                    let mut cycle_pools = pools.clone();
                    cycle_pools.push(edge.pool_address.clone());

                    let mut cycle_dexes = dexes.clone();
                    cycle_dexes.push(edge.dex.clone());

                    // Estimate gas: ~80k CU per swap, ~5000 lamports per CU
                    let estimated_gas = (depth + 1) as u64 * 80_000 * 5;

                    results.push(MultiverseCycle {
                        path: cycle_path,
                        pool_addresses: cycle_pools,
                        hop_count: depth + 1,
                        profit_pct,
                        min_liquidity_usd: new_liquidity,
                        total_fee_bps: new_fees.min(u16::MAX as u32) as u16,
                        dexes: cycle_dexes,
                        estimated_gas_lamports: estimated_gas,
                    });
                }
                continue;
            }

            // Continue DFS if we need more hops
            if depth < target_hops - 1 {
                // Early pruning: if weight is already too positive, skip
                // (We can't possibly reach a profitable cycle)
                let remaining_hops = target_hops - depth - 1;
                let optimistic_remaining = -0.003 * remaining_hops as f64; // Best case: 0.3% per hop
                if new_weight + optimistic_remaining > 0.0 {
                    stats.paths_pruned += 1;
                    continue;
                }

                let mut new_path = path.clone();
                new_path.push(edge.target_mint.clone());

                let mut new_pools = pools.clone();
                new_pools.push(edge.pool_address.clone());

                let mut new_dexes = dexes.clone();
                new_dexes.push(edge.dex.clone());

                self.dfs_exact_hops(
                    graph,
                    start_mint,
                    &edge.target_mint,
                    new_path,
                    new_pools,
                    new_dexes,
                    new_weight,
                    new_liquidity,
                    new_fees,
                    depth + 1,
                    target_hops,
                    min_profit,
                    results,
                    stats,
                );
            }
        }
    }
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_multiverse_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<MultiverseCycle>()?;
    m.add_class::<MultiverseResult>()?;
    m.add_class::<ScanStats>()?;
    m.add_class::<MultiverseScanner>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::PoolEdge;

    fn create_multi_hop_graph() -> HopGraph {
        let mut graph = HopGraph::new();

        // Create a graph with cycles at different hop levels

        // 2-hop: SOL -> USDC -> SOL (0.5% profit)
        graph.update_edge(PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "p_sol_usdc".to_string(),
            100.0,
            25,
            1_000_000,
            1000,
            "RAYDIUM",
        ));
        graph.update_edge(PoolEdge::new(
            "USDC".to_string(),
            "SOL".to_string(),
            "p_usdc_sol".to_string(),
            0.01005,
            25,
            1_000_000,
            1000,
            "ORCA", // 0.5% profit
        ));

        // 3-hop: SOL -> USDC -> BONK -> SOL (0.8% profit)
        graph.update_edge(PoolEdge::new(
            "USDC".to_string(),
            "BONK".to_string(),
            "p_usdc_bonk".to_string(),
            10000.0,
            30,
            500_000,
            1000,
            "RAYDIUM",
        ));
        graph.update_edge(PoolEdge::new(
            "BONK".to_string(),
            "SOL".to_string(),
            "p_bonk_sol".to_string(),
            0.00000108,
            25,
            800_000,
            1000,
            "METEORA", // ~0.8% profit cycle
        ));

        // 4-hop: SOL -> USDC -> BONK -> WIF -> SOL (1.2% profit)
        graph.update_edge(PoolEdge::new(
            "BONK".to_string(),
            "WIF".to_string(),
            "p_bonk_wif".to_string(),
            0.5,
            30,
            300_000,
            1000,
            "ORCA",
        ));
        graph.update_edge(PoolEdge::new(
            "WIF".to_string(),
            "SOL".to_string(),
            "p_wif_sol".to_string(),
            0.00000218,
            25,
            600_000,
            1000,
            "RAYDIUM", // ~1.2% profit cycle
        ));

        graph
    }

    #[test]
    fn test_multiverse_scan() {
        let graph = create_multi_hop_graph();
        let mut scanner = MultiverseScanner::new(2, 4, 100_000, 10);

        let result = scanner.scan_multiverse(&graph, "SOL");

        // Should find cycles at multiple levels
        assert!(
            result.scan_stats.total_cycles_found > 0,
            "Should find cycles"
        );
        assert!(result.best_cycle.is_some(), "Should have a best cycle");

        // Best should be the most profitable
        let best = result.best_cycle.unwrap();
        assert!(best.profit_pct > 0.0, "Best cycle should be profitable");

        println!(
            "Multiverse scan found {} cycles in {:.2}ms",
            result.scan_stats.total_cycles_found, result.scan_stats.scan_time_ms
        );
        println!("Best cycle: {}", best.__repr__());
    }

    #[test]
    fn test_multiverse_scan_stats() {
        let graph = create_multi_hop_graph();
        let mut scanner = MultiverseScanner::new(2, 5, 100_000, 50);

        let result = scanner.scan_multiverse(&graph, "SOL");

        assert!(result.scan_stats.paths_explored > 0, "Should explore paths");
        assert!(result.scan_stats.scan_time_ms >= 0.0, "Should track time");
    }
}
