from dataclasses import dataclass

@dataclass
class StrategyConfig:
    # Arbitrage Thresholds
    min_spread_pct: float = 0.3
    min_profit_after_fees_usd: float = 0.25
    
    # Scalper Thresholds
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    min_confidence: float = 0.75
    
    # Rotation
    pod_rotation_interval_sec: int = 30
