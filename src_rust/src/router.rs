use base64::Engine;
use pyo3::prelude::*;
use solana_sdk::instruction::Instruction;
use solana_sdk::pubkey::Pubkey;
use solana_sdk::signature::{Keypair, Signer};
use solana_sdk::system_instruction;
use solana_sdk::transaction::Transaction;
use std::str::FromStr; // Fix base64 trait scope

use crate::network_submitter::{get_runtime, submit_jito_async, submit_rpc_async};

#[pyclass]
#[derive(Clone, Debug)]
pub enum ExecutionPath {
    AtomicJito,    // For Arbitrage (Bundles)
    SmartStandard, // For Scalping (Priority Fees)
}

#[pyclass]
pub struct UnifiedTradeRouter {
    keypair: Keypair,
    jito_tip_account: Pubkey,
    // Removed #[pyo3(get)] as AtomicU64 doesn't implement IntoPy/Clone directly for get
    pub total_session_exposure: std::sync::atomic::AtomicU64, // In Milli-USD for atomic ops
}

#[pymethods]
impl UnifiedTradeRouter {
    #[new]
    pub fn new(private_key_base58: String) -> PyResult<Self> {
        // Init keypair once for zero-latency signing
        // Keypair::from_base58_string in this version returns Self directly (panics on invalid)
        let keypair = Keypair::from_base58_string(&private_key_base58);

        Ok(Self {
            keypair,
            jito_tip_account: Pubkey::from_str("96g9sAg9CeGguRiYp9YmNTSUky1F9p7hYy1B52B7WAbA")
                .unwrap(),
            total_session_exposure: std::sync::atomic::AtomicU64::new(0),
        })
    }

    /// Manual getter for atomic exposure
    #[getter]
    pub fn get_total_session_exposure(&self) -> u64 {
        self.total_session_exposure
            .load(std::sync::atomic::Ordering::Relaxed)
    }

    /// The High-Frequency Entry Point
    pub fn route(
        &self,
        path: ExecutionPath,
        instruction_data: Vec<u8>, // Serialized Instruction
        _cu_limit: u32,
        priority_fee_lamports: u64,
        recent_blockhash: String,
    ) -> PyResult<String> {
        let blockhash = solana_sdk::hash::Hash::from_str(&recent_blockhash).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid blockhash: {}", e))
        })?;

        // V34 Safety Check
        let exposure = self
            .total_session_exposure
            .load(std::sync::atomic::Ordering::Relaxed);
        if exposure > 10_000_000 {
            // $10k hard limit in Rust
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                "EMERGENCY_STOP: Session exposure limit reached in Rust",
            ));
        }

        match path {
            ExecutionPath::AtomicJito => self.execute_jito_bundle(
                instruction_data,
                _cu_limit,
                priority_fee_lamports,
                blockhash,
            ),
            ExecutionPath::SmartStandard => self.execute_standard_tx(
                instruction_data,
                _cu_limit,
                priority_fee_lamports,
                blockhash,
            ),
        }
    }

    /// Optimized path for pre-built transactions (e.g. from Jupiter)
    pub fn route_transaction(
        &self,
        path: ExecutionPath,
        tx_data: Vec<u8>, // Serialized VersionedTransaction
        tip_lamports: u64,
    ) -> PyResult<String> {
        let tx_base64 = base64::engine::general_purpose::STANDARD.encode(&tx_data);
        let rt = get_runtime();

        match path {
            ExecutionPath::AtomicJito => {
                match rt.block_on(async {
                    submit_jito_async(
                        "https://ny.mainnet.block-engine.jito.wtf",
                        &tx_base64,
                        tip_lamports,
                    )
                    .await
                }) {
                    Ok(sig) => Ok(sig),
                    Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
                }
            }
            ExecutionPath::SmartStandard => {
                match rt.block_on(async {
                    submit_rpc_async("https://api.mainnet-beta.solana.com", &tx_base64, true).await
                }) {
                    Ok(sig) => Ok(sig),
                    Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
                }
            }
        }
    }
}

impl UnifiedTradeRouter {
    fn execute_jito_bundle(
        &self,
        ix_data: Vec<u8>,
        _cu_limit: u32,
        tip_lamports: u64,
        blockhash: solana_sdk::hash::Hash,
    ) -> PyResult<String> {
        // 1. Deserialize Instruction
        let ix: Instruction = bincode::deserialize(&ix_data).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize instruction: {}",
                e
            ))
        })?;

        // 2. Add Jito Tip Instruction (System Transfer)
        let tip_ix = system_instruction::transfer(
            &self.keypair.pubkey(),
            &self.jito_tip_account,
            tip_lamports,
        );

        // 3. Create Transaction
        let tx = Transaction::new_signed_with_payer(
            &[ix, tip_ix],
            Some(&self.keypair.pubkey()),
            &[&self.keypair],
            blockhash,
        );

        // 4. Submit via Jito
        let rt = get_runtime();
        let tx_base64 =
            base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx).unwrap());

        match rt.block_on(async {
            submit_jito_async(
                "https://ny.mainnet.block-engine.jito.wtf",
                &tx_base64,
                tip_lamports,
            )
            .await
        }) {
            Ok(sig) => Ok(sig),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
        }
    }

    fn execute_standard_tx(
        &self,
        ix_data: Vec<u8>,
        _cu_limit: u32,
        _priority_fee: u64,
        blockhash: solana_sdk::hash::Hash,
    ) -> PyResult<String> {
        // 1. Deserialize
        let ix: Instruction = bincode::deserialize(&ix_data).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Failed to deserialize instruction: {}",
                e
            ))
        })?;

        // 2. Build & Sign
        let tx = Transaction::new_signed_with_payer(
            &[ix],
            Some(&self.keypair.pubkey()),
            &[&self.keypair],
            blockhash,
        );

        // 3. Submit via RPC
        let rt = get_runtime();
        let tx_base64 =
            base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx).unwrap());

        match rt.block_on(async {
            submit_rpc_async("https://api.mainnet-beta.solana.com", &tx_base64, true).await
        }) {
            Ok(sig) => Ok(sig),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// MULTI-HOP BUILDER - Atomic 4-5 Leg Transaction Construction
// V140: Narrow Path Infrastructure (Phase 15)
// ═══════════════════════════════════════════════════════════════════════════

use crate::multiverse::MultiverseCycle;
use solana_sdk::compute_budget::ComputeBudgetInstruction;

/// Multi-hop atomic execution builder
/// Transforms a MultiverseCycle into a single Jito bundle transaction
#[pyclass]
#[derive(Clone, Debug)]
pub struct MultiHopBundle {
    /// Base64-encoded transaction ready for Jito submission
    #[pyo3(get)]
    pub tx_base64: String,

    /// Estimated compute units required
    #[pyo3(get)]
    pub compute_units: u32,

    /// Total tip in lamports
    #[pyo3(get)]
    pub tip_lamports: u64,

    /// Number of swap legs
    #[pyo3(get)]
    pub leg_count: usize,

    /// Expected profit after all costs
    #[pyo3(get)]
    pub net_profit_pct: f64,

    /// Bundle creation timestamp
    #[pyo3(get)]
    pub created_at_ms: u64,
}

/// Swap leg data for multi-hop execution
#[pyclass]
#[derive(Clone, Debug)]
pub struct SwapLeg {
    /// Pool address for this leg
    #[pyo3(get)]
    pub pool_address: String,

    /// DEX name (Raydium, Orca, Meteora, etc.)
    #[pyo3(get)]
    pub dex: String,

    /// Input token mint
    #[pyo3(get)]
    pub input_mint: String,

    /// Output token mint
    #[pyo3(get)]
    pub output_mint: String,

    /// Serialized swap instruction (DEX-specific)
    #[pyo3(get)]
    pub instruction_data: Vec<u8>,
}

#[pymethods]
impl SwapLeg {
    #[new]
    pub fn new(
        pool_address: String,
        dex: String,
        input_mint: String,
        output_mint: String,
        instruction_data: Vec<u8>,
    ) -> Self {
        Self {
            pool_address,
            dex,
            input_mint,
            output_mint,
            instruction_data,
        }
    }
}

/// Multi-Hop Builder - constructs atomic Jito bundles from cycle data
#[pyclass]
pub struct MultiHopBuilder {
    keypair: Keypair,
    jito_tip_accounts: Vec<Pubkey>,

    /// Default compute units per swap leg
    cu_per_leg: u32,

    /// Base compute overhead for transaction
    cu_base_overhead: u32,

    /// Minimum tip in lamports
    min_tip_lamports: u64,

    /// Session statistics
    bundles_built: std::sync::atomic::AtomicU64,
    bundles_submitted: std::sync::atomic::AtomicU64,
}

#[pymethods]
impl MultiHopBuilder {
    #[new]
    pub fn new(
        private_key_base58: String,
        cu_per_leg: Option<u32>,
        min_tip_lamports: Option<u64>,
    ) -> PyResult<Self> {
        let keypair = Keypair::from_base58_string(&private_key_base58);

        // Jito tip accounts (rotate for load balancing)
        let tip_accounts = vec![
            Pubkey::from_str("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5").unwrap(),
            Pubkey::from_str("HFqU5x63VTqvQss8hp11i4bVhaapnNcBRaC3bvMsPF9C").unwrap(),
            Pubkey::from_str("Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY").unwrap(),
            Pubkey::from_str("ADaUMid9yfUytqMBgopwjb2DTLSLgqB7B9MjU4C4fqPr").unwrap(),
            Pubkey::from_str("DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh").unwrap(),
            Pubkey::from_str("ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt").unwrap(),
            Pubkey::from_str("DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL").unwrap(),
            Pubkey::from_str("3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT").unwrap(),
        ];

        Ok(Self {
            keypair,
            jito_tip_accounts: tip_accounts,
            cu_per_leg: cu_per_leg.unwrap_or(60_000),
            cu_base_overhead: 50_000,
            min_tip_lamports: min_tip_lamports.unwrap_or(10_000),
            bundles_built: std::sync::atomic::AtomicU64::new(0),
            bundles_submitted: std::sync::atomic::AtomicU64::new(0),
        })
    }

    /// Calculate required compute units for a multi-hop transaction
    pub fn estimate_compute_units(&self, leg_count: usize) -> u32 {
        // Base overhead + per-leg costs
        self.cu_base_overhead + (self.cu_per_leg * leg_count as u32)
    }

    /// Calculate tip based on leg count and congestion level
    pub fn calculate_tip(
        &self,
        leg_count: usize,
        congestion_multiplier: f64,
        expected_profit_lamports: u64,
    ) -> u64 {
        // Base tip scales with complexity
        let complexity_factor = 1.0 + (leg_count as f64 - 2.0) * 0.25;
        let congestion_factor = 1.0 + congestion_multiplier;

        let calculated_tip =
            (self.min_tip_lamports as f64 * complexity_factor * congestion_factor) as u64;

        // Cap tip at 50% of expected profit to ensure profitability
        let max_tip = expected_profit_lamports / 2;

        calculated_tip.min(max_tip).max(self.min_tip_lamports)
    }

    /// Build a multi-hop atomic transaction from pre-built swap instructions
    ///
    /// This is the core function that assembles:
    /// 1. Compute Budget instructions (limit + heap size)
    /// 2. All swap leg instructions in sequence
    /// 3. Jito tip instruction
    ///
    /// Returns a MultiHopBundle ready for submission
    pub fn build_bundle(
        &self,
        swap_legs: Vec<SwapLeg>,
        tip_lamports: u64,
        recent_blockhash: String,
        expected_profit_pct: f64,
    ) -> PyResult<MultiHopBundle> {
        use std::time::{SystemTime, UNIX_EPOCH};

        let leg_count = swap_legs.len();
        if leg_count < 2 || leg_count > 5 {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                "Invalid leg count: {}. Must be 2-5 legs.",
                leg_count
            )));
        }

        let blockhash = solana_sdk::hash::Hash::from_str(&recent_blockhash).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid blockhash: {}", e))
        })?;

        // 1. Calculate compute budget
        let compute_units = self.estimate_compute_units(leg_count);

        // 2. Build instruction list
        let mut instructions: Vec<Instruction> = Vec::with_capacity(leg_count + 3);

        // Add compute budget instruction
        instructions.push(ComputeBudgetInstruction::set_compute_unit_limit(
            compute_units,
        ));

        // Add heap frame increase for complex transactions
        if leg_count >= 4 {
            instructions.push(ComputeBudgetInstruction::request_heap_frame(256 * 1024));
        }

        // 3. Deserialize and add swap instructions
        for leg in &swap_legs {
            let ix: Instruction = bincode::deserialize(&leg.instruction_data).map_err(|e| {
                PyErr::new::<pyo3::exceptions::PyValueError, _>(format!(
                    "Failed to deserialize leg instruction for {}: {}",
                    leg.dex, e
                ))
            })?;
            instructions.push(ix);
        }

        // 4. Add Jito tip instruction
        let tip_account = self.get_tip_account();
        let tip_ix =
            system_instruction::transfer(&self.keypair.pubkey(), &tip_account, tip_lamports);
        instructions.push(tip_ix);

        // 5. Build and sign transaction
        let tx = Transaction::new_signed_with_payer(
            &instructions,
            Some(&self.keypair.pubkey()),
            &[&self.keypair],
            blockhash,
        );

        // 6. Serialize to base64
        let tx_bytes = bincode::serialize(&tx).map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!(
                "Failed to serialize transaction: {}",
                e
            ))
        })?;
        let tx_base64 = base64::engine::general_purpose::STANDARD.encode(&tx_bytes);

        // Calculate net profit (rough estimate)
        let fee_impact_pct = (leg_count as f64) * 0.003; // ~30bps per leg
        let net_profit_pct = expected_profit_pct - fee_impact_pct;

        // Update stats
        self.bundles_built
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        let created_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;

        Ok(MultiHopBundle {
            tx_base64,
            compute_units,
            tip_lamports,
            leg_count,
            net_profit_pct,
            created_at_ms: created_at,
        })
    }

    /// Submit a built bundle to Jito block engine
    pub fn submit_bundle(&self, bundle: &MultiHopBundle) -> PyResult<String> {
        let rt = get_runtime();

        match rt.block_on(async {
            submit_jito_async(
                "https://ny.mainnet.block-engine.jito.wtf",
                &bundle.tx_base64,
                bundle.tip_lamports,
            )
            .await
        }) {
            Ok(sig) => {
                self.bundles_submitted
                    .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                Ok(sig)
            }
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
        }
    }

    /// Build and submit in one call for maximum speed
    pub fn build_and_submit(
        &self,
        swap_legs: Vec<SwapLeg>,
        tip_lamports: u64,
        recent_blockhash: String,
        expected_profit_pct: f64,
    ) -> PyResult<String> {
        let bundle = self.build_bundle(
            swap_legs,
            tip_lamports,
            recent_blockhash,
            expected_profit_pct,
        )?;

        self.submit_bundle(&bundle)
    }

    /// Get statistics
    pub fn get_stats(&self) -> (u64, u64) {
        (
            self.bundles_built
                .load(std::sync::atomic::Ordering::Relaxed),
            self.bundles_submitted
                .load(std::sync::atomic::Ordering::Relaxed),
        )
    }

    /// Get public key as string
    pub fn pubkey(&self) -> String {
        self.keypair.pubkey().to_string()
    }
}

impl MultiHopBuilder {
    /// Rotate through Jito tip accounts for load balancing
    fn get_tip_account(&self) -> Pubkey {
        use std::time::{SystemTime, UNIX_EPOCH};
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as usize;

        // Simple rotation based on time
        self.jito_tip_accounts[now % self.jito_tip_accounts.len()]
    }
}

/// Registry function for PyO3
pub fn register_router_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<ExecutionPath>()?;
    m.add_class::<UnifiedTradeRouter>()?;
    m.add_class::<MultiHopBundle>()?;
    m.add_class::<SwapLeg>()?;
    m.add_class::<MultiHopBuilder>()?;
    Ok(())
}
