// ------------------------------------------------------------------------
// INSTRUCTION BUILDER (THE FORGE)
// Native DEX instruction building for sub-millisecond transaction assembly
// Phase 1: Raydium AMM V4
// Phase 2: Orca Whirlpool
// Phase 3: Meteora DLMM
// ------------------------------------------------------------------------

use pyo3::prelude::*;
use solana_sdk::{
    instruction::{AccountMeta, Instruction},
    pubkey::Pubkey,
};
use std::str::FromStr;

// ============================================================================
// CONSTANTS: DEX PROGRAM IDs
// ============================================================================

/// Raydium AMM V4 Program ID
const RAYDIUM_AMM_V4: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";

/// Orca Whirlpool Program ID  
const ORCA_WHIRLPOOL: &str = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

/// Meteora DLMM Program ID
const METEORA_DLMM: &str = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo";

/// SPL Token Program ID
const TOKEN_PROGRAM: &str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

// ============================================================================
// PHASE 1: RAYDIUM AMM V4 SWAP
// ============================================================================

/// Build a Raydium AMM V4 swap instruction.
/// 
/// # Arguments
/// * `amm_id` - The AMM pool address
/// * `amm_authority` - The AMM authority PDA
/// * `amm_open_orders` - Open orders account
/// * `amm_target_orders` - Target orders account (can be same as open_orders)
/// * `pool_coin_token` - Pool's coin token account
/// * `pool_pc_token` - Pool's PC (quote) token account
/// * `serum_program` - Serum DEX program ID
/// * `serum_market` - Serum market address
/// * `serum_bids` - Serum bids account
/// * `serum_asks` - Serum asks account
/// * `serum_event_queue` - Serum event queue
/// * `serum_coin_vault` - Serum coin vault
/// * `serum_pc_vault` - Serum PC vault
/// * `serum_vault_signer` - Serum vault signer PDA
/// * `user_source` - User's source token account
/// * `user_destination` - User's destination token account
/// * `user_owner` - User's wallet (signer)
/// * `amount_in` - Amount of tokens to swap
/// * `minimum_amount_out` - Minimum tokens to receive (slippage protection)
/// 
/// # Returns
/// Tuple of (instruction_data as bytes, serialized instruction as bytes)
#[pyfunction]
#[pyo3(signature = (
    amm_id,
    amm_authority,
    amm_open_orders,
    amm_target_orders,
    pool_coin_token,
    pool_pc_token,
    serum_program,
    serum_market,
    serum_bids,
    serum_asks,
    serum_event_queue,
    serum_coin_vault,
    serum_pc_vault,
    serum_vault_signer,
    user_source,
    user_destination,
    user_owner,
    amount_in,
    minimum_amount_out
))]
pub fn build_raydium_swap_ix(
    amm_id: &str,
    amm_authority: &str,
    amm_open_orders: &str,
    amm_target_orders: &str,
    pool_coin_token: &str,
    pool_pc_token: &str,
    serum_program: &str,
    serum_market: &str,
    serum_bids: &str,
    serum_asks: &str,
    serum_event_queue: &str,
    serum_coin_vault: &str,
    serum_pc_vault: &str,
    serum_vault_signer: &str,
    user_source: &str,
    user_destination: &str,
    user_owner: &str,
    amount_in: u64,
    minimum_amount_out: u64,
) -> PyResult<Vec<u8>> {
    // Parse all pubkeys
    let token_program = Pubkey::from_str(TOKEN_PROGRAM)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let raydium_program = Pubkey::from_str(RAYDIUM_AMM_V4)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    
    let amm_id_pk = parse_pubkey(amm_id)?;
    let amm_authority_pk = parse_pubkey(amm_authority)?;
    let amm_open_orders_pk = parse_pubkey(amm_open_orders)?;
    let amm_target_orders_pk = parse_pubkey(amm_target_orders)?;
    let pool_coin_token_pk = parse_pubkey(pool_coin_token)?;
    let pool_pc_token_pk = parse_pubkey(pool_pc_token)?;
    let serum_program_pk = parse_pubkey(serum_program)?;
    let serum_market_pk = parse_pubkey(serum_market)?;
    let serum_bids_pk = parse_pubkey(serum_bids)?;
    let serum_asks_pk = parse_pubkey(serum_asks)?;
    let serum_event_queue_pk = parse_pubkey(serum_event_queue)?;
    let serum_coin_vault_pk = parse_pubkey(serum_coin_vault)?;
    let serum_pc_vault_pk = parse_pubkey(serum_pc_vault)?;
    let serum_vault_signer_pk = parse_pubkey(serum_vault_signer)?;
    let user_source_pk = parse_pubkey(user_source)?;
    let user_destination_pk = parse_pubkey(user_destination)?;
    let user_owner_pk = parse_pubkey(user_owner)?;
    
    // Build account metas (order matters!)
    let accounts = vec![
        AccountMeta::new_readonly(token_program, false),           // 0
        AccountMeta::new(amm_id_pk, false),                        // 1
        AccountMeta::new_readonly(amm_authority_pk, false),        // 2
        AccountMeta::new(amm_open_orders_pk, false),               // 3
        AccountMeta::new(amm_target_orders_pk, false),             // 4
        AccountMeta::new(pool_coin_token_pk, false),               // 5
        AccountMeta::new(pool_pc_token_pk, false),                 // 6
        AccountMeta::new_readonly(serum_program_pk, false),        // 7
        AccountMeta::new(serum_market_pk, false),                  // 8
        AccountMeta::new(serum_bids_pk, false),                    // 9
        AccountMeta::new(serum_asks_pk, false),                    // 10
        AccountMeta::new(serum_event_queue_pk, false),             // 11
        AccountMeta::new(serum_coin_vault_pk, false),              // 12
        AccountMeta::new(serum_pc_vault_pk, false),                // 13
        AccountMeta::new_readonly(serum_vault_signer_pk, false),   // 14
        AccountMeta::new(user_source_pk, false),                   // 15
        AccountMeta::new(user_destination_pk, false),              // 16
        AccountMeta::new_readonly(user_owner_pk, true),            // 17 (signer)
    ];
    
    // Build instruction data
    // Raydium V4 Swap: [9, amount_in (8 bytes LE), minimum_amount_out (8 bytes LE)]
    let mut data = Vec::with_capacity(17);
    data.push(9u8); // Instruction discriminator for swap
    data.extend_from_slice(&amount_in.to_le_bytes());
    data.extend_from_slice(&minimum_amount_out.to_le_bytes());
    
    // Build instruction
    let ix = Instruction {
        program_id: raydium_program,
        accounts,
        data,
    };
    
    // Serialize instruction for transport
    let serialized = bincode::serialize(&ix)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    
    Ok(serialized)
}

/// Get the instruction data bytes only (for use with Python instruction building)
#[pyfunction]
pub fn build_raydium_swap_data(amount_in: u64, minimum_amount_out: u64) -> PyResult<Vec<u8>> {
    let mut data = Vec::with_capacity(17);
    data.push(9u8); // Instruction discriminator
    data.extend_from_slice(&amount_in.to_le_bytes());
    data.extend_from_slice(&minimum_amount_out.to_le_bytes());
    Ok(data)
}

// ============================================================================
// PHASE 2: ORCA WHIRLPOOL SWAP
// ============================================================================

/// Anchor discriminator for Whirlpool `swap` instruction
const WHIRLPOOL_SWAP_DISCRIMINATOR: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];

/// Build Orca Whirlpool swap instruction data.
/// 
/// # Arguments
/// * `amount` - Amount to swap (input or output depending on amount_specified_is_input)
/// * `other_amount_threshold` - Slippage threshold
/// * `sqrt_price_limit` - Price limit as Q64.64 (0 for no limit)
/// * `amount_specified_is_input` - True if `amount` is input amount
/// * `a_to_b` - True if swapping token A for token B
/// 
/// # Returns
/// Instruction data bytes (without accounts)
#[pyfunction]
#[pyo3(signature = (amount, other_amount_threshold, sqrt_price_limit, amount_specified_is_input=true, a_to_b=true))]
pub fn build_whirlpool_swap_data(
    amount: u64,
    other_amount_threshold: u64,
    sqrt_price_limit: u128,
    amount_specified_is_input: bool,
    a_to_b: bool,
) -> PyResult<Vec<u8>> {
    // Anchor instruction format:
    // [8 byte discriminator] + [borsh-encoded args]
    
    let mut data = Vec::with_capacity(8 + 8 + 8 + 16 + 1 + 1);
    
    // Discriminator
    data.extend_from_slice(&WHIRLPOOL_SWAP_DISCRIMINATOR);
    
    // Args (Borsh serialized)
    data.extend_from_slice(&amount.to_le_bytes());
    data.extend_from_slice(&other_amount_threshold.to_le_bytes());
    data.extend_from_slice(&sqrt_price_limit.to_le_bytes());
    data.push(amount_specified_is_input as u8);
    data.push(a_to_b as u8);
    
    Ok(data)
}

/// Build complete Whirlpool swap instruction with accounts.
#[pyfunction]
#[pyo3(signature = (
    whirlpool,
    token_owner_account_a,
    token_vault_a,
    token_owner_account_b,
    token_vault_b,
    tick_array_0,
    tick_array_1,
    tick_array_2,
    oracle,
    token_authority,
    amount,
    other_amount_threshold,
    sqrt_price_limit,
    amount_specified_is_input=true,
    a_to_b=true
))]
pub fn build_whirlpool_swap_ix(
    whirlpool: &str,
    token_owner_account_a: &str,
    token_vault_a: &str,
    token_owner_account_b: &str,
    token_vault_b: &str,
    tick_array_0: &str,
    tick_array_1: &str,
    tick_array_2: &str,
    oracle: &str,
    token_authority: &str,
    amount: u64,
    other_amount_threshold: u64,
    sqrt_price_limit: u128,
    amount_specified_is_input: bool,
    a_to_b: bool,
) -> PyResult<Vec<u8>> {
    let whirlpool_program = Pubkey::from_str(ORCA_WHIRLPOOL)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let token_program = Pubkey::from_str(TOKEN_PROGRAM)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    
    let accounts = vec![
        AccountMeta::new_readonly(token_program, false),           // token_program
        AccountMeta::new_readonly(parse_pubkey(token_authority)?, true), // token_authority (signer)
        AccountMeta::new(parse_pubkey(whirlpool)?, false),         // whirlpool
        AccountMeta::new(parse_pubkey(token_owner_account_a)?, false), // token_owner_account_a
        AccountMeta::new(parse_pubkey(token_vault_a)?, false),     // token_vault_a
        AccountMeta::new(parse_pubkey(token_owner_account_b)?, false), // token_owner_account_b
        AccountMeta::new(parse_pubkey(token_vault_b)?, false),     // token_vault_b
        AccountMeta::new(parse_pubkey(tick_array_0)?, false),      // tick_array_0
        AccountMeta::new(parse_pubkey(tick_array_1)?, false),      // tick_array_1
        AccountMeta::new(parse_pubkey(tick_array_2)?, false),      // tick_array_2
        AccountMeta::new_readonly(parse_pubkey(oracle)?, false),   // oracle
    ];
    
    let data = build_whirlpool_swap_data(
        amount,
        other_amount_threshold,
        sqrt_price_limit,
        amount_specified_is_input,
        a_to_b,
    )?;
    
    let ix = Instruction {
        program_id: whirlpool_program,
        accounts,
        data,
    };
    
    bincode::serialize(&ix)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
}

// ============================================================================
// PHASE 3: METEORA DLMM SWAP
// ============================================================================

/// Anchor discriminator for Meteora DLMM `swap` instruction
const DLMM_SWAP_DISCRIMINATOR: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];

/// Build Meteora DLMM swap instruction data.
/// 
/// # Arguments
/// * `amount_in` - Amount of tokens to swap
/// * `min_amount_out` - Minimum tokens to receive
/// 
/// # Returns
/// Instruction data bytes
#[pyfunction]
pub fn build_dlmm_swap_data(amount_in: u64, min_amount_out: u64) -> PyResult<Vec<u8>> {
    let mut data = Vec::with_capacity(8 + 8 + 8);
    
    // Discriminator
    data.extend_from_slice(&DLMM_SWAP_DISCRIMINATOR);
    
    // Args
    data.extend_from_slice(&amount_in.to_le_bytes());
    data.extend_from_slice(&min_amount_out.to_le_bytes());
    
    Ok(data)
}

/// Build complete DLMM swap instruction with accounts.
#[pyfunction]
#[pyo3(signature = (
    lb_pair,
    bin_array_bitmap_extension,
    reserve_x,
    reserve_y,
    user_token_in,
    user_token_out,
    token_x_mint,
    token_y_mint,
    oracle,
    host_fee_in,
    user,
    bin_arrays,
    amount_in,
    min_amount_out
))]
pub fn build_dlmm_swap_ix(
    lb_pair: &str,
    bin_array_bitmap_extension: &str,
    reserve_x: &str,
    reserve_y: &str,
    user_token_in: &str,
    user_token_out: &str,
    token_x_mint: &str,
    token_y_mint: &str,
    oracle: &str,
    host_fee_in: &str,
    user: &str,
    bin_arrays: Vec<String>,
    amount_in: u64,
    min_amount_out: u64,
) -> PyResult<Vec<u8>> {
    let dlmm_program = Pubkey::from_str(METEORA_DLMM)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    let token_program = Pubkey::from_str(TOKEN_PROGRAM)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    
    let mut accounts = vec![
        AccountMeta::new(parse_pubkey(lb_pair)?, false),
        AccountMeta::new_readonly(parse_pubkey(bin_array_bitmap_extension)?, false),
        AccountMeta::new(parse_pubkey(reserve_x)?, false),
        AccountMeta::new(parse_pubkey(reserve_y)?, false),
        AccountMeta::new(parse_pubkey(user_token_in)?, false),
        AccountMeta::new(parse_pubkey(user_token_out)?, false),
        AccountMeta::new_readonly(parse_pubkey(token_x_mint)?, false),
        AccountMeta::new_readonly(parse_pubkey(token_y_mint)?, false),
        AccountMeta::new_readonly(parse_pubkey(oracle)?, false),
        AccountMeta::new(parse_pubkey(host_fee_in)?, false),
        AccountMeta::new_readonly(parse_pubkey(user)?, true), // signer
        AccountMeta::new_readonly(token_program, false),
    ];
    
    // Add bin arrays (variable number)
    for bin_array in bin_arrays {
        accounts.push(AccountMeta::new(parse_pubkey(&bin_array)?, false));
    }
    
    let data = build_dlmm_swap_data(amount_in, min_amount_out)?;
    
    let ix = Instruction {
        program_id: dlmm_program,
        accounts,
        data,
    };
    
    bincode::serialize(&ix)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
}

// ============================================================================
// HELPERS
// ============================================================================

fn parse_pubkey(s: &str) -> PyResult<Pubkey> {
    Pubkey::from_str(s)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Invalid pubkey '{}': {}", s, e)))
}

/// Get program ID constants for Python
#[pyfunction]
pub fn get_dex_program_ids() -> PyResult<Vec<(String, String)>> {
    Ok(vec![
        ("RAYDIUM_AMM_V4".to_string(), RAYDIUM_AMM_V4.to_string()),
        ("ORCA_WHIRLPOOL".to_string(), ORCA_WHIRLPOOL.to_string()),
        ("METEORA_DLMM".to_string(), METEORA_DLMM.to_string()),
        ("TOKEN_PROGRAM".to_string(), TOKEN_PROGRAM.to_string()),
    ])
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

pub fn register_instruction_functions(m: &PyModule) -> PyResult<()> {
    // Raydium
    m.add_function(wrap_pyfunction!(build_raydium_swap_ix, m)?)?;
    m.add_function(wrap_pyfunction!(build_raydium_swap_data, m)?)?;
    
    // Orca Whirlpool
    m.add_function(wrap_pyfunction!(build_whirlpool_swap_data, m)?)?;
    m.add_function(wrap_pyfunction!(build_whirlpool_swap_ix, m)?)?;
    
    // Meteora DLMM
    m.add_function(wrap_pyfunction!(build_dlmm_swap_data, m)?)?;
    m.add_function(wrap_pyfunction!(build_dlmm_swap_ix, m)?)?;
    
    // Helpers
    m.add_function(wrap_pyfunction!(get_dex_program_ids, m)?)?;
    
    Ok(())
}
