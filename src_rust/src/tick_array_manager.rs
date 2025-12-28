// ------------------------------------------------------------------------
// TICK ARRAY MANAGER (Phase 19)
// Raydium CLMM Tick Array Derivation and Pool State Parsing
// ------------------------------------------------------------------------
//
// CLMM swaps require 3 Tick Array accounts. Incorrect arrays = 100% failure.
// This module provides:
// 1. Pool state parsing (sqrt_price → current_tick)
// 2. Tick array PDA derivation
// 3. Array selection logic for swap direction

use pyo3::prelude::*;
use solana_sdk::pubkey::Pubkey;
use std::str::FromStr;
use bytemuck::{Pod, Zeroable};

// ============================================================================
// CONSTANTS
// ============================================================================

/// Raydium CLMM Program ID
const RAYDIUM_CLMM_PROGRAM: &str = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK";

/// Number of ticks per tick array (Raydium uses 60)
const TICKS_PER_ARRAY: i32 = 60;

/// Q64.64 fixed-point constant (2^64)
const Q64: u128 = 1u128 << 64;

// ============================================================================
// POOL STATE PARSING
// ============================================================================

/// Raydium CLMM Pool State (partial structure for tick extraction)
/// Full size is ~1544 bytes, we only need the first ~200 for tick info
#[repr(C, packed)]
#[derive(Copy, Clone)]
pub struct ClmmPoolStatePartial {
    /// Discriminator (8 bytes) - Anchor account discriminator
    pub discriminator: [u8; 8],
    /// Bump seed (1 byte)
    pub bump: u8,
    /// AMM Config pubkey (32 bytes)
    pub amm_config: [u8; 32],
    /// Owner pubkey (32 bytes)
    pub owner: [u8; 32],
    /// Token Mint 0 (32 bytes)
    pub token_mint_0: [u8; 32],
    /// Token Mint 1 (32 bytes)
    pub token_mint_1: [u8; 32],
    /// Token Vault 0 (32 bytes)
    pub token_vault_0: [u8; 32],
    /// Token Vault 1 (32 bytes)
    pub token_vault_1: [u8; 32],
    /// Observation Key (32 bytes)
    pub observation_key: [u8; 32],
    /// Mint 0 decimals (1 byte)
    pub mint_decimals_0: u8,
    /// Mint 1 decimals (1 byte)
    pub mint_decimals_1: u8,
    /// Tick spacing (2 bytes)
    pub tick_spacing: u16,
    /// Liquidity (16 bytes, u128)
    pub liquidity: [u8; 16],
    /// Sqrt price X64 (16 bytes, u128)
    pub sqrt_price_x64: [u8; 16],
    /// Current tick (4 bytes, i32)
    pub tick_current: i32,
    // Padding to align (2 bytes)
    pub _padding: [u8; 2],
    /// Protocol fees token 0 (8 bytes, u64)
    pub protocol_fees_token_0: u64,
    /// Protocol fees token 1 (8 bytes, u64)
    pub protocol_fees_token_1: u64,
    /// Fund fees token 0 (8 bytes, u64)
    pub fund_fees_token_0: u64,
    /// Fund fees token 1 (8 bytes, u64)
    pub fund_fees_token_1: u64,
}

// Safety: This struct is repr(C, packed) and all fields are Copy
unsafe impl Pod for ClmmPoolStatePartial {}
unsafe impl Zeroable for ClmmPoolStatePartial {}

/// Parsed CLMM pool information returned to Python
#[pyclass]
#[derive(Clone)]
pub struct ClmmPoolInfo {
    #[pyo3(get)]
    pub pool_id: String,
    #[pyo3(get)]
    pub amm_config: String,
    #[pyo3(get)]
    pub token_mint_0: String,
    #[pyo3(get)]
    pub token_mint_1: String,
    #[pyo3(get)]
    pub token_vault_0: String,
    #[pyo3(get)]
    pub token_vault_1: String,
    #[pyo3(get)]
    pub observation_key: String,
    #[pyo3(get)]
    pub tick_spacing: u16,
    #[pyo3(get)]
    pub tick_current: i32,
    #[pyo3(get)]
    pub sqrt_price_x64: String, // u128 as string to avoid overflow
    #[pyo3(get)]
    pub liquidity: String, // u128 as string
    #[pyo3(get)]
    pub mint_decimals_0: u8,
    #[pyo3(get)]
    pub mint_decimals_1: u8,
}

#[pymethods]
impl ClmmPoolInfo {
    fn __repr__(&self) -> String {
        format!(
            "ClmmPoolInfo(tick={}, spacing={}, mints=[{}, {}])",
            self.tick_current,
            self.tick_spacing,
            &self.token_mint_0[..8],
            &self.token_mint_1[..8]
        )
    }
    
    /// Get price from sqrt_price_x64
    pub fn get_price(&self) -> PyResult<f64> {
        let sqrt_price: u128 = self.sqrt_price_x64.parse()
            .map_err(|_| PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid sqrt_price"))?;
        
        if sqrt_price == 0 {
            return Ok(0.0);
        }
        
        let sqrt_price_f64 = (sqrt_price as f64) / (Q64 as f64);
        Ok(sqrt_price_f64 * sqrt_price_f64)
    }
}

/// Parse Raydium CLMM pool state from base64-encoded account data.
/// 
/// # Arguments
/// * `pool_id` - Pool address as base58 string
/// * `data_b64` - Base64-encoded account data
/// 
/// # Returns
/// ClmmPoolInfo with parsed tick and price information
#[pyfunction]
pub fn parse_clmm_pool_state(pool_id: String, data_b64: String) -> PyResult<ClmmPoolInfo> {
    use base64::{Engine as _, engine::general_purpose};
    
    let data = general_purpose::STANDARD.decode(&data_b64)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Base64 decode error: {}", e)
        ))?;
    
    // Minimum size check (we need at least 300 bytes for the partial struct)
    if data.len() < 300 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Data too short: {} bytes, need at least 300", data.len())
        ));
    }
    
    // Parse using bytemuck (zero-copy where possible)
    let state: &ClmmPoolStatePartial = bytemuck::from_bytes(&data[..std::mem::size_of::<ClmmPoolStatePartial>()]);
    
    // Convert fixed arrays to pubkey strings
    let amm_config = bs58::encode(&state.amm_config).into_string();
    let token_mint_0 = bs58::encode(&state.token_mint_0).into_string();
    let token_mint_1 = bs58::encode(&state.token_mint_1).into_string();
    let token_vault_0 = bs58::encode(&state.token_vault_0).into_string();
    let token_vault_1 = bs58::encode(&state.token_vault_1).into_string();
    let observation_key = bs58::encode(&state.observation_key).into_string();
    
    // Parse u128 values
    let sqrt_price_x64 = u128::from_le_bytes(state.sqrt_price_x64);
    let liquidity = u128::from_le_bytes(state.liquidity);
    
    Ok(ClmmPoolInfo {
        pool_id,
        amm_config,
        token_mint_0,
        token_mint_1,
        token_vault_0,
        token_vault_1,
        observation_key,
        tick_spacing: state.tick_spacing,
        tick_current: state.tick_current,
        sqrt_price_x64: sqrt_price_x64.to_string(),
        liquidity: liquidity.to_string(),
        mint_decimals_0: state.mint_decimals_0,
        mint_decimals_1: state.mint_decimals_1,
    })
}

// ============================================================================
// TICK ARRAY DERIVATION
// ============================================================================

/// Calculate the tick array index for a given tick.
/// 
/// Formula: array_index = floor(tick / (tick_spacing * TICKS_PER_ARRAY))
fn get_tick_array_index(tick: i32, tick_spacing: u16) -> i32 {
    let ticks_in_array = (tick_spacing as i32) * TICKS_PER_ARRAY;
    
    // Handle negative ticks correctly (floor division)
    if tick >= 0 {
        tick / ticks_in_array
    } else {
        // For negative numbers, we need to subtract 1 if there's a remainder
        let div = tick / ticks_in_array;
        let rem = tick % ticks_in_array;
        if rem != 0 { div - 1 } else { div }
    }
}

/// Calculate the start tick for a tick array at the given index.
fn get_tick_array_start_tick(array_index: i32, tick_spacing: u16) -> i32 {
    array_index * (tick_spacing as i32) * TICKS_PER_ARRAY
}

/// Derive the PDA for a tick array.
/// 
/// Seeds: ["tick_array", pool_id, start_tick_bytes]
fn derive_tick_array_pda(pool_id: &Pubkey, start_tick: i32) -> Result<Pubkey, String> {
    let program_id = Pubkey::from_str(RAYDIUM_CLMM_PROGRAM)
        .map_err(|e| e.to_string())?;
    
    let start_tick_bytes = start_tick.to_le_bytes();
    
    let seeds: &[&[u8]] = &[
        b"tick_array",
        pool_id.as_ref(),
        &start_tick_bytes,
    ];
    
    let (pda, _bump) = Pubkey::find_program_address(seeds, &program_id);
    Ok(pda)
}

/// Derive the 3 tick arrays needed for a CLMM swap.
/// 
/// # Arguments
/// * `pool_id` - Pool address as base58 string
/// * `tick_current` - Current tick from pool state
/// * `tick_spacing` - Tick spacing from pool state
/// * `a_to_b` - Swap direction (true = token0 → token1, price decreases)
/// 
/// # Returns
/// Tuple of (tick_array_lower, tick_array_current, tick_array_upper) as base58 strings
#[pyfunction]
pub fn derive_tick_arrays(
    pool_id: &str,
    tick_current: i32,
    tick_spacing: u16,
    a_to_b: bool,
) -> PyResult<(String, String, String)> {
    let pool_pubkey = Pubkey::from_str(pool_id)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Invalid pool_id: {}", e)
        ))?;
    
    // Calculate current array index
    let current_index = get_tick_array_index(tick_current, tick_spacing);
    
    // Get array indices based on swap direction
    // A→B (price down): need current and lower arrays
    // B→A (price up): need current and upper arrays
    let (lower_index, upper_index) = if a_to_b {
        (current_index - 1, current_index)
    } else {
        (current_index, current_index + 1)
    };
    
    // Calculate start ticks
    let lower_start = get_tick_array_start_tick(lower_index, tick_spacing);
    let current_start = get_tick_array_start_tick(current_index, tick_spacing);
    let upper_start = get_tick_array_start_tick(upper_index, tick_spacing);
    
    // Derive PDAs
    let lower_pda = derive_tick_array_pda(&pool_pubkey, lower_start)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    let current_pda = derive_tick_array_pda(&pool_pubkey, current_start)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    let upper_pda = derive_tick_array_pda(&pool_pubkey, upper_start)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
    
    Ok((
        lower_pda.to_string(),
        current_pda.to_string(),
        upper_pda.to_string(),
    ))
}

/// Derive tick arrays with extra headroom for high-volatility swaps.
/// 
/// Returns 5 tick arrays: [current-2, current-1, current, current+1, current+2]
/// Use the 3 most relevant based on swap direction and expected slippage.
#[pyfunction]
pub fn derive_tick_arrays_extended(
    pool_id: &str,
    tick_current: i32,
    tick_spacing: u16,
) -> PyResult<Vec<String>> {
    let pool_pubkey = Pubkey::from_str(pool_id)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Invalid pool_id: {}", e)
        ))?;
    
    let current_index = get_tick_array_index(tick_current, tick_spacing);
    
    let mut arrays = Vec::with_capacity(5);
    
    for offset in -2..=2 {
        let array_index = current_index + offset;
        let start_tick = get_tick_array_start_tick(array_index, tick_spacing);
        let pda = derive_tick_array_pda(&pool_pubkey, start_tick)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))?;
        arrays.push(pda.to_string());
    }
    
    Ok(arrays)
}

/// Convert sqrt_price_x64 to tick index.
/// 
/// Formula: tick = 2 * log(sqrt_price) / log(1.0001)
#[pyfunction]
pub fn sqrt_price_to_tick(sqrt_price_x64: u128) -> PyResult<i32> {
    if sqrt_price_x64 == 0 {
        return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            "sqrt_price cannot be zero"
        ));
    }
    
    let sqrt_price = (sqrt_price_x64 as f64) / (Q64 as f64);
    let ln_1_0001 = 0.00009999500033330834f64; // ln(1.0001)
    let tick = (2.0 * sqrt_price.ln()) / ln_1_0001;
    
    Ok(tick.floor() as i32)
}

/// Convert tick index to sqrt_price_x64.
/// 
/// Formula: sqrt_price = 1.0001^(tick/2) * 2^64
#[pyfunction]
pub fn tick_to_sqrt_price(tick: i32) -> PyResult<u128> {
    let tick_f64 = tick as f64;
    let ln_1_0001 = 0.00009999500033330834f64;
    let exponent = tick_f64 * ln_1_0001 / 2.0;
    let sqrt_price = exponent.exp();
    
    let sqrt_price_x64 = (sqrt_price * (Q64 as f64)) as u128;
    
    Ok(sqrt_price_x64)
}

// ============================================================================
// MODULE REGISTRATION
// ============================================================================

pub fn register_tick_array_functions(m: &PyModule) -> PyResult<()> {
    // Pool state parsing
    m.add_class::<ClmmPoolInfo>()?;
    m.add_function(wrap_pyfunction!(parse_clmm_pool_state, m)?)?;
    
    // Tick array derivation
    m.add_function(wrap_pyfunction!(derive_tick_arrays, m)?)?;
    m.add_function(wrap_pyfunction!(derive_tick_arrays_extended, m)?)?;
    
    // Tick/price conversion
    m.add_function(wrap_pyfunction!(sqrt_price_to_tick, m)?)?;
    m.add_function(wrap_pyfunction!(tick_to_sqrt_price, m)?)?;
    
    Ok(())
}

// ============================================================================
// TESTS
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tick_array_index_positive() {
        // tick=1000, spacing=10, TICKS_PER_ARRAY=60
        // 1000 / (10 * 60) = 1000 / 600 = 1
        assert_eq!(get_tick_array_index(1000, 10), 1);
    }

    #[test]
    fn test_tick_array_index_negative() {
        // tick=-1000, spacing=10
        // -1000 / 600 = -1.67 → floor = -2
        assert_eq!(get_tick_array_index(-1000, 10), -2);
    }

    #[test]
    fn test_tick_array_index_zero() {
        assert_eq!(get_tick_array_index(0, 10), 0);
    }

    #[test]
    fn test_tick_array_start() {
        // array_index=1, spacing=10
        // 1 * 10 * 60 = 600
        assert_eq!(get_tick_array_start_tick(1, 10), 600);
    }

    #[test]
    fn test_tick_roundtrip() {
        let original_tick = 12345;
        let sqrt_price = tick_to_sqrt_price(original_tick).unwrap();
        let recovered_tick = sqrt_price_to_tick(sqrt_price).unwrap();
        
        // Allow +/- 1 due to rounding
        assert!((recovered_tick - original_tick).abs() <= 1);
    }
}
