use solana_sdk::{
    transaction::VersionedTransaction,
    message::{v0, VersionedMessage},
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    hash::Hash,
    instruction::Instruction,
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
#[pyfunction]
fn build_atomic_transaction(
    instruction_data_b64: String, // Placeholder for real instruction building
    payer_key_b58: String,
    blockhash_b58: String,
    rpc_slot: u64,
    jito_slot: u64
) -> PyResult<Vec<u8>> {
    
    // 1. Safety Check: Liveness
    verify_slot_sync(rpc_slot, jito_slot)?;

    // 2. Parsers (Fast Rust Parsing)
    let payer = Keypair::from_base58_string(&payer_key_b58);
    let blockhash = Hash::from_str(&blockhash_b58)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

    // 3. Instruction Assembly (Simplified Logic for Prototype)
    // For now, we mock a "Memo" instruction to prove the builder works.
    let memo_program_id = Pubkey::from_str("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcQb").unwrap();
    let instruction = Instruction::new_with_bytes(
        memo_program_id, 
        instruction_data_b64.as_bytes(), 
        vec![]
    );

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
// SECTION 4: MODULE REGISTRATION
// ------------------------------------------------------------------------

/// A Python module implemented in Rust.
#[pymodule]
fn phantom_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_net_profit, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_net_profit_batch, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_compute_units, m)?)?;
    m.add_function(wrap_pyfunction!(build_atomic_transaction, m)?)?;
    Ok(())
}
