use pyo3::prelude::*;
use solana_sdk::pubkey::Pubkey;
use solana_sdk::signature::{Keypair, Signer};
use solana_sdk::transaction::Transaction;
use solana_sdk::instruction::{Instruction, AccountMeta};
use solana_sdk::system_instruction;
use std::str::FromStr;
use solana_sdk::transaction::VersionedTransaction;
use solana_sdk::hash::Hash;

#[pyclass]
#[derive(Clone, Debug)]
pub enum ExecutionPath {
    AtomicJito,   // For Arbitrage (Bundles)
    SmartStandard, // For Scalping (Priority Fees)
}

#[pyclass]
pub struct UnifiedTradeRouter {
    keypair: Keypair,
    jito_tip_account: Pubkey,
    #[pyo3(get)]
    pub total_session_exposure: std::sync::atomic::AtomicU64, // In Milli-USD for atomic ops
}

#[pymethods]
impl UnifiedTradeRouter {
    #[new]
    pub fn new(private_key_base58: String) -> PyResult<Self> {
        // Init keypair once for zero-latency signing
        let keypair = Keypair::from_base58_string(&private_key_base58)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid keypair: {}", e)))?;
            
        Ok(Self { 
            keypair,
            jito_tip_account: Pubkey::from_str("96g9sAg9CeGguRiYp9YmNTSUky1F9p7hYy1B52B7WAbA").unwrap(),
            total_session_exposure: std::sync::atomic::AtomicU64::new(0),
        })
    }

    /// The High-Frequency Entry Point
    pub fn route(
        &self, 
        path: ExecutionPath, 
        instruction_data: Vec<u8>, // Serialized Instruction
        cu_limit: u32,
        priority_fee_lamports: u64,
        recent_blockhash: String
    ) -> PyResult<String> {
        let blockhash = solana_sdk::hash::Hash::from_str(&recent_blockhash)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid blockhash: {}", e)))?;

        // V34 Safety Check
        let exposure = self.total_session_exposure.load(std::sync::atomic::Ordering::Relaxed);
        if exposure > 10_000_000 { // $10k hard limit in Rust
            return Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>("EMERGENCY_STOP: Session exposure limit reached in Rust"));
        }

        match path {
            ExecutionPath::AtomicJito => {
                self.execute_jito_bundle(instruction_data, cu_limit, priority_fee_lamports, blockhash)
            },
            ExecutionPath::SmartStandard => {
                self.execute_standard_tx(instruction_data, cu_limit, priority_fee_lamports, blockhash)
            },
        }
    }
}

impl UnifiedTradeRouter {
    fn execute_jito_bundle(
        &self, 
        ix_data: Vec<u8>, 
        cu_limit: u32, 
        tip_lamports: u64,
        blockhash: solana_sdk::hash::Hash
    ) -> PyResult<String> {
        // 1. Deserialize Instruction
        let ix: Instruction = bincode::deserialize(&ix_data)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Failed to deserialize instruction: {}", e)))?;
        
        // 2. Add Jito Tip Instruction (System Transfer)
        let tip_ix = system_instruction::transfer(
            &self.keypair.pubkey(),
            &self.jito_tip_account,
            tip_lamports
        );

        // For simplicity in this skeleton, we'll assume the instruction vector passed from Python 
        // already includes needed ComputeBudget instructions if required, or we add them here.
        
        // 3. Create Transaction
        let tx = Transaction::new_signed_with_payer(
            &[ix, tip_ix],
            Some(&self.keypair.pubkey()),
            &[&self.keypair],
            blockhash,
        );

        // 4. Submit via Jito
        let rt = get_runtime();
        let tx_base64 = base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx).unwrap());
        
        match rt.block_on(async {
            submit_jito_async("https://ny.mainnet.block-engine.jito.wtf", &tx_base64, tip_lamports).await
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
        blockhash: solana_sdk::hash::Hash
    ) -> PyResult<String> {
        // 1. Deserialize
        let ix: Instruction = bincode::deserialize(&ix_data)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Failed to deserialize instruction: {}", e)))?;

        // 2. Build & Sign
        let tx = Transaction::new_signed_with_payer(
            &[ix],
            Some(&self.keypair.pubkey()),
            &[&self.keypair],
            blockhash,
        );

        // 3. Submit via RPC
        let rt = get_runtime();
        let tx_base64 = base64::engine::general_purpose::STANDARD.encode(bincode::serialize(&tx).unwrap());
        
        match rt.block_on(async {
            submit_rpc_async("https://api.mainnet-beta.solana.com", &tx_base64, true).await
        }) {
            Ok(sig) => Ok(sig),
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
        }
    }
}
