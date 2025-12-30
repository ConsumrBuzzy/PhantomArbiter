use pyo3::prelude::*;
use crate::metadata::SharedTokenMetadata;

#[pyclass]
#[derive(Clone, Debug)]
pub struct ScalpSignal {
    #[pyo3(get)]
    pub confidence: f32,
    #[pyo3(get)]
    pub direction: String, // "BUY" or "SELL"
    #[pyo3(get)]
    pub expected_exit: f64,
    #[pyo3(get)]
    pub token: String,
}

#[pyclass]
pub struct SignalScanner {
    
}

#[pymethods]
impl SignalScanner {
    #[new]
    fn new() -> Self {
        SignalScanner {}
    }

    /// Batch scans metadata for scalp opportunities.
    /// Returns opportunities where velocity > 2%/min and RugSafe is True.
    #[pyo3(signature = (registry, current_slot))]
    fn scan_scalp_opportunities(&self, registry: Vec<SharedTokenMetadata>, current_slot: u64) -> Vec<ScalpSignal> {
        // High-Performance Filtering (Zero-Cost Abstractions)
        registry.into_iter()
            .filter(|m| {
                // 1. Safety Filter
                m.is_rug_safe && 
                !m.is_stale(current_slot) && 
                m.transfer_fee_bps < 500 // Avoid Tax Traps (>5%)
            })
            .filter(|m| {
                // 2. Momentum Filter
                m.velocity_1m.abs() > 0.02 // 2% move in 1m
            })
            .map(|m| {
                // 3. Signal Generation
                let direction = if m.velocity_1m > 0.0 { "BUY" } else { "SELL" };
                
                // Confidence weighted by Flow
                let mut confidence = (m.velocity_1m.abs() * 10.0) as f32; // 0.02 -> 0.2 base
                if m.order_imbalance > 1.2 { confidence += 0.2; }
                if m.liquidity_usd > 10_000.0 { confidence += 0.1; }
                
                // Cap confidence
                if confidence > 1.0 { confidence = 1.0; }

                ScalpSignal {
                    token: m.mint.clone(),
                    confidence,
                    direction: direction.to_string(),
                    expected_exit: if direction == "BUY" { 
                        m.price_usd * (1.0 + m.velocity_1m.abs()) 
                    } else { 
                        m.price_usd * (1.0 - m.velocity_1m.abs()) 
                    }
                }
            })
            .collect()
    }
}

pub fn register_scalper_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<ScalpSignal>()?;
    m.add_class::<SignalScanner>()?;
    Ok(())
}
