"""
DriftSDK - Shared Foundation for Trading Engines
==============================================

Provides shared mathematical libraries, data models, and utilities
for all Drift Protocol trading engines and strategies.

Components:
- math: Mathematical calculations (VaR, correlation, volatility)
- models: Shared data models and validation
- data: Market data abstractions and providers
- utils: Common utilities and helpers
"""

from .math import VaRCalculator, CorrelationCalculator, VolatilityCalculator
from .models import PortfolioState, RiskMetrics, TradeSignal, Position, MarketSummary
from .data import MarketDataProvider, RiskDataProvider

__all__ = [
    # Mathematical libraries
    'VaRCalculator',
    'CorrelationCalculator', 
    'VolatilityCalculator',
    
    # Data models
    'PortfolioState',
    'RiskMetrics',
    'TradeSignal',
    'Position',
    'MarketSummary',
    
    # Data providers
    'MarketDataProvider',
    'RiskDataProvider',
]

__version__ = "1.0.0"