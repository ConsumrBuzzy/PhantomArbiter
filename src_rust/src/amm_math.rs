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
// PHASE 2: CLMM (Concentrated Liquidity) - Placeholder
// ============================================================================

// TODO: Implement compute_clmm_swap for Orca Whirlpool / Raydium CLMM

// ============================================================================
// PHASE 3: DLMM (Discrete Liquidity) - Placeholder
// ============================================================================

// TODO: Implement compute_dlmm_swap for Meteora DLMM

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_amm_functions(m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_amm_out, m)?)?;
    m.add_function(wrap_pyfunction!(compute_amm_in, m)?)?;
    m.add_function(wrap_pyfunction!(compute_amm_out_batch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_price_impact, m)?)?;
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
