use solana_sdk::{
    signature::{Keypair, Signer},
    hash::Hash,
    instruction::Instruction,
    transaction::VersionedTransaction,
    message::{v0, VersionedMessage},
};
use std::str::FromStr;
use pyo3::prelude::*;

// ------------------------------------------------------------------------
// SECTION 1: ARBITRAGE LOGIC (HOT PATH)
// ------------------------------------------------------------------------

/// Go/No-Go Decision Engine for Net Profit.
/// Moves float math to Rust to avoid GIL and precision overhead.
#[pyfunction]
fn calculate_net_profit(spread_raw: f64, trade_size: f64, jito_tip: f64, route_friction: f64) -> PyResult<f64> {
    let gross = trade_size * (spread_raw / 100.0);
    let net = gross - jito_tip - route_friction;
    Ok(net)
}

/// Batch processing to eliminate FFI overhead.
/// Processes thousands of trades in a single Rust call.
#[pyfunction]
fn calculate_net_profit_batch(
    spreads: Vec<f64>,
    trade_size: f64,
    jito_tip: f64,
    route_friction: f64
) -> PyResult<Vec<f64>> {
    let mut results = Vec::with_capacity(spreads.len());
    for spread in spreads {
        let gross = trade_size * (spread / 100.0);
        let net = gross - jito_tip - route_friction;
        results.push(net);
    }
    Ok(results)
}

// ------------------------------------------------------------------------
// SECTION 2: CHAOS SHIELD (ESTIMATORS & CHECKS)
// ------------------------------------------------------------------------

/// High-Fidelity Compute Unit Estimator.
/// Simulates transaction "weight" to prevent CU Bloat.
/// "Reality Parity" calibration based on Mainnet averages (Q4 2024).
#[pyfunction]
fn estimate_compute_units(
    ops: Vec<String>,
    num_accounts: u32,
    num_signers: u32,
    safety_margin_percent: f64
) -> PyResult<u32> {
    let mut estimated_cu: f64 = 0.0; 

    // 1. Signature Cost
    estimated_cu += (num_signers as f64) * 1_500.0;

    // 2. Serialization Overhead
    estimated_cu += (num_accounts as f64) * 850.0;

    // 3. Instruction Simulation
    for op in ops {
        let cost = match op.as_str() {
            "transfer_sol" => 500.0,
            "transfer_spl" => 4_500.0,
            "create_ata" => 25_000.0,
            "close_account" => 3_000.0,
            "memo" => 100.0,
            "raydium_swap_v4" => 80_000.0,
            "raydium_swap_cpcc" => 120_000.0,
            "orca_whirlpool_swap" => 145_000.0,
            "meteora_dlmm_swap" => 70_000.0,
            "jupiter_aggregator" => 180_000.0,
            "phoenix_swap" => 25_000.0,
            _ => 10_000.0,
        };
        estimated_cu += cost;
    }

    // 4. Safety Margin
    estimated_cu *= 1.0 + (safety_margin_percent / 100.0);

    if estimated_cu < 5_000.0 {
        estimated_cu = 5_000.0;
    }

    Ok(estimated_cu.ceil() as u32)
}

/// Liveness Check: Ensures the RPC data isn't stale.
/// Returns error if the gap is > 2 slots.
fn verify_slot_sync(rpc_slot: u64, jito_slot: u64) -> PyResult<()> {
    let gap = if rpc_slot > jito_slot {
        rpc_slot - jito_slot
    } else {
        jito_slot - rpc_slot
    };

    if gap > 2 {
        return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("State Desync: Gap is {} slots. Aborting to prevent Ghost Trade.", gap)
        ));
    }
    Ok(())
}

// ------------------------------------------------------------------------
// SECTION 3: ATOMIC BUILDER (TRANSACTION COMPOSITION)
// ------------------------------------------------------------------------

/// Atomic V0 Transaction Builder.
/// Constructs, Signs, and Serializes in one Rust call.
/// 
/// # Arguments
/// * `instruction_payload` - Bincode-serialized `solana_sdk::instruction::Instruction`
/// * `payer_key_b58` - Base58 private key of payer
/// * `blockhash_b58` - Recent blockhash
/// * `rpc_slot` - Current RPC slot for liveness check
/// * `jito_slot` - Last Jito bundle slot (optional, pass 0 to skip)
/// 
/// # Returns
/// Serialized VersionedTransaction (bincode)
#[pyfunction]
#[pyo3(signature = (instruction_payload, payer_key_b58, blockhash_b58, rpc_slot, jito_slot=0))]
fn build_atomic_transaction(
    instruction_payload: Vec<u8>, 
    payer_key_b58: String,
    blockhash_b58: String,
    rpc_slot: u64,
    jito_slot: u64
) -> PyResult<Vec<u8>> {
    
    // 1. Safety Check: Liveness (if Jito slot provided)
    if jito_slot > 0 {
        verify_slot_sync(rpc_slot, jito_slot)?;
    }

    // 2. Parsers (Fast Rust Parsing)
    let payer = Keypair::from_base58_string(&payer_key_b58);
    let blockhash = Hash::from_str(&blockhash_b58)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

    // 3. Instruction Deserialization
    // We expect a valid, fully constructed Instruction from "The Forge"
    let instruction: Instruction = bincode::deserialize(&instruction_payload)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Failed to deserialize instruction: {}", e)
        ))?;

    // 4. Message V0 Construction
    let message = v0::Message::try_compile(
        &payer.pubkey(), 
        &[instruction], 
        &[], // Address Lookup Tables (Empty for now)
        blockhash
    ).map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

    // 5. Signing
    let versioned_msg = VersionedMessage::V0(message);
    let tx = VersionedTransaction::try_new(versioned_msg, &[&payer])
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

    // 6. Serialization
    let serialized = bincode::serialize(&tx)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

    Ok(serialized)
}


// ------------------------------------------------------------------------
// SECTION 4: PATHFINDER (GRAPH ENGINE)
// ------------------------------------------------------------------------

use std::collections::{HashMap, VecDeque};

#[derive(Clone)]
struct Edge {
    target_id: usize, // Cache-friendly ID
    pool_id: String,
    weight: f64,      // -ln(price)
}

#[pyclass]
struct Graph {
    adjacency: Vec<Vec<Edge>>,
    mint_to_id: HashMap<String, usize>,
    id_to_mint: Vec<String>,
}

#[pymethods]
impl Graph {
    #[new]
    fn new() -> Self {
        Graph {
            adjacency: Vec::new(),
            mint_to_id: HashMap::new(),
            id_to_mint: Vec::new(),
        }
    }

    /// Adds or updates an edge in the graph.
    /// Automatically interns new tokens to usize IDs.
    /// Price is converted to -ln(price) for additive cycle detection.
    fn update_edge(&mut self, source_mint: String, target_mint: String, pool_id: String, price: f64) {
        // 1. Intern Source
        let source_id = if let Some(&id) = self.mint_to_id.get(&source_mint) {
            id
        } else {
            let id = self.id_to_mint.len();
            self.mint_to_id.insert(source_mint.clone(), id);
            self.id_to_mint.push(source_mint);
            self.adjacency.push(Vec::new());
            id
        };

        // 2. Intern Target
        let target_id = if let Some(&id) = self.mint_to_id.get(&target_mint) {
            id
        } else {
            let id = self.id_to_mint.len();
            self.mint_to_id.insert(target_mint.clone(), id);
            self.id_to_mint.push(target_mint);
            self.adjacency.push(Vec::new());
            id
        };

        // 3. Calculate Weight (-ln(price))
        // Protect against <= 0 prices
        let safe_price = if price <= 1e-9 { 1e-9 } else { price };
        let weight = -safe_price.ln();

        // 4. Upsert Edge
        let edges = &mut self.adjacency[source_id];
        // Check if edge exists to update it (O(k) where k is small degree)
        if let Some(edge) = edges.iter_mut().find(|e| e.target_id == target_id) {
            edge.weight = weight;
            edge.pool_id = pool_id;
        } else {
            edges.push(Edge {
                target_id,
                pool_id,
                weight,
            });
        }
    }

    /// SPFA (Shortest Path Faster Algorithm) for Negative Cycle Detection.
    /// Returns a list of Pool IDs forming the arbitrage loop.
    fn find_arbitrage_loop(&self, start_mint: String) -> PyResult<Vec<String>> {
        let start_id = match self.mint_to_id.get(&start_mint) {
            Some(&id) => id,
            None => return Ok(vec![]), // Token not in graph
        };

        let n = self.id_to_mint.len();
        let mut dist = vec![f64::INFINITY; n];
        let mut parent_node = vec![None; n];
        let mut parent_pool = vec![String::new(); n];
        let mut count = vec![0; n];
        let mut in_queue = vec![false; n];
        let mut queue = VecDeque::new();

        dist[start_id] = 0.0;
        queue.push_back(start_id);
        in_queue[start_id] = true;

        while let Some(u) = queue.pop_front() {
            in_queue[u] = false;

            for edge in &self.adjacency[u] {
                // Relaxation
                if dist[u] + edge.weight < dist[edge.target_id] {
                    dist[edge.target_id] = dist[u] + edge.weight;
                    parent_node[edge.target_id] = Some(u);
                    parent_pool[edge.target_id] = edge.pool_id.clone();

                    if !in_queue[edge.target_id] {
                        count[edge.target_id] += 1;
                        
                        // Negative Cycle Check (Limit iterations to avoid infinite loops)
                        // In SPFA, visiting a node >= N times usually means a cycle.
                        // For arbitrage, we can be more aggressive (e.g. depth > 3).
                        if count[edge.target_id] > n {
                            // Cycle detected! Reconstruct.
                            return Ok(self.reconstruct_path(edge.target_id, &parent_node, &parent_pool));
                        }

                        queue.push_back(edge.target_id);
                        in_queue[edge.target_id] = true;
                    }
                }
            }
        }
        Ok(vec![])
    }

    /// Scans for arbitrage cycles starting from multiple base tokens.
    /// Returns a list of paths (each path is a list of pool IDs).
    /// Uses Rayon for parallel execution across CPU cores.
    fn find_all_cycles(&self, start_mints: Vec<String>) -> PyResult<Vec<Vec<String>>> {
        use rayon::prelude::*;
        
        // Parallel Iterator
        let results: Vec<Vec<String>> = start_mints.par_iter()
            .map(|mint| {
                // We typically need to handle errors inside map/fold
                // Graph access is read-only, so ThreadSafe.
                // However, `find_arbitrage_loop` returns PyResult.
                // We unwrap or handle here.
                match self.find_arbitrage_loop(mint.clone()) {
                    Ok(path) => path,
                    Err(_) => vec![],
                }
            })
            .filter(|path| !path.is_empty())
            .collect();
            
        Ok(results)
    }
}

impl Graph {
    fn reconstruct_path(&self, end_id: usize, parent_node: &[Option<usize>], parent_pool: &[String]) -> Vec<String> {
        let mut path = Vec::new();
        let mut curr = end_id;
        let mut visited = vec![false; self.id_to_mint.len()];

        // Backtrack to find the cycle
        while let Some(prev) = parent_node[curr] {
            if visited[curr] {
                 // We closed the loop. Now strictly record the pool IDs.
                 // We need to trace forward from this point or just capture the segment.
                 // Simplified: Just push pool IDs until we loop.
                 break;
            }
            visited[curr] = true;
            path.push(parent_pool[curr].clone());
            curr = prev;
        }

        // The path is reversed (from end to start)
        path.reverse();
        path
    }
}

// ------------------------------------------------------------------------
// SECTION 5: LOG PARSER (THE WIRE)
// ------------------------------------------------------------------------
mod log_parser;

// ------------------------------------------------------------------------
// SECTION 6: MODULE REGISTRATION
// ------------------------------------------------------------------------
// ------------------------------------------------------------------------
// SECTION 6: SLAB DECODER (PHASE 4)
// ------------------------------------------------------------------------
mod slab_decoder;

// ------------------------------------------------------------------------
// SECTION 7: AMM MATH ENGINE (THE ORACLE)
// ------------------------------------------------------------------------
mod amm_math;

// ------------------------------------------------------------------------
// SECTION 8: INSTRUCTION BUILDER (THE FORGE)
// ------------------------------------------------------------------------
mod instruction_builder;

// ------------------------------------------------------------------------
// SECTION 9: NETWORK SUBMITTER (THE BLAST)
// ------------------------------------------------------------------------
mod network_submitter;

// ------------------------------------------------------------------------
// SECTION 10: SLOT CONSENSUS (THE ACCURACY GUARD)
// ------------------------------------------------------------------------
mod slot_consensus;

// ------------------------------------------------------------------------
// SECTION 11: TICK ARRAY MANAGER (CLMM CORRECTNESS)
// ------------------------------------------------------------------------
mod tick_array_manager;

// ------------------------------------------------------------------------
// SECTION 14: UNIFIED TRADE ROUTER (THE MUSCLE)
// ------------------------------------------------------------------------
pub mod router;
pub mod wss_aggregator;

// ------------------------------------------------------------------------
// SECTION 15: MODULE REGISTRATION
// ------------------------------------------------------------------------

/// A Python module implemented in Rust.
#[pymodule]
fn phantom_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<Graph>()?;
    m.add_class::<log_parser::SwapEvent>()?;
    m.add_function(wrap_pyfunction!(calculate_net_profit, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_net_profit_batch, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_compute_units, m)?)?;
    m.add_function(wrap_pyfunction!(build_atomic_transaction, m)?)?;
    m.add_function(wrap_pyfunction!(log_parser::parse_raydium_log, m)?)?;
    m.add_function(wrap_pyfunction!(log_parser::parse_universal_log, m)?)?;
    
    // AMM Math (The Oracle)
    amm_math::register_amm_functions(m)?;
    
    // Instruction Builder (The Forge)
    instruction_builder::register_instruction_functions(m)?;
    
    // Slab Decoder (The Ledger)
    slab_decoder::register_slab_functions(m)?;
    
    // Network Submitter (The Blast)
    network_submitter::register_network_functions(m)?;
    
    // Slot Consensus (The Accuracy Guard)
    slot_consensus::register_consensus_classes(m)?;
    
    // Tick Array Manager (CLMM Correctness)
    tick_array_manager::register_tick_array_functions(m)?;
    
    // WSS Aggregator (The Wire v2)
    wss_aggregator::register_wss_aggregator_classes(m)?;
    
    // Unified Trade Router (The Muscle)
    m.add_class::<router::ExecutionPath>()?;
    m.add_class::<router::UnifiedTradeRouter>()?;
    
    Ok(())
}



