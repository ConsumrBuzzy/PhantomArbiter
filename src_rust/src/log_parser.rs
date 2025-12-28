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

// Anchor Event Discriminators (calculated via sha256("event:<Name>")[..8])
const DISC_SWAP: [u8; 8] = [81, 108, 227, 190, 205, 208, 10, 196];       // "Swap" (Meteora?)
const DISC_TRADE: [u8; 8] = [24, 254, 218, 152, 253, 43, 18, 81];        // "Trade" (Orca?)
const DISC_SWAP_EVENT: [u8; 8] = [64, 198, 205, 232, 38, 8, 113, 226];   // "SwapEvent" (Generic)

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
            
            let disc: [u8; 8] = data[0..8].try_into().unwrap();
            
            if disc == DISC_SWAP {
                 // Meteora DLMM "Swap" (Hypothesis)
                 // Layout: [8 disc] + [32 lbPair] + [32 userX] + [32 userY] + [32 resX] + [32 resY] + [8 amtIn] + [8 amtInUi] ...
                 // AmtIn Offset = 8 + 32*5 = 168? That's deep.
                 // Let's safe-guess for now or correct in V2. 
                 // Actually, let's just Log it for calibration first.
                 // println!("[Rust] Caught Meteora Swap!");
            } else if disc == DISC_TRADE {
                 // Orca "Trade"
                 // println!("[Rust] Caught Orca Trade!");
            } else if disc == DISC_SWAP_EVENT {
                 // Generic
            } else {
                 // Unknown - Print for Debugging
                 // println!("[Rust] Unknown Anchor Event: {:?}", disc);
            }
        }
    }

    Ok(None)
}
