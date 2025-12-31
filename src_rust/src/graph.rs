// ------------------------------------------------------------------------
// GRAPH MODULE - Pool Matrix for Multi-Hop Arbitrage (Narrow Path)
// V140: Token Hopping Infrastructure
// ------------------------------------------------------------------------
//
// This module provides a directed graph data structure where:
// - Nodes = Token mints
// - Edges = Pools (with exchange rate, liquidity, fees)
// - Edge weights = -ln(exchange_rate) for Bellman-Ford cycle detection
//
// A negative cycle in this graph represents a profitable arbitrage opportunity.
// ------------------------------------------------------------------------

use pyo3::prelude::*;
use std::collections::HashMap;

/// Represents a directed edge (pool) in the token graph.
/// Each edge connects two tokens via a liquidity pool.
#[pyclass]
#[derive(Clone, Debug)]
pub struct PoolEdge {
    /// Source token mint address
    #[pyo3(get, set)]
    pub source_mint: String,

    /// Target token mint address  
    #[pyo3(get, set)]
    pub target_mint: String,

    /// Pool/AMM address
    #[pyo3(get, set)]
    pub pool_address: String,

    /// Exchange rate: how much target you get per 1 source (after fees)
    #[pyo3(get, set)]
    pub exchange_rate: f64,

    /// Edge weight for Bellman-Ford: -ln(exchange_rate)
    /// Negative cycle = sum of weights < 0 = product of rates > 1 = profit
    #[pyo3(get, set)]
    pub weight: f64,

    /// Trading fee in basis points (e.g., 25 = 0.25%)
    #[pyo3(get, set)]
    pub fee_bps: u16,

    /// Pool liquidity in USD (for bottleneck calculation)
    #[pyo3(get, set)]
    pub liquidity_usd: u64,

    /// Solana slot when this edge was last updated
    #[pyo3(get, set)]
    pub last_update_slot: u64,

    /// DEX identifier (e.g., "RAYDIUM", "ORCA", "METEORA")
    #[pyo3(get, set)]
    pub dex: String,
}

#[pymethods]
impl PoolEdge {
    #[new]
    #[pyo3(signature = (
        source_mint,
        target_mint,
        pool_address,
        exchange_rate,
        fee_bps = 25,
        liquidity_usd = 0,
        last_update_slot = 0,
        dex = "UNKNOWN"
    ))]
    pub fn new(
        source_mint: String,
        target_mint: String,
        pool_address: String,
        exchange_rate: f64,
        fee_bps: u16,
        liquidity_usd: u64,
        last_update_slot: u64,
        dex: &str,
    ) -> Self {
        // Calculate weight: -ln(rate) so negative cycles = profit
        // If rate > 1.0, weight is negative (good)
        // If rate < 1.0, weight is positive (loss)
        let weight = if exchange_rate > 0.0 {
            -exchange_rate.ln()
        } else {
            f64::INFINITY // Invalid rate, effectively disable this edge
        };

        Self {
            source_mint,
            target_mint,
            pool_address,
            exchange_rate,
            weight,
            fee_bps,
            liquidity_usd,
            last_update_slot,
            dex: dex.to_string(),
        }
    }

    /// Recalculate weight from current exchange rate
    pub fn recalculate_weight(&mut self) {
        self.weight = if self.exchange_rate > 0.0 {
            -self.exchange_rate.ln()
        } else {
            f64::INFINITY
        };
    }

    /// Check if this edge is stale (older than threshold slot)
    pub fn is_stale(&self, min_slot: u64) -> bool {
        self.last_update_slot < min_slot
    }

    /// String representation for debugging
    pub fn __repr__(&self) -> String {
        format!(
            "PoolEdge({} -> {} | rate={:.6} | liq=${} | {})",
            &self.source_mint[..8.min(self.source_mint.len())],
            &self.target_mint[..8.min(self.target_mint.len())],
            self.exchange_rate,
            self.liquidity_usd,
            self.dex
        )
    }
}

/// The Pool Matrix - Adjacency list representation of the token graph.
///
/// Optimized for:
/// - Fast edge updates (O(1) average via HashMap)
/// - Fast outbound edge lookup (O(1) for adjacency list)
/// - Memory efficiency (edges stored once, not duplicated)
#[pyclass]
pub struct HopGraph {
    /// Adjacency list: source_mint -> Vec<PoolEdge>
    edges: HashMap<String, Vec<PoolEdge>>,

    /// Pool lookup: pool_address -> (source_mint, index in edges vec)
    /// Enables O(1) updates when a pool price changes
    pool_index: HashMap<String, (String, usize)>,

    /// All unique token mints (nodes)
    nodes: std::collections::HashSet<String>,

    /// Total edge count (for stats)
    edge_count: usize,
}

#[pymethods]
impl HopGraph {
    #[new]
    pub fn new() -> Self {
        Self {
            edges: HashMap::new(),
            pool_index: HashMap::new(),
            nodes: std::collections::HashSet::new(),
            edge_count: 0,
        }
    }

    /// Update or insert an edge from WSS price feed.
    /// If the pool already exists, update it in place. Otherwise, add new edge.
    pub fn update_edge(&mut self, edge: PoolEdge) {
        // Track nodes
        self.nodes.insert(edge.source_mint.clone());
        self.nodes.insert(edge.target_mint.clone());

        // Check if pool already exists
        if let Some((source, idx)) = self.pool_index.get(&edge.pool_address) {
            // Update existing edge
            if let Some(edges) = self.edges.get_mut(source) {
                if let Some(existing) = edges.get_mut(*idx) {
                    existing.exchange_rate = edge.exchange_rate;
                    existing.weight = edge.weight;
                    existing.liquidity_usd = edge.liquidity_usd;
                    existing.last_update_slot = edge.last_update_slot;
                    existing.fee_bps = edge.fee_bps;
                    return;
                }
            }
        }

        // New edge - add to adjacency list
        let source = edge.source_mint.clone();
        let pool_addr = edge.pool_address.clone();

        let edges_vec = self.edges.entry(source.clone()).or_insert_with(Vec::new);
        let idx = edges_vec.len();
        edges_vec.push(edge);

        // Update pool index
        self.pool_index.insert(pool_addr, (source, idx));
        self.edge_count += 1;
    }

    /// Get all outbound edges from a token.
    /// Returns empty vec if token not in graph.
    pub fn get_outbound(&self, mint: &str) -> Vec<PoolEdge> {
        self.edges.get(mint).cloned().unwrap_or_default()
    }

    /// Get a specific edge by pool address.
    pub fn get_edge(&self, pool_address: &str) -> Option<PoolEdge> {
        if let Some((source, idx)) = self.pool_index.get(pool_address) {
            if let Some(edges) = self.edges.get(source) {
                return edges.get(*idx).cloned();
            }
        }
        None
    }

    /// Check if a token exists in the graph.
    pub fn has_node(&self, mint: &str) -> bool {
        self.nodes.contains(mint)
    }

    /// Get all tokens (nodes) in the graph.
    pub fn get_all_nodes(&self) -> Vec<String> {
        self.nodes.iter().cloned().collect()
    }

    /// Total unique tokens (nodes).
    pub fn node_count(&self) -> usize {
        self.nodes.len()
    }

    /// Total pools (edges).
    pub fn edge_count(&self) -> usize {
        self.edge_count
    }

    /// Get all neighbors of a token (tokens reachable in one hop).
    pub fn get_neighbors(&self, mint: &str) -> Vec<String> {
        self.edges
            .get(mint)
            .map(|edges| edges.iter().map(|e| e.target_mint.clone()).collect())
            .unwrap_or_default()
    }

    /// Prune stale edges older than the given slot threshold.
    /// Returns the number of edges pruned.
    pub fn prune_stale(&mut self, min_slot: u64) -> usize {
        let mut pruned = 0;
        let mut pools_to_remove: Vec<String> = Vec::new();

        for (source, edges) in self.edges.iter_mut() {
            let before_len = edges.len();

            // Collect pool addresses of stale edges
            for edge in edges.iter() {
                if edge.is_stale(min_slot) {
                    pools_to_remove.push(edge.pool_address.clone());
                }
            }

            // Remove stale edges
            edges.retain(|e| !e.is_stale(min_slot));

            let removed = before_len - edges.len();
            pruned += removed;
            self.edge_count -= removed;

            // Update pool index for remaining edges (indices may have shifted)
            for (idx, edge) in edges.iter().enumerate() {
                self.pool_index
                    .insert(edge.pool_address.clone(), (source.clone(), idx));
            }
        }

        // Remove pool index entries for pruned edges
        for pool_addr in pools_to_remove {
            self.pool_index.remove(&pool_addr);
        }

        // Clean up empty source entries
        self.edges.retain(|_, edges| !edges.is_empty());

        pruned
    }

    /// Clear all edges and nodes.
    pub fn clear(&mut self) {
        self.edges.clear();
        self.pool_index.clear();
        self.nodes.clear();
        self.edge_count = 0;
    }

    /// Get statistics about the graph.
    pub fn stats(&self) -> HashMap<String, usize> {
        let mut stats = HashMap::new();
        stats.insert("node_count".to_string(), self.node_count());
        stats.insert("edge_count".to_string(), self.edge_count());
        stats.insert("source_count".to_string(), self.edges.len());
        stats
    }

    /// String representation for debugging.
    pub fn __repr__(&self) -> String {
        format!(
            "HopGraph(nodes={}, edges={}, sources={})",
            self.node_count(),
            self.edge_count(),
            self.edges.len()
        )
    }
}

impl Default for HopGraph {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_graph_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<PoolEdge>()?;
    m.add_class::<HopGraph>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_edge_weight_calculation() {
        // Rate 1.01 (1% profit) should have negative weight
        let edge = PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "pool1".to_string(),
            1.01,
            25,
            100000,
            1000,
            "RAYDIUM",
        );
        assert!(
            edge.weight < 0.0,
            "Profitable rate should have negative weight"
        );

        // Rate 0.99 (1% loss) should have positive weight
        let edge2 = PoolEdge::new(
            "USDC".to_string(),
            "SOL".to_string(),
            "pool2".to_string(),
            0.99,
            25,
            100000,
            1000,
            "RAYDIUM",
        );
        assert!(edge2.weight > 0.0, "Loss rate should have positive weight");
    }

    #[test]
    fn test_graph_update() {
        let mut graph = HopGraph::new();

        let edge1 = PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "pool1".to_string(),
            100.0,
            25,
            1000000,
            1000,
            "RAYDIUM",
        );

        graph.update_edge(edge1);

        assert_eq!(graph.node_count(), 2);
        assert_eq!(graph.edge_count(), 1);
        assert!(graph.has_node("SOL"));
        assert!(graph.has_node("USDC"));

        // Update same pool with new rate
        let edge2 = PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "pool1".to_string(),
            101.0, // New rate
            25,
            1000000,
            1001,
            "RAYDIUM",
        );

        graph.update_edge(edge2);

        // Should still be 1 edge (updated in place)
        assert_eq!(graph.edge_count(), 1);

        // Verify rate was updated
        let fetched = graph.get_edge("pool1").unwrap();
        assert!((fetched.exchange_rate - 101.0).abs() < 0.001);
    }

    #[test]
    fn test_graph_prune() {
        let mut graph = HopGraph::new();

        // Add edge at slot 1000
        let edge1 = PoolEdge::new(
            "SOL".to_string(),
            "USDC".to_string(),
            "pool1".to_string(),
            100.0,
            25,
            1000000,
            1000,
            "RAYDIUM",
        );
        graph.update_edge(edge1);

        // Add edge at slot 2000
        let edge2 = PoolEdge::new(
            "USDC".to_string(),
            "BONK".to_string(),
            "pool2".to_string(),
            0.001,
            30,
            500000,
            2000,
            "ORCA",
        );
        graph.update_edge(edge2);

        assert_eq!(graph.edge_count(), 2);

        // Prune edges older than slot 1500
        let pruned = graph.prune_stale(1500);

        assert_eq!(pruned, 1);
        assert_eq!(graph.edge_count(), 1);
        assert!(graph.get_edge("pool1").is_none());
        assert!(graph.get_edge("pool2").is_some());
    }
}
