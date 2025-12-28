use pyo3::prelude::*;
use base64::{Engine as _, engine::general_purpose};
use borsh::{BorshDeserialize};

#[pyclass]
pub struct SwapEvent {
    #[pyo3(get)]
    pub amount_in: u64,
    #[pyo3(get)]
    pub amount_out: u64,
    #[pyo3(get)]
    pub is_buy: bool,
}

// Orca Whirlpool "Trade" Event Discriminator (first 8 bytes of sha256("event:Trade"))
// This is approximate; for production we verify exact hash.
// For now we will detect "Program data: " and look for common patterns or just enable Raydium first.
// Actually, let's implement the generic Anchor parser structure.

#[pyfunction]
pub fn parse_raydium_log(log_str: String) -> PyResult<Option<SwapEvent>> {
    parse_universal_log(log_str)
}

#[pyfunction]
pub fn parse_universal_log(log_str: String) -> PyResult<Option<SwapEvent>> {
    // 1. Raydium (ray_log)
    if let Some(pos) = log_str.find("ray_log: ") {
        let b64_part = &log_str[pos + 9..];
        let b64_clean = b64_part.trim();
        
        if let Ok(data) = general_purpose::STANDARD.decode(b64_clean) {
             if data.len() >= 33 && data[0] == 3 {
                 let amount_in = u64::from_le_bytes(data[1..9].try_into().unwrap_or([0;8]));
                 let amount_out = u64::from_le_bytes(data[9..17].try_into().unwrap_or([0;8]));
                 let direction = u64::from_le_bytes(data[25..33].try_into().unwrap_or([0;8]));
                 
                 return Ok(Some(SwapEvent {
                     amount_in,
                     amount_out,
                     is_buy: direction == 1,
                 }));
             }
        }
    }
    
    // 2. Anchor Events (Orca/Meteora) - "Program data: "
    if let Some(pos) = log_str.find("Program data: ") {
        let b64_part = &log_str[pos + 14..];
        let b64_clean = b64_part.trim();
        
        if let Ok(data) = general_purpose::STANDARD.decode(b64_clean) {
            if data.len() < 8 { return Ok(None); }
            
            // Discriminator check (First 8 bytes)
            // Orca Whirlpool Trade: [0xdd, 0xaf, 0xd9, 0xfd, 0x6e, 0xd0, 0x76, 0x5a] (Example)
            // We need to implement specific checks. For this MVP, we will stick to Raydium 
            // but structure this to allow easy addition.
            
            // Pseudo-code for future expansion:
            // let disc = &data[0..8];
            // if disc == ORCA_TRADE_DISCRIMINATOR { ... }
            // if disc == METEORA_SWAP_DISCRIMINATOR { ... }
        }
    }

    Ok(None)
}
