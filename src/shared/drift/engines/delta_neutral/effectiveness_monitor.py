"""
Effectiveness Monitor
====================

Component for monitoring hedge effectiveness and performance.
Cohesive with delta-neutral hedging logic.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from ...sdk.models.portfolio import PortfolioState
from ...sdk.models.trading import TradeResult
from ...sdk.data.portfolio_data_provider import PortfolioDataProvider
from ...sdk.math.performance_calculator import PerformanceCalculator
from ...sdk.math.correlation_calculator import CorrelationCalculator
from src.shared.system.logging import Logger


class EffectivenessLevel(Enum):
    """Hedge effectiveness levels."""
    EXCELLENT = "excellent"  # >90% effectiveness
    GOOD = "good"           # 70-90% effectiveness
    FAIR = "fair"           # 50-70% effectiveness
    POOR = "poor"           # <50% effectiveness


@dataclass
class HedgeEffectivenessResult:
    """Hedge effectiveness monitoring result."""
    current_delta: float
    target_delta: float
    delta_drift: float
    hedge_effectiveness: float  # 0.0 to 1.0
    effectiveness_level: EffectivenessLevel
    correlation_stability: float
    time_since_last_hedge: timedelta
    next_hedge_recommendation: Optional[datetime]
    monitoring_alerts: List[str]
    calculation_time: datetime
    
    # Performance metrics
    hedge_pnl_contribution: float
    hedge_cost_efficiency: float
    delta_tracking_error: float
    
    # Detailed analysis
    hedge_performance_history: List[Dict[str, Any]]
    correlation_breakdown: Dict[str, float]


class EffectivenessMonitor:
    """
    Hedge effectiveness monitoring comp