//! SignalScorer - Economic Validator for Trade Decisions
//! ======================================================
//! Phase 4: Institutional Realism
//!
//! This module moves the "Go/No-Go" decision logic from Python to Rust
//! to achieve sub-millisecond latency in the hot path.
//!
//! Net Profit Equation:
//! Net = (Size × Spread%) - (Gas + Jito + Slippage + DEX Fee)

use crate::metadata::SharedTokenMetadata;
use pyo3::prelude::*;

// ============================================================================
// CONFIGURATION
// ============================================================================

/// Static configuration for the scorer.
/// These values are typically set once at startup from Python settings.
#[pyclass]
#[derive(Clone, Debug)]
pub struct ScorerConfig {
    /// Minimum net profit required to approve a trade (USD)
    #[pyo3(get, set)]
    pub min_profit_usd: f64,

    /// Maximum allowed slippage in basis points (100 bps = 1%)
    #[pyo3(get, set)]
    pub max_slippage_bps: u16,

    /// Estimated gas fee per transaction (USD)
    #[pyo3(get, set)]
    pub gas_fee_usd: f64,

    /// Jito bundle tip per transaction (USD)
    #[pyo3(get, set)]
    pub jito_tip_usd: f64,

    /// DEX trading fee in basis points (30 = 0.3%)
    #[pyo3(get, set)]
    pub dex_fee_bps: u16,

    /// Default trade size for calculations (USD)
    #[pyo3(get, set)]
    pub default_trade_size_usd: f64,
}

#[pymethods]
impl ScorerConfig {
    #[new]
    #[pyo3(signature = (
        min_profit_usd = 0.10,
        max_slippage_bps = 500,
        gas_fee_usd = 0.02,
        jito_tip_usd = 0.001,
        dex_fee_bps = 30,
        default_trade_size_usd = 15.0
    ))]
    fn new(
        min_profit_usd: f64,
        max_slippage_bps: u16,
        gas_fee_usd: f64,
        jito_tip_usd: f64,
        dex_fee_bps: u16,
        default_trade_size_usd: f64,
    ) -> Self {
        ScorerConfig {
            min_profit_usd,
            max_slippage_bps,
            gas_fee_usd,
            jito_tip_usd,
            dex_fee_bps,
            default_trade_size_usd,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "ScorerConfig(min_profit={:.4}, max_slip={}bps, gas={:.4}, jito={:.4}, dex={}bps)",
            self.min_profit_usd,
            self.max_slippage_bps,
            self.gas_fee_usd,
            self.jito_tip_usd,
            self.dex_fee_bps
        )
    }
}

// ============================================================================
// VALIDATED SIGNAL OUTPUT
// ============================================================================

/// Output of a successful trade validation.
/// Only produced when a trade passes the economic viability check.
#[pyclass]
#[derive(Clone, Debug)]
pub struct ValidatedSignal {
    /// Net profit after all frictions (USD)
    #[pyo3(get)]
    pub net_profit: f64,

    /// Confidence score (0.0 to 1.0)
    #[pyo3(get)]
    pub confidence: f32,

    /// Token mint address
    #[pyo3(get)]
    pub token: String,

    /// Recommended action: "BUY" | "SELL"
    #[pyo3(get)]
    pub action: String,

    /// Gross spread before frictions (USD)
    #[pyo3(get)]
    pub gross_spread: f64,

    /// Total frictions applied (USD)
    #[pyo3(get)]
    pub total_frictions: f64,
}

#[pymethods]
impl ValidatedSignal {
    fn __repr__(&self) -> String {
        format!(
            "ValidatedSignal({} {} | net={:.4} USD | conf={:.2})",
            self.action, self.token, self.net_profit, self.confidence
        )
    }
}

// ============================================================================
// SIGNAL SCORER ENGINE
// ============================================================================

/// High-performance trade validator.
/// Evaluates whether a trade is economically viable after all frictions.
#[pyclass]
pub struct SignalScorer {
    config: ScorerConfig,
}

#[pymethods]
impl SignalScorer {
    /// Create a new SignalScorer with the given configuration.
    #[new]
    fn new(config: ScorerConfig) -> Self {
        SignalScorer { config }
    }

    /// Score a single trade opportunity.
    /// Returns `Some(ValidatedSignal)` if profitable, `None` if not worth executing.
    ///
    /// # Arguments
    /// * `metadata` - Token metadata including price, spread, liquidity
    /// * `trade_size_usd` - Optional override for trade size (defaults to config)
    #[pyo3(signature = (metadata, trade_size_usd = None))]
    fn score_trade(
        &self,
        metadata: &SharedTokenMetadata,
        trade_size_usd: Option<f64>,
    ) -> Option<ValidatedSignal> {
        let size = trade_size_usd.unwrap_or(self.config.default_trade_size_usd);

        // 1. Safety Pre-flight Checks
        if !self.passes_safety_checks(metadata) {
            return None;
        }

        // 2. Calculate Gross Spread (potential profit before costs)
        let spread_pct = metadata.spread_bps as f64 / 10_000.0;
        let gross_spread = size * spread_pct;

        // 3. Calculate Total Frictions
        let frictions = self.calculate_frictions(metadata, size);

        // 4. Net Profit
        let net_profit = gross_spread - frictions;

        // 5. Decision Gate
        if net_profit < self.config.min_profit_usd {
            return None;
        }

        // 6. Compute Confidence Score
        let confidence = self.compute_confidence(metadata, net_profit);

        // 7. Determine Action
        let action = if metadata.velocity_1m > 0.0 {
            "BUY"
        } else {
            "SELL"
        };

        Some(ValidatedSignal {
            net_profit,
            confidence,
            token: metadata.mint.clone(),
            action: action.to_string(),
            gross_spread,
            total_frictions: frictions,
        })
    }

    /// Batch score multiple opportunities.
    /// Returns only the validated signals (filters out unprofitable ones).
    fn score_batch(
        &self,
        metadata_list: Vec<SharedTokenMetadata>,
        trade_size_usd: Option<f64>,
    ) -> Vec<ValidatedSignal> {
        metadata_list
            .iter()
            .filter_map(|m| self.score_trade(m, trade_size_usd))
            .collect()
    }

    /// Batch score with parallel processing (for large batches).
    /// Uses Rayon for CPU-parallel filtering.
    fn score_batch_parallel(
        &self,
        metadata_list: Vec<SharedTokenMetadata>,
        trade_size_usd: Option<f64>,
    ) -> Vec<ValidatedSignal> {
        use rayon::prelude::*;

        let size = trade_size_usd.unwrap_or(self.config.default_trade_size_usd);

        metadata_list
            .par_iter()
            .filter_map(|m| {
                // Inline the scoring logic for parallel context
                if !self.passes_safety_checks(m) {
                    return None;
                }

                let spread_pct = m.spread_bps as f64 / 10_000.0;
                let gross_spread = size * spread_pct;
                let frictions = self.calculate_frictions(m, size);
                let net_profit = gross_spread - frictions;

                if net_profit < self.config.min_profit_usd {
                    return None;
                }

                let confidence = self.compute_confidence(m, net_profit);
                let action = if m.velocity_1m > 0.0 { "BUY" } else { "SELL" };

                Some(ValidatedSignal {
                    net_profit,
                    confidence,
                    token: m.mint.clone(),
                    action: action.to_string(),
                    gross_spread,
                    total_frictions: frictions,
                })
            })
            .collect()
    }

    /// Get the current configuration.
    fn get_config(&self) -> ScorerConfig {
        self.config.clone()
    }

    /// Update configuration at runtime.
    fn update_config(&mut self, config: ScorerConfig) {
        self.config = config;
    }
}

// ============================================================================
// INTERNAL METHODS
// ============================================================================

impl SignalScorer {
    /// Pre-flight safety checks before calculating profitability.
    fn passes_safety_checks(&self, metadata: &SharedTokenMetadata) -> bool {
        // 1. Rug Safety
        if !metadata.is_rug_safe {
            return false;
        }

        // 2. Minimum Liquidity ($500 floor)
        if metadata.liquidity_usd < 500.0 {
            return false;
        }

        // 3. Token-2022 Transfer Tax Check
        if metadata.transfer_fee_bps > self.config.max_slippage_bps {
            return false;
        }

        // 4. Mint Authority Check (avoid ruggable tokens)
        if metadata.has_mint_auth {
            return false;
        }

        // 5. Spread must be positive
        if metadata.spread_bps == 0 {
            return false;
        }

        true
    }

    /// Calculate total frictions for a trade.
    /// Frictions = Gas + Jito Tip + DEX Fee + Slippage Impact
    fn calculate_frictions(&self, metadata: &SharedTokenMetadata, trade_size: f64) -> f64 {
        // 1. Fixed Costs
        let gas = self.config.gas_fee_usd;
        let jito = self.config.jito_tip_usd;

        // 2. DEX Fee (proportional to trade size)
        let dex_fee = trade_size * (self.config.dex_fee_bps as f64 / 10_000.0);

        // 3. Slippage Impact (dynamic based on liquidity)
        let slippage = self.calculate_slippage_impact(metadata, trade_size);

        // 4. Token-2022 Transfer Tax (if applicable)
        let transfer_tax = if metadata.transfer_fee_bps > 0 {
            trade_size * (metadata.transfer_fee_bps as f64 / 10_000.0)
        } else {
            0.0
        };

        gas + jito + dex_fee + slippage + transfer_tax
    }

    /// Calculate slippage impact based on trade size vs liquidity.
    /// Uses the formula: Slippage = Base + (Size/Liquidity) × Impact Multiplier
    fn calculate_slippage_impact(&self, metadata: &SharedTokenMetadata, trade_size: f64) -> f64 {
        // Base slippage (0.3%)
        let base_slippage_pct = 0.003;

        // Impact multiplier based on size vs liquidity
        let impact_multiplier = 0.05; // 5% impact per unit of size/liquidity

        // Protect against zero liquidity
        let liquidity = if metadata.liquidity_usd > 0.0 {
            metadata.liquidity_usd
        } else {
            1.0 // Prevent division by zero
        };

        // Size impact: larger trades relative to liquidity = more slippage
        let size_ratio = trade_size / liquidity;
        let dynamic_slippage_pct = size_ratio * impact_multiplier;

        // Volatility penalty (higher velocity = more slippage)
        let volatility_penalty = metadata.velocity_1m.abs() * 0.01; // 1% per 1% velocity

        // Total slippage percentage
        let total_slippage_pct = base_slippage_pct + dynamic_slippage_pct + volatility_penalty;

        // Cap at max_slippage_bps from config
        let max_slippage_pct = self.config.max_slippage_bps as f64 / 10_000.0;
        let capped_slippage_pct = total_slippage_pct.min(max_slippage_pct);

        // Convert to USD
        trade_size * capped_slippage_pct
    }

    /// Compute confidence score based on metadata quality.
    fn compute_confidence(&self, metadata: &SharedTokenMetadata, net_profit: f64) -> f32 {
        let mut confidence: f32 = 0.0;

        // 1. Profit Margin Bonus (higher profit = higher confidence)
        // Scale: $0.10 profit = 0.1, $1.00 profit = 0.5 (capped)
        let profit_bonus = (net_profit / 2.0).min(0.5) as f32;
        confidence += profit_bonus;

        // 2. Liquidity Bonus (more liquidity = safer)
        if metadata.liquidity_usd > 100_000.0 {
            confidence += 0.2;
        } else if metadata.liquidity_usd > 10_000.0 {
            confidence += 0.1;
        }

        // 3. Order Flow Imbalance Bonus
        if metadata.order_imbalance > 1.2 {
            confidence += 0.15;
        }

        // 4. Momentum Bonus (velocity aligned with action)
        if metadata.velocity_1m.abs() > 0.02 {
            confidence += 0.1;
        }

        // 5. LP Lock Bonus (safety)
        if metadata.lp_locked_pct > 0.8 {
            confidence += 0.05;
        }

        // 6. Whale-Pulse Bonus (Phase 5A)
        // If a whale is buying, boost confidence by up to 0.2
        confidence += metadata.whale_confidence_bonus;

        // Cap at 1.0
        confidence.min(1.0)
    }
}

// ============================================================================
// MODULE REGISTRATION
// ============================================================================

pub fn register_scorer_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<ScorerConfig>()?;
    m.add_class::<ValidatedSignal>()?;
    m.add_class::<SignalScorer>()?;
    Ok(())
}

// ============================================================================
// UNIT TESTS
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_config() -> ScorerConfig {
        ScorerConfig {
            min_profit_usd: 0.10,
            max_slippage_bps: 500,
            gas_fee_usd: 0.02,
            jito_tip_usd: 0.001,
            dex_fee_bps: 30,
            default_trade_size_usd: 15.0,
        }
    }

    fn make_test_metadata() -> SharedTokenMetadata {
        SharedTokenMetadata {
            mint: "TestToken123".to_string(),
            symbol: "TEST".to_string(),
            program_id: "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA".to_string(),
            decimals: 6,
            is_rug_safe: true,
            lp_locked_pct: 0.9,
            has_mint_auth: false,
            freeze_authority: None,
            is_mutable: false,
            top_10_holders: 0.25,
            price_usd: 1.0,
            liquidity_usd: 50_000.0,
            volume_5m: 10_000.0,
            velocity_1m: 0.03, // 3% per minute
            order_imbalance: 1.3,
            buy_sell_ratio: 1.2,
            spread_bps: 250, // 2.5% spread (profitable after frictions)
            is_pump_fun: false,
            graduated: true,
            last_updated_slot: 100,
            transfer_fee_bps: 0,
            whale_confidence_bonus: 0.0, // V3: Phase 5A
        }
    }

    #[test]
    fn test_profitable_trade() {
        let config = make_test_config();
        let scorer = SignalScorer::new(config);
        let metadata = make_test_metadata();

        let result = scorer.score_trade(&metadata, Some(15.0));

        assert!(
            result.is_some(),
            "Expected profitable trade to return ValidatedSignal"
        );
        let signal = result.unwrap();
        assert!(signal.net_profit > 0.0, "Net profit should be positive");
        assert_eq!(signal.action, "BUY"); // velocity_1m > 0
        assert!(signal.confidence > 0.0 && signal.confidence <= 1.0);
    }

    #[test]
    fn test_unprofitable_trade() {
        let config = make_test_config();
        let scorer = SignalScorer::new(config);
        let mut metadata = make_test_metadata();

        // Set spread too low to be profitable
        metadata.spread_bps = 5; // 0.05% spread

        let result = scorer.score_trade(&metadata, Some(15.0));

        assert!(
            result.is_none(),
            "Expected unprofitable trade to return None"
        );
    }

    #[test]
    fn test_safety_check_fails() {
        let config = make_test_config();
        let scorer = SignalScorer::new(config);
        let mut metadata = make_test_metadata();

        // Make token unsafe (mint authority active)
        metadata.has_mint_auth = true;

        let result = scorer.score_trade(&metadata, Some(15.0));

        assert!(result.is_none(), "Expected unsafe token to be rejected");
    }

    #[test]
    fn test_friction_calculation() {
        let config = make_test_config();
        let scorer = SignalScorer::new(config);
        let metadata = make_test_metadata();

        let frictions = scorer.calculate_frictions(&metadata, 15.0);

        // Expected: gas(0.02) + jito(0.001) + dex(15*0.003=0.045) + slippage(~0.045) ≈ 0.11+
        assert!(frictions > 0.1, "Frictions should be at least $0.10");
        assert!(
            frictions < 1.0,
            "Frictions should not exceed $1.00 for $15 trade"
        );
    }

    #[test]
    fn test_batch_scoring() {
        let config = make_test_config();
        let scorer = SignalScorer::new(config);

        let good_token = make_test_metadata();
        let mut bad_token = make_test_metadata();
        bad_token.has_mint_auth = true; // Unsafe

        let batch = vec![good_token, bad_token];
        let results = scorer.score_batch(batch, Some(15.0));

        assert_eq!(results.len(), 1, "Only profitable+safe trades should pass");
    }
}
