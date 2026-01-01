use pyo3::prelude::*;
use base64::{Engine as _, engine::general_purpose};
// use borsh::{BorshDeserialize};

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

// ============================================================================
// WHIFF DETECTION (Asymmetric Intelligence)
// ============================================================================
// Detects "leading indicators" before price impact:
// - Whale CCTP/Wormhole mints
// - Lending protocol liquidations
// - High-value transfers

/// WhiffEvent types
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum WhiffType {
    WhaleMint,      // Large CCTP/Wormhole mint
    Liquidation,    // Lending protocol liquidation
    LargeTransfer,  // Significant token movement
    FailedSwap,     // Slippage failure detected
}

impl WhiffType {
    pub fn as_str(&self) -> &'static str {
        match self {
            WhiffType::WhaleMint => "WHALE_MINT",
            WhiffType::Liquidation => "LIQUIDATION",
            WhiffType::LargeTransfer => "LARGE_TRANSFER",
            WhiffType::FailedSwap => "FAILED_SWAP",
        }
    }
}

/// Whiff event for asymmetric intelligence
#[pyclass]
#[derive(Clone)]
pub struct WhiffEvent {
    #[pyo3(get)]
    pub whiff_type: String,
    #[pyo3(get)]
    pub mint: String,
    #[pyo3(get)]
    pub amount: u64,
    #[pyo3(get)]
    pub confidence: f32,
    #[pyo3(get)]
    pub direction: String,  // "BULLISH", "BEARISH", "VOLATILE"
    #[pyo3(get)]
    pub source: String,
}

// Known program IDs for whiff detection
const CCTP_PROGRAM: &str = "CCTPmbSD7gX1bxKPAmg77w8oFzNFpaQiQUWD43TKaecd";
const WORMHOLE_PROGRAM: &str = "worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth";
const SOLEND_PROGRAM: &str = "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo";
const KAMINO_PROGRAM: &str = "KLend2g3cP87fffoy8q1mQqGKjrxjC8boQo7AQnufHj";
const MARGINFI_PROGRAM: &str = "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA";

/// Parse logs for "whiff" signals (asymmetric intelligence)
#[pyfunction]
pub fn parse_whiff_log(log_str: String, program_id: String) -> PyResult<Option<WhiffEvent>> {
    // 1. Whale CCTP/Wormhole Mint Detection
    if program_id == CCTP_PROGRAM || program_id == WORMHOLE_PROGRAM {
        if log_str.contains("MintTo") || log_str.contains("mintTo") || log_str.contains("Mint") {
            // Extract amount if possible (placeholder logic)
            let amount = extract_amount_from_log(&log_str).unwrap_or(0);
            
            // Only care about $100k+ inflows (assuming 6 decimals for USDC)
            if amount >= 100_000_000_000 {  // 100k USDC in raw units
                let source = if program_id == CCTP_PROGRAM { "CCTP" } else { "WORMHOLE" };
                return Ok(Some(WhiffEvent {
                    whiff_type: WhiffType::WhaleMint.as_str().to_string(),
                    mint: "USDC".to_string(),  // Assume USDC for cross-chain
                    amount,
                    confidence: 0.80,
                    direction: "BULLISH".to_string(),
                    source: source.to_string(),
                }));
            }
        }
    }
    
    // 2. Lending Protocol Liquidation Detection
    if program_id == SOLEND_PROGRAM || program_id == KAMINO_PROGRAM || program_id == MARGINFI_PROGRAM {
        if log_str.to_lowercase().contains("liquidat") {
            let source = match program_id.as_str() {
                SOLEND_PROGRAM => "SOLEND",
                KAMINO_PROGRAM => "KAMINO",
                MARGINFI_PROGRAM => "MARGINFI",
                _ => "LENDING",
            };
            
            return Ok(Some(WhiffEvent {
                whiff_type: WhiffType::Liquidation.as_str().to_string(),
                mint: "UNKNOWN".to_string(),  // Would parse from logs
                amount: 0,
                confidence: 0.85,
                direction: "BEARISH".to_string(),
                source: source.to_string(),
            }));
        }
    }
    
    // 3. Failed Swap Detection (slippage wars)
    if log_str.contains("Program failed") || log_str.contains("Slippage") || log_str.contains("InsufficientFunds") {
        return Ok(Some(WhiffEvent {
            whiff_type: WhiffType::FailedSwap.as_str().to_string(),
            mint: "UNKNOWN".to_string(),
            amount: 0,
            confidence: 0.70,
            direction: "VOLATILE".to_string(),
            source: "FAILED_TX".to_string(),
        }));
    }
    
    Ok(None)
}

/// Extract amount from log string (basic pattern matching)
fn extract_amount_from_log(log_str: &str) -> Option<u64> {
    // Look for patterns like "amount: 123456" or "amount=123456"
    if let Some(pos) = log_str.find("amount") {
        let after = &log_str[pos..];
        // Find digits after ": " or "="
        let start = after.find(|c: char| c.is_ascii_digit())?;
        let digits: String = after[start..].chars().take_while(|c| c.is_ascii_digit()).collect();
        return digits.parse().ok();
    }
    None
}

/// Batch parse multiple logs for whiffs (reduces FFI overhead)
#[pyfunction]
pub fn parse_whiff_logs_batch(
    logs: Vec<String>,
    program_id: String,
) -> PyResult<Vec<WhiffEvent>> {
    let mut results = Vec::new();
    
    for log in logs {
        if let Ok(Some(whiff)) = parse_whiff_log(log, program_id.clone()) {
            results.push(whiff);
        }
    }
    
    Ok(results)
}
