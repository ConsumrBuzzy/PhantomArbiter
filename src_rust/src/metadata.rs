use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[pyclass]
#[derive(Clone, Default, Debug, Serialize, Deserialize)]
pub struct SharedTokenMetadata {
    // Identity
    #[pyo3(get, set)]
    pub mint: String,
    #[pyo3(get, set)]
    pub program_id: String, // SPL vs Token-2022
    #[pyo3(get, set)]
    pub decimals: u8,
    #[pyo3(get, set)]
    pub symbol: String,

    // Risk (Slow)
    #[pyo3(get, set)]
    pub is_rug_safe: bool,
    #[pyo3(get, set)]
    pub lp_locked_pct: f32,
    #[pyo3(get, set)]
    pub has_mint_auth: bool,
    #[pyo3(get, set)]
    pub freeze_authority: Option<String>,
    #[pyo3(get, set)]
    pub is_mutable: bool,
    #[pyo3(get, set)]
    pub top_10_holders: f32,

    // Market (Fast) - Scalper Metadata
    #[pyo3(get, set)]
    pub price_usd: f64,
    #[pyo3(get, set)]
    pub liquidity_usd: f64,
    #[pyo3(get, set)]
    pub volume_5m: f64,
    #[pyo3(get, set)]
    pub velocity_1m: f64, // Price change % / min
    #[pyo3(get, set)]
    pub order_imbalance: f32, // Buy vol vs Sell vol
    #[pyo3(get, set)]
    pub buy_sell_ratio: f32,
    #[pyo3(get, set)]
    pub spread_bps: u32,

    // Launchpad Info
    #[pyo3(get, set)]
    pub is_pump_fun: bool,
    #[pyo3(get, set)]
    pub graduated: bool, // True if migrated to Raydium

    #[pyo3(get, set)]
    pub last_updated_slot: u64,

    // V2: Token-2022
    #[pyo3(get, set)]
    pub transfer_fee_bps: u16,

    // V3: Whale-Pulse Confidence Bonus (Phase 5A)
    #[pyo3(get, set)]
    pub whale_confidence_bonus: f32, // 0.0 to 0.5 based on whale activity

    // Lifecycle (Phase 6 Universal Discovery)
    #[pyo3(get, set)]
    pub market_stage: String, // "PUMP", "STD", "CLMM"
    #[pyo3(get, set)]
    pub bonding_curve_progress: f32, // 0-100%
}

#[pymethods]
impl SharedTokenMetadata {
    #[new]
    fn new(mint: String) -> Self {
        SharedTokenMetadata {
            mint,
            symbol: "UNKNOWN".to_string(),
            program_id: "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA".to_string(), // Default SPL
            market_stage: "UNKNOWN".to_string(),
            bonding_curve_progress: 0.0,
            ..Default::default()
        }
    }

    pub fn is_stale(&self, current_slot: u64) -> bool {
        current_slot.saturating_sub(self.last_updated_slot) > 10 // Stale if > 4-5 seconds
    }

    fn is_valid_scalp_candidate(&self) -> bool {
        self.is_rug_safe && self.liquidity_usd > 500.0 && !self.has_mint_auth
    }

    // Token-2022 Logic placeholder
    fn has_transfer_tax(&self) -> bool {
        self.transfer_fee_bps > 0
    }
}

pub fn register_metadata_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<SharedTokenMetadata>()?;
    Ok(())
}
