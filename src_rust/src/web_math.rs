use wasm_bindgen::prelude::*;

/// V21.1: Web Math Core
/// ====================
/// High-performance math logic extracted for WASM and PyO3.
/// Precision-matched with arb_logic_standalone.py.

#[wasm_bindgen]
pub fn calculate_net_profit(
    spread_raw: f64,
    trade_size: f64,
    jito_tip: f64,
    route_friction: f64,
) -> f64 {
    let gross = trade_size * (spread_raw / 100.0);
    let net = gross - jito_tip - route_friction;
    net
}

#[wasm_bindgen]
pub fn calculate_optimal_size(
    spread_pct: f64,
    impact_factor: f64,
    min_size: f64,
    max_size: f64,
) -> f64 {
    if impact_factor <= 0.0 {
        return max_size;
    }

    // x_opt = Spread / (2 * Impact)
    let s = spread_pct / 100.0;
    let optimal_size = s / (2.0 * impact_factor);

    optimal_size.clamp(min_size, max_size)
}

#[wasm_bindgen]
pub fn estimate_compute_units(
    ops: Vec<String>,
    num_accounts: u32,
    num_signers: u32,
    safety_margin_percent: f64,
) -> u32 {
    let mut estimated_cu = 0.0;

    // 1. Signature Cost
    estimated_cu += (num_signers as f64) * 1500.0;

    // 2. Serialization Overhead
    estimated_cu += (num_accounts as f64) * 850.0;

    // 3. Instruction Simulation
    for op in ops {
        let cost = match op.as_str() {
            "transfer_sol" => 500.0,
            "transfer_spl" => 4500.0,
            "create_ata" => 25000.0,
            "close_account" => 3000.0,
            "memo" => 100.0,
            "raydium_swap_v4" => 80000.0,
            "raydium_swap_cpcc" => 120000.0,
            "orca_whirlpool_swap" => 145000.0,
            "meteora_dlmm_swap" => 70000.0,
            "jupiter_aggregator" => 180000.0,
            "phoenix_swap" => 25000.0,
            _ => 10000.0,
        };
        estimated_cu += cost;
    }

    // 4. Safety Margin
    estimated_cu *= 1.0 + (safety_margin_percent / 100.0);

    if estimated_cu < 5000.0 {
        estimated_cu = 5000.0;
    }

    estimated_cu.ceil() as u32
}
