"""
LST De-Pegger Configuration
===========================
Config defines safe fair-value thresholds for Liquid Staked Tokens.
"""

from dataclasses import dataclass

@dataclass
class LSTConfig:
    # Thresholds for triggering a buy (negative = discount)
    depeg_threshold: float = -0.005  # -0.5% discount
    
    # Fair Value Ratios (hardcoded or fetched)
    # Ideally fetched, but hardcoded fallback for safety
    fair_value = {
        "jitoSOL": 1.072,  # Example: 1 jitoSOL = 1.072 SOL
        "mSOL": 1.145,     # Example: 1 mSOL = 1.145 SOL
    }
    
    # Trade Sizing
    max_trade_sol: float = 1.0
    
    # Slippage tolerance
    slippage_bps: int = 20  # 0.2%
    
    # Mode
    paper_mode: bool = True
