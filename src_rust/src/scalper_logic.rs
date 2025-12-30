use pyo3.prelude::*;
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
    fn scan_scalp_opportunities(&self, registry: Vec<SharedTokenMetadata>) -> Vec<ScalpSignal> {
        let mut signals = Vec::new();
        
        for token in registry {
            // 1. Hard Filter: Must be Rug Safe & Liquid
            if !token.is_rug_safe || token.liquidity_usd < 500.0 {
                continue;
            }
            
            // 2. Velocity Check (Momentum)
            if token.velocity_1m > 0.05 { // > 5% per minute
                // BUY SIGNAL
                let mut confidence = 0.5;
                
                if token.order_imbalance > 1.5 { confidence += 0.2; } 
                if token.spread_bps < 50 { confidence += 0.1; }       
                if token.ema_cross { confidence += 0.1; }
                
                if confidence > 0.7 {
                    signals.push(ScalpSignal {
                        token: token.mint,
                        confidence,
                        direction: "BUY".to_string(),
                        expected_exit: token.price_usd * 1.015
                    });
                }
            }
            
            // 3. Reversion Check (RSI)
             if token.rsi_1m < 20.0 && token.is_rug_safe {
                  signals.push(ScalpSignal {
                        token: token.mint,
                        confidence: 0.6, // Risky
                        direction: "BUY".to_string(),
                        expected_exit: token.price_usd * 1.03
                    });
             }
        }
        
        signals
    }
}

pub fn register_scalper_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<ScalpSignal>()?;
    m.add_class::<SignalScanner>()?;
    Ok(())
}
