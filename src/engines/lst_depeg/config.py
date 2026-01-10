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
    
    # Fair Value Ratios (LST/SOL)
    # Ideally should be dynamic based on stake pool state
    fair_value = {
        "jitoSOL": 1.072,
        "mSOL": 1.145,
    }
    
    # Token Mints
    MINTS = {
        "jitoSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
        "mSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
        "SOL": "So11111111111111111111111111111111111111112"
    }
    
    # Trade Sizing
    max_trade_sol: float = 1.0
    
    # Slippage tolerance
    slippage_bps: int = 20  # 0.2%
    
    # Mode
    paper_mode: bool = True
