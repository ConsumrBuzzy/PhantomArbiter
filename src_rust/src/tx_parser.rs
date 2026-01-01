// ------------------------------------------------------------------------
// TX PARSER (V42: Helius Enhanced Transaction Parsing)
// Fast Rust parsing of Helius enhanced transaction responses
// ------------------------------------------------------------------------

use pyo3::prelude::*;
use serde::Deserialize;

/// Represents a token transfer extracted from a transaction
#[pyclass]
#[derive(Clone, Debug)]
pub struct TokenTransfer {
    #[pyo3(get)]
    pub mint: String,
    #[pyo3(get)]
    pub symbol: Option<String>,
    #[pyo3(get)]
    pub amount: f64,
    #[pyo3(get)]
    pub from_account: Option<String>,
    #[pyo3(get)]
    pub to_account: Option<String>,
    #[pyo3(get)]
    pub is_native: bool,
}

#[pymethods]
impl TokenTransfer {
    fn __repr__(&self) -> String {
        format!(
            "TokenTransfer(mint={}, symbol={:?}, amount={})",
            &self.mint[..8.min(self.mint.len())],
            self.symbol,
            self.amount
        )
    }
}

/// Parsed transaction result
#[pyclass]
#[derive(Clone, Debug)]
pub struct ParsedTx {
    #[pyo3(get)]
    pub signature: String,
    #[pyo3(get)]
    pub tx_type: String,  // "SWAP", "TRANSFER", "UNKNOWN"
    #[pyo3(get)]
    pub source: String,   // "RAYDIUM", "ORCA", "JUPITER", "UNKNOWN"
    #[pyo3(get)]
    pub token_transfers: Vec<TokenTransfer>,
    #[pyo3(get)]
    pub fee_payer: Option<String>,
    #[pyo3(get)]
    pub slot: u64,
}

#[pymethods]
impl ParsedTx {
    /// Get the primary token (non-USDC) from the swap
    fn get_primary_token(&self) -> Option<TokenTransfer> {
        const USDC_MINT: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
        const USDT_MINT: &str = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB";
        const SOL_MINT: &str = "So11111111111111111111111111111111111111112";
        
        // Find the non-stablecoin token
        for transfer in &self.token_transfers {
            if transfer.mint != USDC_MINT && transfer.mint != USDT_MINT {
                return Some(transfer.clone());
            }
        }
        
        // If all are stablecoins/SOL, return SOL if present
        for transfer in &self.token_transfers {
            if transfer.mint == SOL_MINT {
                return Some(transfer.clone());
            }
        }
        
        self.token_transfers.first().cloned()
    }
}

// Serde structs for Helius response parsing
#[derive(Deserialize, Debug)]
struct HeliusTx {
    signature: Option<String>,
    #[serde(rename = "type")]
    tx_type: Option<String>,
    source: Option<String>,
    #[serde(rename = "tokenTransfers")]
    token_transfers: Option<Vec<HeliusTokenTransfer>>,
    #[serde(rename = "nativeTransfers")]
    native_transfers: Option<Vec<HeliusNativeTransfer>>,
    #[serde(rename = "feePayer")]
    fee_payer: Option<String>,
    slot: Option<u64>,
}

#[derive(Deserialize, Debug)]
struct HeliusTokenTransfer {
    mint: Option<String>,
    #[serde(rename = "tokenAmount")]
    token_amount: Option<f64>,
    #[serde(rename = "fromUserAccount")]
    from_user_account: Option<String>,
    #[serde(rename = "toUserAccount")]
    to_user_account: Option<String>,
}

#[derive(Deserialize, Debug)]
struct HeliusNativeTransfer {
    amount: Option<u64>,
    #[serde(rename = "fromUserAccount")]
    from_user_account: Option<String>,
    #[serde(rename = "toUserAccount")]
    to_user_account: Option<String>,
}

/// Parse a Helius enhanced transaction response (JSON string)
/// Returns a ParsedTx with extracted token transfers
#[pyfunction]
pub fn parse_helius_tx(json_str: &str) -> PyResult<Option<ParsedTx>> {
    // Try to parse as single tx or array
    let txs: Vec<HeliusTx> = match serde_json::from_str::<Vec<HeliusTx>>(json_str) {
        Ok(arr) => arr,
        Err(_) => {
            // Try single object
            match serde_json::from_str::<HeliusTx>(json_str) {
                Ok(tx) => vec![tx],
                Err(e) => {
                    return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                        format!("Failed to parse Helius response: {}", e)
                    ));
                }
            }
        }
    };
    
    if txs.is_empty() {
        return Ok(None);
    }
    
    let tx = &txs[0];
    
    // Extract token transfers
    let mut transfers: Vec<TokenTransfer> = Vec::new();
    
    if let Some(token_xfers) = &tx.token_transfers {
        for xfer in token_xfers {
            if let Some(mint) = &xfer.mint {
                transfers.push(TokenTransfer {
                    mint: mint.clone(),
                    symbol: None,  // Helius doesn't always include this
                    amount: xfer.token_amount.unwrap_or(0.0),
                    from_account: xfer.from_user_account.clone(),
                    to_account: xfer.to_user_account.clone(),
                    is_native: false,
                });
            }
        }
    }
    
    // Check for native SOL transfers
    if let Some(native_xfers) = &tx.native_transfers {
        for xfer in native_xfers {
            if let Some(amount) = xfer.amount {
                if amount > 0 {
                    transfers.push(TokenTransfer {
                        mint: "So11111111111111111111111111111111111111112".to_string(),
                        symbol: Some("SOL".to_string()),
                        amount: amount as f64 / 1_000_000_000.0,  // Convert lamports to SOL
                        from_account: xfer.from_user_account.clone(),
                        to_account: xfer.to_user_account.clone(),
                        is_native: true,
                    });
                }
            }
        }
    }
    
    // Determine source (DEX)
    let source = tx.source.clone().unwrap_or_else(|| "UNKNOWN".to_string());
    
    Ok(Some(ParsedTx {
        signature: tx.signature.clone().unwrap_or_default(),
        tx_type: tx.tx_type.clone().unwrap_or_else(|| "UNKNOWN".to_string()),
        source,
        token_transfers: transfers,
        fee_payer: tx.fee_payer.clone(),
        slot: tx.slot.unwrap_or(0),
    }))
}

/// Parse multiple Helius transactions at once (batch processing)
#[pyfunction]
pub fn parse_helius_tx_batch(json_str: &str) -> PyResult<Vec<ParsedTx>> {
    let txs: Vec<HeliusTx> = serde_json::from_str(json_str)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    
    let mut results = Vec::with_capacity(txs.len());
    
    for tx in txs {
        let mut transfers: Vec<TokenTransfer> = Vec::new();
        
        if let Some(token_xfers) = &tx.token_transfers {
            for xfer in token_xfers {
                if let Some(mint) = &xfer.mint {
                    transfers.push(TokenTransfer {
                        mint: mint.clone(),
                        symbol: None,
                        amount: xfer.token_amount.unwrap_or(0.0),
                        from_account: xfer.from_user_account.clone(),
                        to_account: xfer.to_user_account.clone(),
                        is_native: false,
                    });
                }
            }
        }
        
        if let Some(native_xfers) = &tx.native_transfers {
            for xfer in native_xfers {
                if let Some(amount) = xfer.amount {
                    if amount > 0 {
                        transfers.push(TokenTransfer {
                            mint: "So11111111111111111111111111111111111111112".to_string(),
                            symbol: Some("SOL".to_string()),
                            amount: amount as f64 / 1_000_000_000.0,
                            from_account: xfer.from_user_account.clone(),
                            to_account: xfer.to_user_account.clone(),
                            is_native: true,
                        });
                    }
                }
            }
        }
        
        results.push(ParsedTx {
            signature: tx.signature.unwrap_or_default(),
            tx_type: tx.tx_type.unwrap_or_else(|| "UNKNOWN".to_string()),
            source: tx.source.unwrap_or_else(|| "UNKNOWN".to_string()),
            token_transfers: transfers,
            fee_payer: tx.fee_payer,
            slot: tx.slot.unwrap_or(0),
        });
    }
    
    Ok(results)
}

/// Extract the primary token mint from a Helius response (fast path)
/// Returns (mint, symbol, amount_usd) or None
#[pyfunction]
pub fn extract_swap_token(json_str: &str) -> PyResult<Option<(String, Option<String>, f64)>> {
    const USDC_MINT: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";
    
    let parsed = parse_helius_tx(json_str)?;
    
    if let Some(tx) = parsed {
        if let Some(primary) = tx.get_primary_token() {
            // Find USDC transfer to get USD value
            let usdc_amount = tx.token_transfers.iter()
                .find(|t| t.mint == USDC_MINT)
                .map(|t| t.amount)
                .unwrap_or(0.0);
            
            return Ok(Some((primary.mint, primary.symbol, usdc_amount)));
        }
    }
    
    Ok(None)
}

// Module registration
pub fn register_tx_parser_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<TokenTransfer>()?;
    m.add_class::<ParsedTx>()?;
    m.add_function(wrap_pyfunction!(parse_helius_tx, m)?)?;
    m.add_function(wrap_pyfunction!(parse_helius_tx_batch, m)?)?;
    m.add_function(wrap_pyfunction!(extract_swap_token, m)?)?;
    Ok(())
}
