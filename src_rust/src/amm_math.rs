// ------------------------------------------------------------------------
// AMM MATH ENGINE (THE ORACLE)
// Phase 1: Constant Product AMM (Raydium V4)
// Phase 2: CLMM (Orca Whirlpool / Raydium CLMM)
// Phase 3: DLMM (Meteora)
// ------------------------------------------------------------------------

use pyo3::prelude::*;

// ============================================================================
// PHASE 1: CONSTANT PRODUCT AMM (x * y = k)
// ============================================================================

/// Compute output amount for a constant product AMM swap.
/// 
/// Formula: amount_out = (reserve_out * amount_in * (10000 - fee_bps)) / 
///                       (reserve_in * 10000 + amount_in * (10000 - fee_bps))
/// 
/// # Arguments
/// * `amount_in` - Input token amount (in smallest unit, e.g., lamports)
/// * `reserve_in` - Pool reserve of input token
/// * `reserve_out` - Pool reserve of output token  
/// * `fee_bps` - Fee in basis points (e.g., 25 = 0.25% for Raydium V4)
/// 
/// # Returns
/// Output amount after swap (in smallest unit)
#[pyfunction]
#[pyo3(signature = (amount_in, reserve_in, reserve_out, fee_bps=25))]
pub fn compute_amm_out(
    amount_in: u64,
    reserve_in: u64,
    reserve_out: u64,
    fee_bps: u64,
) -> PyResult<u64> {
    // Guard against zero reserves or zero input
    if reserve_in == 0 || reserve_out == 0 || amount_in == 0 {
        return Ok(0);
    }
    
    // Use u128 for intermediate calculations to prevent overflow
    let amount_in_128 = amount_in as u128;
    let reserve_in_128 = reserve_in as u128;
    let reserve_out_128 = reserve_out as u128;
    let fee_factor = 10000u128 - fee_bps as u128;
    
    // Numerator: reserve_out * amount_in * fee_factor
    let numerator = reserve_out_128
        .checked_mul(amount_in_128)
        .and_then(|v| v.checked_mul(fee_factor))
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyOverflowError, _>("Overflow in numerator"))?;
    
    // Denominator: reserve_in * 10000 + amount_in * fee_factor
    let denominator = reserve_in_128
        .checked_mul(10000)
        .and_then(|v| v.checked_add(amount_in_128.checked_mul(fee_factor)?))
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyOverflowError, _>("Overflow in denominator"))?;
    
    if denominator == 0 {
        return Ok(0);
    }
    
    let amount_out = numerator / denominator;
    
    // Clamp to u64 max (should never be an issue in practice)
    Ok(amount_out.min(u64::MAX as u128) as u64)
}

/// Compute required input amount for a desired output in a constant product AMM.
/// 
/// Inverse of compute_amm_out.
/// 
/// # Arguments
/// * `amount_out` - Desired output token amount
/// * `reserve_in` - Pool reserve of input token
/// * `reserve_out` - Pool reserve of output token
/// * `fee_bps` - Fee in basis points
/// 
/// # Returns
/// Required input amount (in smallest unit)
#[pyfunction]
#[pyo3(signature = (amount_out, reserve_in, reserve_out, fee_bps=25))]
pub fn compute_amm_in(
    amount_out: u64,
    reserve_in: u64,
    reserve_out: u64,
    fee_bps: u64,
) -> PyResult<u64> {
    // Guard against invalid inputs
    if reserve_in == 0 || reserve_out == 0 || amount_out == 0 {
        return Ok(0);
    }
    
    // Cannot withdraw more than reserve
    if amount_out >= reserve_out {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "amount_out exceeds reserve_out"
        ));
    }
    
    let amount_out_128 = amount_out as u128;
    let reserve_in_128 = reserve_in as u128;
    let reserve_out_128 = reserve_out as u128;
    let fee_factor = 10000u128 - fee_bps as u128;
    
    // Formula: amount_in = (reserve_in * amount_out * 10000) / 
    //                      ((reserve_out - amount_out) * fee_factor) + 1
    let numerator = reserve_in_128
        .checked_mul(amount_out_128)
        .and_then(|v| v.checked_mul(10000))
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyOverflowError, _>("Overflow in numerator"))?;
    
    let denominator = (reserve_out_128 - amount_out_128)
        .checked_mul(fee_factor)
        .ok_or_else(|| PyErr::new::<pyo3::exceptions::PyOverflowError, _>("Overflow in denominator"))?;
    
    if denominator == 0 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "Zero denominator in compute_amm_in"
        ));
    }
    
    // Round up to ensure we get at least the desired output
    let amount_in = (numerator + denominator - 1) / denominator;
    
    Ok(amount_in.min(u64::MAX as u128) as u64)
}

/// Batch compute AMM outputs for multiple swaps.
/// 
/// Useful for scanning multiple opportunities in a single FFI call.
/// 
/// # Arguments
/// * `amounts_in` - Vector of input amounts
/// * `reserve_in` - Pool reserve of input token (same for all)
/// * `reserve_out` - Pool reserve of output token (same for all)
/// * `fee_bps` - Fee in basis points
/// 
/// # Returns
/// Vector of output amounts
#[pyfunction]
#[pyo3(signature = (amounts_in, reserve_in, reserve_out, fee_bps=25))]
pub fn compute_amm_out_batch(
    amounts_in: Vec<u64>,
    reserve_in: u64,
    reserve_out: u64,
    fee_bps: u64,
) -> PyResult<Vec<u64>> {
    let mut results = Vec::with_capacity(amounts_in.len());
    
    for amount_in in amounts_in {
        let out = compute_amm_out(amount_in, reserve_in, reserve_out, fee_bps)?;
        results.push(out);
    }
    
    Ok(results)
}

/// Calculate price impact for a swap.
/// 
/// # Returns
/// Price impact as a percentage (e.g., 0.5 = 0.5% slippage)
#[pyfunction]
#[pyo3(signature = (amount_in, reserve_in, reserve_out, fee_bps=25))]
pub fn compute_price_impact(
    amount_in: u64,
    reserve_in: u64,
    reserve_out: u64,
    fee_bps: u64,
) -> PyResult<f64> {
    if reserve_in == 0 || reserve_out == 0 || amount_in == 0 {
        return Ok(0.0);
    }
    
    // Spot price before swap
    let spot_price = reserve_out as f64 / reserve_in as f64;
    
    // Execute swap
    let amount_out = compute_amm_out(amount_in, reserve_in, reserve_out, fee_bps)?;
    
    // Effective price
    let effective_price = amount_out as f64 / amount_in as f64;
    
    // Price impact = (spot_price - effective_price) / spot_price * 100
    let impact = ((spot_price - effective_price) / spot_price) * 100.0;
    
    Ok(impact.max(0.0)) // Clamp to positive
}

// ============================================================================
// PHASE 2: CLMM (Concentrated Liquidity Market Maker)
// Supports: Orca Whirlpool, Raydium CLMM
// ============================================================================

/// Q64.64 fixed-point constant (2^64)
const Q64: u128 = 1u128 << 64;

/// Compute output amount for a CLMM swap within a single tick range.
/// 
/// This is an approximation that assumes the swap does NOT cross tick boundaries.
/// For accurate multi-tick swaps, call this iteratively or use the full SDK.
/// 
/// # Arguments
/// * `amount_in` - Input token amount
/// * `sqrt_price_x64` - Current sqrt price as Q64.64 fixed point
/// * `liquidity` - Active liquidity in the current tick range
/// * `a_to_b` - True if swapping token A for token B (price decreases)
/// * `fee_rate_bps` - Fee rate in basis points (e.g., 30 = 0.3%)
/// 
/// # Returns
/// Tuple of (amount_out, new_sqrt_price_x64)
#[pyfunction]
#[pyo3(signature = (amount_in, sqrt_price_x64, liquidity, a_to_b, fee_rate_bps=30))]
pub fn compute_clmm_swap(
    amount_in: u64,
    sqrt_price_x64: u128,
    liquidity: u128,
    a_to_b: bool,
    fee_rate_bps: u64,
) -> PyResult<(u64, u128)> {
    if amount_in == 0 || liquidity == 0 || sqrt_price_x64 == 0 {
        return Ok((0, sqrt_price_x64));
    }
    
    // Apply fee to input
    let fee_factor = 10000u128 - fee_rate_bps as u128;
    let amount_in_after_fee = (amount_in as u128 * fee_factor) / 10000;
    
    if a_to_b {
        // Swapping A -> B (selling A, price goes down)
        // delta_sqrt_price = amount_in * Q64 / liquidity
        // new_sqrt_price = old_sqrt_price - delta_sqrt_price
        
        let delta_sqrt_price = (amount_in_after_fee * Q64)
            .checked_div(liquidity)
            .unwrap_or(0);
        
        let new_sqrt_price = sqrt_price_x64.saturating_sub(delta_sqrt_price);
        
        if new_sqrt_price == 0 {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Swap would drain pool (sqrt_price would be 0)"
            ));
        }
        
        // amount_out = liquidity * (1/new_sqrt_price - 1/old_sqrt_price) * Q64
        // Simplified: amount_out = liquidity * delta_sqrt_price / (sqrt_price_old * sqrt_price_new / Q64)
        let amount_out = compute_b_from_sqrt_price_change(
            sqrt_price_x64, 
            new_sqrt_price, 
            liquidity
        )?;
        
        Ok((amount_out, new_sqrt_price))
    } else {
        // Swapping B -> A (buying A, price goes up)
        // delta_sqrt_price = amount_in * sqrt_price^2 / (liquidity * Q64)
        
        // For B -> A: new_sqrt_price = old_sqrt_price + (amount_in * old_sqrt_price / liquidity)
        let delta_sqrt_price = (amount_in_after_fee * sqrt_price_x64)
            .checked_div(liquidity)
            .unwrap_or(0);
        
        let new_sqrt_price = sqrt_price_x64.saturating_add(delta_sqrt_price);
        
        // amount_out (in A) = liquidity * (new_sqrt_price - old_sqrt_price) / Q64
        let amount_out = compute_a_from_sqrt_price_change(
            sqrt_price_x64,
            new_sqrt_price,
            liquidity
        )?;
        
        Ok((amount_out, new_sqrt_price))
    }
}

/// Helper: Compute amount of token B received from a sqrt_price decrease (A->B swap)
fn compute_b_from_sqrt_price_change(
    sqrt_price_old: u128,
    sqrt_price_new: u128,
    liquidity: u128,
) -> PyResult<u64> {
    // amount_b = liquidity * (sqrt_price_old - sqrt_price_new) / Q64
    let delta = sqrt_price_old.saturating_sub(sqrt_price_new);
    let amount = (liquidity * delta) / Q64;
    Ok(amount.min(u64::MAX as u128) as u64)
}

/// Helper: Compute amount of token A received from a sqrt_price increase (B->A swap)
fn compute_a_from_sqrt_price_change(
    sqrt_price_old: u128,
    sqrt_price_new: u128,
    liquidity: u128,
) -> PyResult<u64> {
    // amount_a = liquidity * Q64 * (1/sqrt_price_old - 1/sqrt_price_new)
    // = liquidity * Q64 * (sqrt_price_new - sqrt_price_old) / (sqrt_price_old * sqrt_price_new)
    
    if sqrt_price_old == 0 || sqrt_price_new == 0 {
        return Ok(0);
    }
    
    let delta = sqrt_price_new.saturating_sub(sqrt_price_old);
    
    // Use u128 arithmetic carefully to avoid overflow
    // amount = liquidity * delta / sqrt_price_old
    // (simplified since we're dividing by Q64 implicitly in the price representation)
    let amount = (liquidity * delta) / sqrt_price_old;
    let amount = amount / sqrt_price_new * Q64; // Normalize
    
    Ok(amount.min(u64::MAX as u128) as u64)
}

/// Convert a tick index to sqrt_price_x64.
/// 
/// Formula: sqrt_price = 1.0001^(tick/2) * 2^64
/// 
/// # Arguments
/// * `tick` - The tick index (can be negative)
/// 
/// # Returns
/// sqrt_price as Q64.64 fixed point
#[pyfunction]
pub fn sqrt_price_from_tick(tick: i32) -> PyResult<u128> {
    // sqrt(1.0001^tick) = 1.0001^(tick/2)
    // We compute this using: e^(tick * ln(1.0001) / 2)
    
    let tick_f64 = tick as f64;
    let ln_1_0001 = 0.00009999500033330834f64; // ln(1.0001)
    let exponent = tick_f64 * ln_1_0001 / 2.0;
    let sqrt_price = exponent.exp();
    
    // Convert to Q64.64
    let sqrt_price_x64 = (sqrt_price * (Q64 as f64)) as u128;
    
    Ok(sqrt_price_x64)
}

/// Convert sqrt_price_x64 back to a tick index.
/// 
/// # Arguments
/// * `sqrt_price_x64` - sqrt price as Q64.64 fixed point
/// 
/// # Returns
/// Tick index (rounded down)
#[pyfunction]
pub fn tick_from_sqrt_price(sqrt_price_x64: u128) -> PyResult<i32> {
    if sqrt_price_x64 == 0 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "sqrt_price cannot be zero"
        ));
    }
    
    // Convert from Q64.64 to f64
    let sqrt_price = (sqrt_price_x64 as f64) / (Q64 as f64);
    
    // tick = 2 * log(sqrt_price) / log(1.0001)
    let ln_1_0001 = 0.00009999500033330834f64;
    let tick = (2.0 * sqrt_price.ln()) / ln_1_0001;
    
    Ok(tick.floor() as i32)
}

/// Get the current price from sqrt_price_x64.
/// 
/// # Returns
/// Price of token A in terms of token B (as f64)
#[pyfunction]
pub fn price_from_sqrt_price(sqrt_price_x64: u128) -> PyResult<f64> {
    if sqrt_price_x64 == 0 {
        return Ok(0.0);
    }
    
    let sqrt_price = (sqrt_price_x64 as f64) / (Q64 as f64);
    Ok(sqrt_price * sqrt_price)
}

// ============================================================================
// PHASE 3: DLMM (Discrete Liquidity Market Maker - Meteora)
// ============================================================================

/// The "zero bin" offset used in Meteora DLMM.
/// Bin IDs are stored as u24, with 2^23 representing price = 1.0
const DLMM_BIN_OFFSET: i32 = 8388608; // 2^23

/// Compute the price for a given bin ID.
/// 
/// Formula: price = (1 + bin_step/10000)^(bin_id - 2^23)
/// 
/// # Arguments
/// * `bin_id` - The bin ID (typically around 2^23 for price = 1.0)
/// * `bin_step` - The bin step in basis points (e.g., 10 = 0.1% per bin)
/// 
/// # Returns
/// Price as f64
#[pyfunction]
pub fn dlmm_price_from_bin(bin_id: i32, bin_step: u16) -> PyResult<f64> {
    let exponent = bin_id - DLMM_BIN_OFFSET;
    let base = 1.0 + (bin_step as f64) / 10000.0;
    let price = base.powi(exponent);
    Ok(price)
}

/// Convert a price to the nearest bin ID.
/// 
/// Formula: bin_id = log(price) / log(1 + bin_step/10000) + 2^23
/// 
/// # Arguments
/// * `price` - The target price
/// * `bin_step` - The bin step in basis points
/// 
/// # Returns
/// Bin ID (rounded down)
#[pyfunction]
pub fn dlmm_bin_from_price(price: f64, bin_step: u16) -> PyResult<i32> {
    if price <= 0.0 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "Price must be positive"
        ));
    }
    
    let base = 1.0 + (bin_step as f64) / 10000.0;
    let exponent = price.ln() / base.ln();
    let bin_id = (exponent.floor() as i32) + DLMM_BIN_OFFSET;
    
    Ok(bin_id)
}

/// Compute output amount for a DLMM swap within a single bin.
/// 
/// In a single bin, the swap behaves like a constant sum AMM (linear).
/// 
/// # Arguments
/// * `amount_in` - Input token amount
/// * `bin_reserve_in` - Reserve of input token in this bin
/// * `bin_reserve_out` - Reserve of output token in this bin
/// * `bin_id` - The bin ID (used for price calculation)
/// * `bin_step` - Bin step in basis points
/// * `fee_rate_bps` - Fee rate in basis points
/// * `swap_for_y` - True if swapping X for Y (token A for token B)
/// 
/// # Returns
/// Tuple of (amount_out, amount_in_consumed, bin_crossed)
#[pyfunction]
#[pyo3(signature = (amount_in, bin_reserve_in, bin_reserve_out, bin_id, bin_step, fee_rate_bps=25, swap_for_y=true))]
pub fn compute_dlmm_swap_single_bin(
    amount_in: u64,
    _bin_reserve_in: u64,
    bin_reserve_out: u64,
    bin_id: i32,
    bin_step: u16,
    fee_rate_bps: u64,
    swap_for_y: bool,
) -> PyResult<(u64, u64, bool)> {
    if amount_in == 0 || bin_reserve_out == 0 {
        return Ok((0, 0, false));
    }
    
    // Calculate price for this bin
    let price = dlmm_price_from_bin(bin_id, bin_step)?;
    
    // Apply fee
    let fee_factor = (10000u64 - fee_rate_bps) as f64 / 10000.0;
    let amount_in_after_fee = (amount_in as f64) * fee_factor;
    
    // In DLMM, within a bin, swap is at constant price
    // amount_out = amount_in * price (for X->Y) or amount_in / price (for Y->X)
    let amount_out_f64 = if swap_for_y {
        amount_in_after_fee * price
    } else {
        amount_in_after_fee / price
    };
    
    // Check if we can fully satisfy from this bin
    let amount_out = amount_out_f64 as u64;
    
    if amount_out <= bin_reserve_out {
        // Fully satisfied within this bin
        Ok((amount_out, amount_in, false))
    } else {
        // Need to cross to next bin
        // How much input does it take to drain this bin?
        let max_out = bin_reserve_out;
        let input_needed_f64 = if swap_for_y {
            (max_out as f64) / price / fee_factor
        } else {
            (max_out as f64) * price / fee_factor
        };
        
        let input_consumed = (input_needed_f64.ceil() as u64).min(amount_in);
        
        Ok((max_out, input_consumed, true))
    }
}

/// Compute output for a DLMM swap across multiple bins.
/// 
/// This simulates traversing bins until all input is consumed or we run out of liquidity.
/// 
/// # Arguments
/// * `amount_in` - Total input amount
/// * `active_bin_id` - Starting bin ID
/// * `bin_step` - Bin step in basis points
/// * `bin_reserves` - Vec of (bin_id, reserve_x, reserve_y) tuples, sorted by bin_id
/// * `fee_rate_bps` - Fee rate in basis points
/// * `swap_for_y` - True if swapping X for Y
/// 
/// # Returns
/// Tuple of (total_amount_out, final_bin_id)
#[pyfunction]
#[pyo3(signature = (amount_in, active_bin_id, bin_step, bin_reserves, fee_rate_bps=25, swap_for_y=true))]
pub fn compute_dlmm_swap(
    amount_in: u64,
    active_bin_id: i32,
    bin_step: u16,
    bin_reserves: Vec<(i32, u64, u64)>, // (bin_id, reserve_x, reserve_y)
    fee_rate_bps: u64,
    swap_for_y: bool,
) -> PyResult<(u64, i32)> {
    if amount_in == 0 || bin_reserves.is_empty() {
        return Ok((0, active_bin_id));
    }
    
    let mut remaining_in = amount_in;
    let mut total_out = 0u64;
    let mut current_bin_id = active_bin_id;
    
    // Sort bins in the direction we're traversing
    let mut sorted_bins = bin_reserves.clone();
    if swap_for_y {
        // Swapping X for Y: price decreases, traverse bins downward
        sorted_bins.sort_by(|a, b| b.0.cmp(&a.0)); // Descending
    } else {
        // Swapping Y for X: price increases, traverse bins upward
        sorted_bins.sort_by(|a, b| a.0.cmp(&b.0)); // Ascending
    }
    
    // Find starting position
    let start_idx = sorted_bins.iter().position(|(bid, _, _)| *bid == active_bin_id);
    let start_idx = match start_idx {
        Some(idx) => idx,
        None => return Ok((0, active_bin_id)), // Active bin not found
    };
    
    for i in start_idx..sorted_bins.len() {
        if remaining_in == 0 {
            break;
        }
        
        let (bin_id, reserve_x, reserve_y) = sorted_bins[i];
        current_bin_id = bin_id;
        
        // Determine reserves based on swap direction
        let (reserve_in, reserve_out) = if swap_for_y {
            (reserve_x, reserve_y)
        } else {
            (reserve_y, reserve_x)
        };
        
        let (out, consumed, _crossed) = compute_dlmm_swap_single_bin(
            remaining_in,
            reserve_in,
            reserve_out,
            bin_id,
            bin_step,
            fee_rate_bps,
            swap_for_y,
        )?;
        
        total_out = total_out.saturating_add(out);
        remaining_in = remaining_in.saturating_sub(consumed);
    }
    
    Ok((total_out, current_bin_id))
}

/// Get composable swap fee for DLMM (used for MEV protection).
/// 
/// Meteora DLMM supports dynamic fees. This returns the base fee
/// plus any volatility adjustments.
/// 
/// # Arguments
/// * `base_fee_bps` - Base fee in basis points
/// * `volatility_accumulator` - Current volatility accumulator value (0-1000000)
/// 
/// # Returns
/// Effective fee in basis points
#[pyfunction]
#[pyo3(signature = (base_fee_bps, volatility_accumulator=0))]
pub fn dlmm_get_effective_fee(
    base_fee_bps: u64,
    volatility_accumulator: u64,
) -> PyResult<u64> {
    // Meteora applies a volatility multiplier up to 10x base fee
    let vol_multiplier = 1.0 + (volatility_accumulator as f64 / 100000.0);
    let effective_fee = (base_fee_bps as f64 * vol_multiplier) as u64;
    
    // Cap at reasonable maximum (10% = 1000 bps)
    Ok(effective_fee.min(1000))
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_amm_functions(m: &PyModule) -> PyResult<()> {
    // Phase 1: Constant Product AMM
    m.add_function(wrap_pyfunction!(compute_amm_out, m)?)?;
    m.add_function(wrap_pyfunction!(compute_amm_in, m)?)?;
    m.add_function(wrap_pyfunction!(compute_amm_out_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_price_impact, m)?)?;
    
    // Phase 2: CLMM
    m.add_function(wrap_pyfunction!(compute_clmm_swap, m)?)?;
    m.add_function(wrap_pyfunction!(sqrt_price_from_tick, m)?)?;
    m.add_function(wrap_pyfunction!(tick_from_sqrt_price, m)?)?;
    m.add_function(wrap_pyfunction!(price_from_sqrt_price, m)?)?;
    
    // Phase 3: DLMM
    m.add_function(wrap_pyfunction!(dlmm_price_from_bin, m)?)?;
    m.add_function(wrap_pyfunction!(dlmm_bin_from_price, m)?)?;
    m.add_function(wrap_pyfunction!(compute_dlmm_swap_single_bin, m)?)?;
    m.add_function(wrap_pyfunction!(compute_dlmm_swap, m)?)?;
    m.add_function(wrap_pyfunction!(dlmm_get_effective_fee, m)?)?;
    
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_amm_out_basic() {
        // SOL/USDC pool: 1000 SOL, 100000 USDC
        // Swap 1 SOL -> expect ~99.7 USDC (after 0.25% fee)
        let out = compute_amm_out(1_000_000_000, 1000_000_000_000, 100000_000_000, 25).unwrap();
        
        // Should be approximately 99.75 USDC (99750000 in 6 decimals)
        // Allow 1% tolerance
        assert!(out > 99_000_000 && out < 100_000_000);
    }

    #[test]
    fn test_compute_amm_in_basic() {
        // Inverse: If I want 99 USDC, how much SOL do I need?
        let in_amt = compute_amm_in(99_000_000, 1000_000_000_000, 100000_000_000, 25).unwrap();
        
        // Should be approximately 1 SOL
        assert!(in_amt > 900_000_000 && in_amt < 1_100_000_000);
    }

    #[test]
    fn test_zero_input() {
        let out = compute_amm_out(0, 1000, 1000, 25).unwrap();
        assert_eq!(out, 0);
    }

    #[test]
    fn test_price_impact() {
        // Large trade should have meaningful impact
        let impact = compute_price_impact(100_000_000_000, 1000_000_000_000, 100000_000_000, 25).unwrap();
        
        // 10% of pool should have noticeable impact
        assert!(impact > 5.0);
    }
}
