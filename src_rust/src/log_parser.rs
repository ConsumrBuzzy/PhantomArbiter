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

#[pyfunction]
pub fn parse_raydium_log(log_str: String) -> PyResult<Option<SwapEvent>> {
    // Expected format: "Program log: ray_log: <BASE64>"
    let marker = "ray_log: ";
    if let Some(pos) = log_str.find(marker) {
        let b64_part = &log_str[pos + marker.len()..];
        // Clean trailing chars just in case (e.g. coloring codes or newlines)
        let b64_clean = b64_part.trim();
        
        if let Ok(data) = general_purpose::STANDARD.decode(b64_clean) {
             // Raydium Log Layout:
             // [0]: u8 (Log Type, 3 = Swap)
             // [1..9]: u64 (Amount In)
             // [9..17]: u64 (Amount Out)
             // [17..25]: u64 (Min Out)
             // [25..33]: u64 (Direction)
             
             if data.len() >= 33 {
                 let log_type = data[0];
                 if log_type == 3 { // Swap Log
                     let start = 1;
                     // Helper for reading le_bytes
                     let read_u64 = |offset: usize| -> u64 {
                         let slice: [u8; 8] = data[offset..offset+8].try_into().unwrap_or([0;8]);
                         u64::from_le_bytes(slice)
                     };

                     let amount_in = read_u64(start);
                     let amount_out = read_u64(start + 8);
                     let _min_out = read_u64(start + 16);
                     let direction = read_u64(start + 24); 
                     
                     // Direction: 1 = Buy (Quote -> Base), 2 = Sell? 
                     // Need to calibrate direction mapping.
                     // Usually 0 or 1. Let's assume 1 is Buy for now.
                     
                     return Ok(Some(SwapEvent {
                         amount_in,
                         amount_out,
                         is_buy: direction == 1,
                     }));
                 }
             }
        }
    }
    Ok(None)
}
