
from dataclasses import dataclass

@dataclass
class ScorerConfig:
    """
    Configuration for Scorer/Slippage Calibrator.
    Fallback for when phantom_core Rust extension is not available.
    """
    min_profit_usd: float
    max_slippage_bps: int
    gas_fee_usd: float
    jito_tip_usd: float
    dex_fee_bps: int
    default_trade_size_usd: float
