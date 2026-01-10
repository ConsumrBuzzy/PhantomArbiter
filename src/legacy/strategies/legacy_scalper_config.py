"""
PhantomScalper - Meme Token Scalper
===================================
V131: Refactored from DataBroker. Supports multiple strategies.

Usage:
    python main.py scalper --live --strategy longtail --duration 60
"""

from dataclasses import dataclass, field
from typing import List, Type
from enum import Enum


class ScalperStrategy(Enum):
    """Available scalping strategies."""

    LONGTAIL = "longtail"  # MACD crossover (trend following)
    VWAP = "vwap"  # VWAP reversion
    KELTNER = "keltner"  # Keltner channel breakouts
    ENSEMBLE = "ensemble"  # All strategies combined (legacy DataBroker mode)


@dataclass
class ScalperConfig:
    """Configuration for the Scalper engine."""

    # Trading Mode
    live_mode: bool = False

    # Strategy Selection
    strategy: ScalperStrategy = ScalperStrategy.LONGTAIL

    # Capital Settings
    budget: float = 100.0  # Starting budget in USD
    max_position_size: float = 50.0  # Max per trade
    max_positions: int = 3  # Max concurrent positions

    # Risk Settings
    stop_loss_pct: float = 5.0  # Stop loss percentage
    take_profit_pct: float = 10.0  # Take profit percentage

    # Watchlist (tokens to scan)
    watchlist: List[str] = field(default_factory=list)

    # Timing
    scan_interval: float = 2.0  # Seconds between scans

    @classmethod
    def from_args(cls, args) -> "ScalperConfig":
        """Create config from CLI arguments."""
        strategy_map = {
            "longtail": ScalperStrategy.LONGTAIL,
            "vwap": ScalperStrategy.VWAP,
            "keltner": ScalperStrategy.KELTNER,
            "ensemble": ScalperStrategy.ENSEMBLE,
        }

        return cls(
            live_mode=getattr(args, "live", False),
            strategy=strategy_map.get(
                getattr(args, "strategy", "longtail"), ScalperStrategy.LONGTAIL
            ),
            budget=getattr(args, "budget", 100.0),
            max_position_size=getattr(args, "max_trade", 50.0),
        )


def get_strategy_class(strategy: ScalperStrategy) -> Type:
    """Get the strategy class for the given strategy enum."""
    from src.strategies.logic.longtail_logic import LongtailLogic
    from src.strategies.logic.vwap_logic import VwapLogic
    from src.strategies.logic.keltner_logic import KeltnerLogic
    from src.strategies.logic.ensemble import MerchantEnsemble

    strategy_map = {
        ScalperStrategy.LONGTAIL: LongtailLogic,
        ScalperStrategy.VWAP: VwapLogic,
        ScalperStrategy.KELTNER: KeltnerLogic,
        ScalperStrategy.ENSEMBLE: MerchantEnsemble,
    }

    return strategy_map.get(strategy, LongtailLogic)
