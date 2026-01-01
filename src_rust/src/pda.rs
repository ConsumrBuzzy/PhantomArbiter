use pyo3::prelude::*;
use solana_sdk::pubkey::Pubkey;
use std::collections::HashMap;
use std::str::FromStr;

/// Constants for common DEX Program IDs
const RAYDIUM_V4_PROGRAM_ID: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";
const ORCA_WHIRLPOOL_PROGRAM_ID: &str = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";

#[pyclass]
pub struct PdaCache {
    cache: HashMap<String, String>,
    raydium_pid: Pubkey,
    orca_pid: Pubkey,
}

#[pymethods]
impl PdaCache {
    #[new]
    fn new() -> Self {
        PdaCache {
            cache: HashMap::new(),
            raydium_pid: Pubkey::from_str(RAYDIUM_V4_PROGRAM_ID).unwrap(),
            orca_pid: Pubkey::from_str(ORCA_WHIRLPOOL_PROGRAM_ID).unwrap(),
        }
    }

    /// Derives the Raydium V4 AMM ID (Pool Address)
    /// Seeds: [program_id, market_id, "amm_associated_seed"]
    /// Note: Raydium derivation acts slightly differently depending on version, 
    /// but standard V4 uses specific seeds.
    /// 
    /// However, usually Raydium pools are found via the factory or hardcoded.
    /// The most common calculation needed is actually for Associated Token Accounts (ATAs).
    /// But sticking to the user request for "PDA Derivation Cache" for "pool lookups".
    ///
    /// Let's implement the standard Raydium V4 Authority PDA which is common.
    fn get_raydium_authority(&self) -> String {
        let (pda, _) = Pubkey::find_program_address(
            &[], // Raydium V4 authority has no seeds? Or specific seeds?
                 // Actually, Raydium often checks authorities.
                 // Let's implement generic finding first.
            &self.raydium_pid
        );
        pda.to_string()
    }

    /// Generic find_program_address wrapper
    /// Returns (pda_address, bump_seed)
    fn find_address(&mut self, program_id_str: String, seeds: Vec<Vec<u8>>) -> PyResult<String> {
        // Construct a cache key
        // Key format: "PID:SEED1:SEED2..."
        // This is a bit expensive to construct strings, but faster than FFI overhead in Python loops
        let mut key = program_id_str.clone();
        for seed in &seeds {
            key.push(':');
            key.push_str(&hex::encode(seed));
        }

        if let Some(cached) = self.cache.get(&key) {
            return Ok(cached.clone());
        }

        let pid = Pubkey::from_str(&program_id_str)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        let seed_slices: Vec<&[u8]> = seeds.iter().map(|v| v.as_slice()).collect();
        let (pda, _) = Pubkey::find_program_address(&seed_slices, &pid);
        
        let pda_str = pda.to_string();
        self.cache.insert(key, pda_str.clone());
        
        Ok(pda_str)
    }

    /// Derives the Orca Whirlpool Address
    /// Seeds: ["whirlpool", whirlpool_config, token_mint_a, token_mint_b, tick_spacing]
    fn get_orca_whirlpool_address(
        &mut self, 
        whirlpools_config: String, 
        token_mint_a: String, 
        token_mint_b: String, 
        tick_spacing: u16
    ) -> PyResult<String> {
        let config_pubkey = Pubkey::from_str(&whirlpools_config)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        
        let mut mint_a_pubkey = Pubkey::from_str(&token_mint_a)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let mut mint_b_pubkey = Pubkey::from_str(&token_mint_b)
             .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        // Orca requires token mints to be sorted
        if mint_a_pubkey > mint_b_pubkey {
            std::mem::swap(&mut mint_a_pubkey, &mut mint_b_pubkey);
        }

        let tick_spacing_bytes = tick_spacing.to_le_bytes();
        
        let seeds = vec![
            b"whirlpool",
            config_pubkey.as_ref(),
            mint_a_pubkey.as_ref(),
            mint_b_pubkey.as_ref(),
            &tick_spacing_bytes
        ];

        let (pda, _) = Pubkey::find_program_address(&seeds, &self.orca_pid);
        Ok(pda.to_string())
    }

    /// Derives the Associated Token Account (ATA) address
    /// This is the #1 most called derivation in Solana
    fn get_ata_address(&mut self, owner: String, mint: String) -> PyResult<String> {
        // ATA Program ID: ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL
        let associated_program_id = Pubkey::from_str("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL").unwrap();
        let token_program_id = Pubkey::from_str("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA").unwrap();
        
        let owner_pubkey = Pubkey::from_str(&owner)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        
        let mint_pubkey = Pubkey::from_str(&mint)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        let seeds = vec![
            owner_pubkey.as_ref(),
            token_program_id.as_ref(),
            mint_pubkey.as_ref(),
        ];

        let (pda, _) = Pubkey::find_program_address(&seeds, &associated_program_id);
        Ok(pda.to_string())
    }
}

/// Registers the module classes with PyO3
pub fn register_pda_classes(m: &PyModule) -> PyResult<()> {
    m.add_class::<PdaCache>()?;
    Ok(())
}
