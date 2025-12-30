use pyo3.prelude::*;
use serde::{Deserialize, Serialize};

#[pyclass]
#[derive(Clone, Default, Debug, Serialize, Deserialize)]
pub struct SharedTokenMetadata {
    // Identity
    #[pyo3(get, set)]
    pub mint: String,
    #[pyo3(get, set)]
    pub program_id: u8, // 0: SPL, 1: Token2022
    #[pyo3(get, set)]
    pub decimals: u8,
    #[pyo3(get, set)]
    pub symbol: String,

    // Risk (Slow)
    #[pyo3(get, set)]
    pub mint_authority: Option<String>,
    #[pyo3(get, set)]
    pub freeze_authority: Option<String>,
    #[pyo3(get, set)]
    pub is_mutable: bool,
    #[pyo3(get, set)]
    pub lp_locked_pct: f32,
    #[pyo3(get, set)]
    pub top_10_holders: f32,
    #[pyo3(get, set)]
    pub is_rug_safe: bool,

    // Market (Fast)
    #[pyo3(get, set)]
    pub price_usd: f64,
    #[pyo3(get, set)]
    pub pools: Vec<String>,
    #[pyo3(get, set)]
    pub liquidity_usd: f64,
    #[pyo3(get, set)]
    pub volume_5m: f64,
    #[pyo3(get, set)]
    pub buy_sell_ratio: f32,
    
    // Scalper Specific (Microstructure)
    #[pyo3(get, set)]
    pub velocity_1m: f64,
    #[pyo3(get, set)]
    pub rsi_1m: f32,
    #[pyo3(get, set)]
    pub ema_cross: bool,
    #[pyo3(get, set)]
    pub spread_bps: u32,
    #[pyo3(get, set)]
    pub order_imbalance: f32,
    
    // Safety
    #[pyo3(get, set)]
    pub is_pump_fun: bool,
    #[pyo3(get, set)]
    pub graduated: bool,

    #[pyo3(get, set)]
    pub last_updated_slot: u64,
}

#[pymethods]
impl SharedTokenMetadata {
    #[new]
    fn new(mint: String) -> Self {
        SharedTokenMetadata {
            mint,
            symbol: "UNKNOWN".to_string(),
            ..Default::default()
        }
    }

    fn is_stale(&self, current_slot: u64) -> bool {
        if current_slot < self.last_updated_slot {
            return false; 
        }
        current_slot - self.last_updated_slot > 5
    }
    
    fn is_valid_scalp_candidate(&self) -> bool {
        self.is_rug_safe && self.liquidity_usd > 1000.0 && self.spread_bps < 100
    }
}

pub fn register_metadata_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<SharedTokenMetadata>()?;
    Ok(())
}
