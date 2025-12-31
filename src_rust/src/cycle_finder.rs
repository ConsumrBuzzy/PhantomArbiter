// ------------------------------------------------------------------------
// CYCLE FINDER MODULE - Bellman-Ford Negative Cycle Detection
// V140: Token Hopping Infrastructure
// ------------------------------------------------------------------------
//
// This module implements the core pathfinding algorithm for multi-hop arbitrage.
//
// Key insight: If we define edge weight = -ln(exchange_rate), then:
// - A profitable cycle has: rate1 * rate2 * rate3 > 1.0
// - ln(rate1) + ln(rate2) + ln(rate3) > 0
// - -ln(rate1) + -ln(rate2) + -ln(rate3) < 0 (negative cycle!)
//
// Therefore, finding a negative cycle = finding a profitable arbitrage path.
// ------------------------------------------------------------------------

use crate::graph::HopGraph;
use pyo3::prelude::*;
use std::collections::HashMap;

/// A profitable arbitrage cycle detected by the algorithm.
#[pyclass]
#[derive(Clone, Debug)]
pub struct HopCycle {
    /// Token mints in order: [SOL, TokenA, TokenB, SOL]
    #[pyo3(get)]
    pub path: Vec<String>,

    /// Pool addresses to traverse in order
    #[pyo3(get)]
    pub pool_addresses: Vec<String>,

    /// Theoretical profit percentage (e.g., 0.5 = 0.5%)
    #[pyo3(get)]
    pub theoretical_profit_pct: f64,

    /// Minimum liquidity across all pools (bottleneck)
    #[pyo3(get)]
    pub min_liquidity_usd: u64,

    /// Total fees across all swaps (in basis points)
    #[pyo3(get)]
    pub total_fee_bps: u16,

    /// Number of hops (legs) in this cycle
    #[pyo3(get)]
    pub hop_count: usize,

    /// Sum of edge weights (should be negative for profit)
    #[pyo3(get)]
    pub total_weight: f64,
}

#[pymethods]
impl HopCycle {
    /// Check if this cycle is still profitable (threshold in %)
    pub fn is_profitable(&self, min_profit_pct: f64) -> bool {
        self.theoretical_profit_pct >= min_profit_pct
    }

    /// Get the DEXes involved in this cycle
    pub fn get_dexes(&self) -> Vec<String> {
        // Would need to store DEX info - for now return empty
        Vec::new()
    }

    /// String representation
    pub fn __repr__(&self) -> String {
        let path_str: Vec<String> = self
            .path
            .iter()
            .map(|m| m[..8.min(m.len())].to_string())
            .collect();
        format!(
            "HopCycle({} | profit={:.3}% | liq=${} | hops={})",
            path_str.join(" → "),
            self.theoretical_profit_pct,
            self.min_liquidity_usd,
            self.hop_count
        )
    }
}

/// The Cycle Finder - Detects profitable arbitrage cycles using Bellman-Ford.
///
/// Algorithm overview:
/// 1. Initialize distances: dist[start] = 0, all others = infinity
/// 2. Relax all edges V-1 times (V = number of vertices)
/// 3. On Vth iteration, any edge that can still be relaxed indicates a negative cycle
/// 4. Reconstruct the cycle path from detected vertices
///
/// Optimization: We use a bounded DFS approach for small hop counts (3-5)
/// which is more efficient than full Bellman-Ford for sparse graphs.
#[pyclass]
pub struct CycleFinder {
    /// Maximum number of hops to consider (3, 4, or 5)
    max_hops: usize,

    /// Minimum profit threshold (as decimal, e.g., 0.002 = 0.2%)
    min_profit_threshold: f64,

    /// Minimum liquidity threshold in USD
    min_liquidity_usd: u64,
}

#[pymethods]
impl CycleFinder {
    #[new]
    #[pyo3(signature = (max_hops = 4, min_profit_threshold = 0.002, min_liquidity_usd = 5000))]
    pub fn new(max_hops: usize, min_profit_threshold: f64, min_liquidity_usd: u64) -> Self {
        Self {
            max_hops: max_hops.clamp(3, 5), // Enforce 3-5 hops
            min_profit_threshold,
            min_liquidity_usd,
        }
    }

    /// Find all profitable cycles starting and ending at the given token.
    /// Uses bounded DFS which is more efficient for small hop counts.
    pub fn find_cycles(&self, graph: &HopGraph, start_mint: &str) -> Vec<HopCycle> {
        let mut cycles = Vec::new();

        // Early exit if start node doesn't exist
        if !graph.has_node(start_mint) {
            return cycles;
        }

        // State for DFS: (current_path, current_pools, total_weight, min_liquidity, total_fees)
        let initial_edges = graph.get_outbound(start_mint);

        for edge in initial_edges {
            // Skip edges below liquidity threshold
            if edge.liquidity_usd < self.min_liquidity_usd {
                continue;
            }

            self.dfs_find_cycles(
                graph,
                start_mint,
                &edge.target_mint,
                vec![start_mint.to_string(), edge.target_mint.clone()],
                vec![edge.pool_address.clone()],
                edge.weight,
                edge.liquidity_usd,
                edge.fee_bps as u32,
                1, // depth
                &mut cycles,
            );
        }

        // Sort by profit (descending)
        cycles.sort_by(|a, b| {
            b.theoretical_profit_pct
                .partial_cmp(&a.theoretical_profit_pct)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        cycles
    }

    /// Validate that a specific path is still profitable.
    /// Returns None if path is no longer valid or profitable.
    pub fn validate_path(&self, graph: &HopGraph, path: Vec<String>) -> Option<HopCycle> {
        if path.len() < 3 || path.first() != path.last() {
            return None; // Invalid cycle structure
        }

        let mut total_weight = 0.0;
        let mut min_liquidity = u64::MAX;
        let mut total_fees: u32 = 0;
        let mut pool_addresses = Vec::new();

        for i in 0..path.len() - 1 {
            let source = &path[i];
            let target = &path[i + 1];

            // Find edge from source to target
            let edges = graph.get_outbound(source);
            let edge = edges.iter().find(|e| e.target_mint == *target)?;

            total_weight += edge.weight;
            min_liquidity = min_liquidity.min(edge.liquidity_usd);
            total_fees += edge.fee_bps as u32;
            pool_addresses.push(edge.pool_address.clone());
        }

        // Calculate profit: if weight < 0, cycle is profitable
        // profit = e^(-total_weight) - 1
        let profit_pct = ((-total_weight).exp() - 1.0) * 100.0;

        if profit_pct < self.min_profit_threshold * 100.0 {
            return None;
        }

        Some(HopCycle {
            path: path.to_vec(),
            pool_addresses,
            theoretical_profit_pct: profit_pct,
            min_liquidity_usd: min_liquidity,
            total_fee_bps: total_fees.min(u16::MAX as u32) as u16,
            hop_count: path.len() - 1,
            total_weight,
        })
    }

    /// Get the finder's configuration
    pub fn get_config(&self) -> HashMap<String, f64> {
        let mut config = HashMap::new();
        config.insert("max_hops".to_string(), self.max_hops as f64);
        config.insert(
            "min_profit_threshold".to_string(),
            self.min_profit_threshold,
        );
        config.insert(
            "min_liquidity_usd".to_string(),
            self.min_liquidity_usd as f64,
        );
        config
    }
}

impl CycleFinder {
    /// Recursive DFS to find cycles back to start.
    #[allow(clippy::too_many_arguments)]
    fn dfs_find_cycles(
        &self,
        graph: &HopGraph,
        start_mint: &str,
        current_mint: &str,
        path: Vec<String>,
        pools: Vec<String>,
        total_weight: f64,
        min_liquidity: u64,
        total_fees: u32,
        depth: usize,
        results: &mut Vec<HopCycle>,
    ) {
        // Get outbound edges from current node
        let edges = graph.get_outbound(current_mint);

        for edge in edges {
            // Skip edges below liquidity threshold
            if edge.liquidity_usd < self.min_liquidity_usd {
                continue;
            }

            // Skip if we'd revisit an intermediate node (not start)
            if path[1..].contains(&edge.target_mint) && edge.target_mint != start_mint {
                continue;
            }

            let new_weight = total_weight + edge.weight;
            let new_liquidity = min_liquidity.min(edge.liquidity_usd);
            let new_fees = total_fees + edge.fee_bps as u32;

            // Check if we've returned to start (cycle found!)
            if edge.target_mint == start_mint && depth >= 2 {
                // Calculate profit percentage
                // If total_weight < 0, profit = e^(-weight) - 1
                let profit_pct = ((-new_weight).exp() - 1.0) * 100.0;

                if profit_pct >= self.min_profit_threshold * 100.0 {
                    let mut cycle_path = path.clone();
                    cycle_path.push(start_mint.to_string());

                    let mut cycle_pools = pools.clone();
                    cycle_pools.push(edge.pool_address.clone());

                    results.push(HopCycle {
                        path: cycle_path,
                        pool_addresses: cycle_pools,
                        theoretical_profit_pct: profit_pct,
                        min_liquidity_usd: new_liquidity,
                        total_fee_bps: new_fees.min(u16::MAX as u32) as u16,
                        hop_count: depth + 1,
                        total_weight: new_weight,
                    });
                }
                continue; // Don't recurse past a found cycle
            }

            // Continue DFS if we haven't hit max depth
            if depth < self.max_hops - 1 {
                let mut new_path = path.clone();
                new_path.push(edge.target_mint.clone());

                let mut new_pools = pools.clone();
                new_pools.push(edge.pool_address.clone());

                self.dfs_find_cycles(
                    graph,
                    start_mint,
                    &edge.target_mint,
                    new_path,
                    new_pools,
                    new_weight,
                    new_liquidity,
                    new_fees,
                    depth + 1,
                    results,
                );
            }
        }
    }
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_cycle_finder_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<HopCycle>()?;
    m.add_class::<CycleFinder>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::PoolEdge;

    fn create_test_graph() -> HopGraph {
        let mut graph = HopGraph::new();

        // Create a simple triangle: SOL -> USDC -> BONK -> SOL
        // With rates that create a profitable cycle

        // SOL -> USDC: 100 USDC per SOL
        graph.update_edge(PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "pool_sol_usdc".to_string(),
            100.0,
            25,
            1000000,
            1000,
            "RAYDIUM",
        ));

        // USDC -> BONK: 10000 BONK per USDC
        graph.update_edge(PoolEdge::new(
            "USDC".to_string(),
            "BONK".to_string(),
            "pool_usdc_bonk".to_string(),
            10000.0,
            30,
            500000,
            1000,
            "ORCA",
        ));

        // BONK -> SOL: 0.0000102 SOL per BONK (creates 2% profit cycle)
        // 1 SOL -> 100 USDC -> 1,000,000 BONK -> 1.02 SOL
        graph.update_edge(PoolEdge::new(
            "BONK".to_string(),
            "SOL".to_string(),
            "pool_bonk_sol".to_string(),
            0.00000102,
            25,
            800000,
            1000,
            "RAYDIUM",
        ));

        graph
    }

    #[test]
    fn test_find_profitable_cycle() {
        let graph = create_test_graph();
        let finder = CycleFinder::new(4, 0.001, 1000); // 0.1% min profit

        let cycles = finder.find_cycles(&graph, "SOL");

        assert!(!cycles.is_empty(), "Should find at least one cycle");

        let best_cycle = &cycles[0];
        assert_eq!(best_cycle.hop_count, 3, "Should be a 3-hop cycle");
        assert!(
            best_cycle.theoretical_profit_pct > 0.0,
            "Should be profitable"
        );
        assert_eq!(
            best_cycle.path.first(),
            best_cycle.path.last(),
            "Should start and end at same token"
        );
    }

    #[test]
    fn test_validate_path() {
        let graph = create_test_graph();
        let finder = CycleFinder::new(4, 0.001, 1000);

        let path = vec![
            "SOL".to_string(),
            "USDC".to_string(),
            "BONK".to_string(),
            "SOL".to_string(),
        ];

        let result = finder.validate_path(&graph, path);
        assert!(result.is_some(), "Valid path should return a cycle");

        let cycle = result.unwrap();
        assert_eq!(cycle.pool_addresses.len(), 3);
    }

    #[test]
    fn test_no_cycle_when_unprofitable() {
        let mut graph = HopGraph::new();

        // Create a cycle with losing rates
        graph.update_edge(PoolEdge::new(
            "A".to_string(),
            "B".to_string(),
            "p1".to_string(),
            0.9,
            25,
            100000,
            1000,
            "TEST",
        ));
        graph.update_edge(PoolEdge::new(
            "B".to_string(),
            "C".to_string(),
            "p2".to_string(),
            0.9,
            25,
            100000,
            1000,
            "TEST",
        ));
        graph.update_edge(PoolEdge::new(
            "C".to_string(),
            "A".to_string(),
            "p3".to_string(),
            0.9,
            25,
            100000,
            1000,
            "TEST",
        ));

        let finder = CycleFinder::new(4, 0.001, 1000);
        let cycles = finder.find_cycles(&graph, "A");

        assert!(
            cycles.is_empty(),
            "Should not find cycles when all are unprofitable"
        );
    }
}
