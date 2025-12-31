from dataclasses import dataclass


@dataclass
class RiskConfig:
    # Capital Management
    total_budget_usd: float = 500.0
    max_trade_size_usd: float = 100.0
    cash_reserve_usd: float = 10.0

    # Circuit Breakers
    stop_loss_pct: float = -0.05
    take_profit_pct: float = 0.04
    max_daily_drawdown_pct: float = 0.10

    # Position Limits
    max_concurrent_positions: int = 5
    max_hold_time_minutes: int = 15

    # Slippage
    base_slippage_bps: int = 50
    max_slippage_bps: int = 500
    mev_protection_enabled: bool = True
