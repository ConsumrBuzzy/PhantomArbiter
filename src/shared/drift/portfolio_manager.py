"""
Drift Portfolio Manager
======================

Central orchestrator for portfolio operations, risk management, and analytics.
Provides comprehensive portfolio management capabilities for Drift Protocol.

Features:
- Portfolio analytics and summaries
- Position breakdown and analysis
- Risk calculations and monitoring
- Automated hedging and rebalancing
- Risk limit enforcement
- Integration with enhanced trading and market data managers

Usage:
    portfolio_manager = DriftPortfolioManager(drift_adapter)
    
    # Get portfolio summary
    summary = await portfolio_manager.get_portfolio_summary()
    
    # Calculate risk metrics
    risk = await portfolio_manager.calculate_portfolio_risk()
    
    # Auto-hedge portfolio
    trades = await portfolio_manager.auto_hedge_portfolio(target_delta=0.0)
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal

from src.shared.system.logging import Logger
from src.shared.drift.client_manager import DriftClientManager
from src.shared.drift.trading_manager import DriftTradingManager
from src.shared.drift.market_data_manager import DriftMarketDataManager


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PortfolioSummary:
    """Complete portfolio summary with all key metrics."""
    total_value: float
    unrealized_pnl: float
    realized_pnl: float
    margin_used: float
    margin_available: float
    leverage: float
    health_ratio: float
    positions: List[Dict[str, Any]]
    open_orders: List[Dict[str, Any]]
    last_updated: datetime

@dataclass
class PositionAnalysis:
    """Detailed analysis of individual position."""
    market: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    risk_contribution: float
    volatility: float
    beta: float
    correlation_to_portfolio: float
    liquidation_price: float
    margin_requirement: float

@dataclass
class RiskLimits:
    """Configurable risk limits for portfolio management."""
    max_portfolio_leverage: float = 5.0
    max_position_size_usd: float = 50000.0
    max_position_size_percent: float = 0.3  # 30% of portfolio
    max_correlation_exposure: float = 0.7
    max_var_1d_percent: float = 0.05  # 5% of portfolio
    min_health_ratio: float = 150.0
    max_drawdown_percent: float = 0.15  # 15% max drawdown

@dataclass
class RiskViolation:
    """Risk limit violation details."""
    limit_type: str
    current_value: float
    limit_value: float
    severity: str  # "warning", "critical"
    message: str
    recommended_action: str

@dataclass
class PositionSizing:
    """Position sizing recommendation."""
    market: str
    recommended_size: float
    max_size: float
    risk_adjusted_size: float
    reasoning: str
    confidence: float


# =============================================================================
# PORTFOLIO MANAGER
# =============================================================================

class DriftPortfolioManager:
    """
    Central portfolio management system for Drift Protocol.
    
    Coordinates all portfolio operations including analytics, risk management,
    hedging, and rebalancing through integration with Phase 1 components.
    """
    
    def __init__(
        self,
        drift_adapter,
        trading_manager: Optional[DriftTradingManager] = None,
        market_data_manager: Optional[DriftMarketDataManager] = None,
        risk_limits: Optional[RiskLimits] = None
    ):
        """
        Initialize portfolio manager.
        
        Args:
            drift_adapter: Existing DriftAdapter instance
            trading_manager: Enhanced trading manager (optional)
            market_data_manager: Enhanced market data manager (optional)
            risk_limits: Risk limits configuration (optional)
        """
        self.drift_adapter = drift_adapter
        self.logger = Logger("DriftPortfolioManager")
        
        # Initialize or use provided managers
        self.trading_manager = trading_manager or DriftTradingManager(drift_adapter)
        self.market_data_manager = market_data_manager or DriftMarketDataManager(drift_adapter)
        
        # Risk management
        self.risk_limits = risk_limits or RiskLimits()
        
        # Cache for performance
        self._portfolio_cache = {}
        self._cache_ttl = 30  # 30 seconds
        self._last_cache_update = 0
        
        self.logger.info("Portfolio Manager initialized")

    # =========================================================================
    # PORTFOLIO ANALYTICS
    # =========================================================================

    async def get_portfolio_summary(self) -> PortfolioSummary:
        """
        Get comprehensive portfolio summary.
        
        Returns:
            PortfolioSummary with all key metrics
        """
        try:
            # Check cache first
            if self._is_cache_valid("portfolio_summary"):
                return self._portfolio_cache["portfolio_summary"]
            
            # Get account data
            account = await self.drift_adapter.get_user_account()
            if not account:
                raise ValueError("Could not retrieve user account")
            
            # Get positions
            positions = await self.drift_adapter.get_positions()
            
            # Get open orders
            open_orders = await self.drift_adapter.get_open_orders()
            
            # Calculate metrics
            total_value = float(account.get('total_collateral', 0))
            unrealized_pnl = float(account.get('unrealized_pnl', 0))
            realized_pnl = 0.0  # TODO: Calculate from trade history
            margin_used = float(account.get('total_position_value', 0))
            margin_available = total_value - margin_used
            leverage = margin_used / total_value if total_value > 0 else 0.0
            health_ratio = float(account.get('health', 100))
            
            summary = PortfolioSummary(
                total_value=total_value,
                unrealized_pnl=unrealized_pnl,
                realized_pnl=realized_pnl,
                margin_used=margin_used,
                margin_available=margin_available,
                leverage=leverage,
                health_ratio=health_ratio,
                positions=positions or [],
                open_orders=open_orders or [],
                last_updated=datetime.now()
            )
            
            # Cache result
            self._portfolio_cache["portfolio_summary"] = summary
            self._last_cache_update = time.time()
            
            self.logger.info(f"Portfolio summary: ${total_value:.2f} total, {leverage:.2f}x leverage")
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio summary: {e}")
            raise

    async def get_position_breakdown(self) -> List[PositionAnalysis]:
        """
        Get detailed analysis of all positions.
        
        Returns:
            List of PositionAnalysis objects
        """
        try:
            positions = await self.drift_adapter.get_positions()
            if not positions:
                return []
            
            analyses = []
            
            for position in positions:
                market = position.get('market', 'UNKNOWN')
                size = float(position.get('base_asset_amount', 0))
                
                if size == 0:
                    continue
                
                # Get current market price
                market_data = await self.market_data_manager.get_market_summary(market)
                current_price = float(market_data.get('mark_price', 0)) if market_data else 0.0
                
                # Calculate metrics
                entry_price = float(position.get('quote_entry_amount', 0)) / size if size != 0 else 0.0
                unrealized_pnl = float(position.get('unrealized_pnl', 0))
                
                # TODO: Implement advanced risk metrics
                risk_contribution = 0.0
                volatility = 0.0
                beta = 0.0
                correlation_to_portfolio = 0.0
                liquidation_price = 0.0
                margin_requirement = float(position.get('quote_asset_amount', 0))
                
                analysis = PositionAnalysis(
                    market=market,
                    size=size,
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=0.0,  # TODO: Calculate from trade history
                    total_pnl=unrealized_pnl,
                    risk_contribution=risk_contribution,
                    volatility=volatility,
                    beta=beta,
                    correlation_to_portfolio=correlation_to_portfolio,
                    liquidation_price=liquidation_price,
                    margin_requirement=margin_requirement
                )
                
                analyses.append(analysis)
            
            self.logger.info(f"Analyzed {len(analyses)} positions")
            return analyses
            
        except Exception as e:
            self.logger.error(f"Error getting position breakdown: {e}")
            raise

    # =========================================================================
    # RISK MANAGEMENT
    # =========================================================================

    async def set_risk_limits(self, limits: RiskLimits) -> bool:
        """
        Set risk limits for portfolio management.
        
        Args:
            limits: RiskLimits configuration
            
        Returns:
            True if limits were set successfully
        """
        try:
            self.risk_limits = limits
            self.logger.info(f"Risk limits updated: max leverage {limits.max_portfolio_leverage}x")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting risk limits: {e}")
            return False

    async def check_risk_limits(self) -> List[RiskViolation]:
        """
        Check current portfolio against risk limits.
        
        Returns:
            List of risk violations
        """
        try:
            violations = []
            
            # Get current portfolio state
            summary = await self.get_portfolio_summary()
            
            # Check leverage limit
            if summary.leverage > self.risk_limits.max_portfolio_leverage:
                violations.append(RiskViolation(
                    limit_type="leverage",
                    current_value=summary.leverage,
                    limit_value=self.risk_limits.max_portfolio_leverage,
                    severity="critical" if summary.leverage > self.risk_limits.max_portfolio_leverage * 1.2 else "warning",
                    message=f"Portfolio leverage {summary.leverage:.2f}x exceeds limit {self.risk_limits.max_portfolio_leverage:.2f}x",
                    recommended_action="Reduce position sizes or add margin"
                ))
            
            # Check health ratio
            if summary.health_ratio < self.risk_limits.min_health_ratio:
                violations.append(RiskViolation(
                    limit_type="health_ratio",
                    current_value=summary.health_ratio,
                    limit_value=self.risk_limits.min_health_ratio,
                    severity="critical" if summary.health_ratio < 110 else "warning",
                    message=f"Health ratio {summary.health_ratio:.1f} below minimum {self.risk_limits.min_health_ratio:.1f}",
                    recommended_action="Close positions or add collateral"
                ))
            
            # Check position size limits
            positions = await self.get_position_breakdown()
            for position in positions:
                position_value = abs(position.size * position.current_price)
                
                # Check absolute position size
                if position_value > self.risk_limits.max_position_size_usd:
                    violations.append(RiskViolation(
                        limit_type="position_size_usd",
                        current_value=position_value,
                        limit_value=self.risk_limits.max_position_size_usd,
                        severity="warning",
                        message=f"{position.market} position ${position_value:.0f} exceeds limit ${self.risk_limits.max_position_size_usd:.0f}",
                        recommended_action=f"Reduce {position.market} position size"
                    ))
                
                # Check percentage position size
                position_percent = position_value / summary.total_value if summary.total_value > 0 else 0
                if position_percent > self.risk_limits.max_position_size_percent:
                    violations.append(RiskViolation(
                        limit_type="position_size_percent",
                        current_value=position_percent,
                        limit_value=self.risk_limits.max_position_size_percent,
                        severity="warning",
                        message=f"{position.market} position {position_percent:.1%} exceeds limit {self.risk_limits.max_position_size_percent:.1%}",
                        recommended_action=f"Reduce {position.market} position size"
                    ))
            
            if violations:
                self.logger.warning(f"Found {len(violations)} risk violations")
            
            return violations
            
        except Exception as e:
            self.logger.error(f"Error checking risk limits: {e}")
            return []

    # =========================================================================
    # BASIC HEDGING (Advanced hedging in separate engine)
    # =========================================================================

    async def auto_hedge_portfolio(self, target_delta: float = 0.0) -> List[str]:
        """
        Basic portfolio hedging functionality.
        
        Args:
            target_delta: Target portfolio delta (default: 0.0 for delta-neutral)
            
        Returns:
            List of order IDs for hedge trades
        """
        try:
            # Get current positions
            positions = await self.get_position_breakdown()
            
            if not positions:
                self.logger.info("No positions to hedge")
                return []
            
            # Calculate current portfolio delta (simplified)
            current_delta = sum(pos.size for pos in positions)
            delta_deviation = current_delta - target_delta
            
            self.logger.info(f"Current delta: {current_delta:.4f}, target: {target_delta:.4f}, deviation: {delta_deviation:.4f}")
            
            # Check if hedging is needed (1% tolerance)
            if abs(delta_deviation) < 0.01:
                self.logger.info("Portfolio delta within tolerance, no hedging needed")
                return []
            
            # Simple hedge: use SOL-PERP to offset delta
            hedge_size = -delta_deviation  # Opposite direction to offset
            hedge_market = "SOL-PERP"
            
            # Place hedge order
            order_id = await self.trading_manager.place_market_order(
                market=hedge_market,
                side="buy" if hedge_size > 0 else "sell",
                size=abs(hedge_size)
            )
            
            if order_id:
                self.logger.info(f"Placed hedge order {order_id}: {hedge_size:.4f} {hedge_market}")
                return [order_id]
            else:
                self.logger.error("Failed to place hedge order")
                return []
            
        except Exception as e:
            self.logger.error(f"Error auto-hedging portfolio: {e}")
            return []

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    async def suggest_position_sizes(
        self,
        market: str,
        strategy: str,
        risk_tolerance: float
    ) -> PositionSizing:
        """
        Suggest optimal position sizes based on risk parameters.
        
        Args:
            market: Market symbol
            strategy: Strategy name
            risk_tolerance: Risk tolerance (0.0 to 1.0)
            
        Returns:
            PositionSizing recommendation
        """
        try:
            # Get portfolio summary
            summary = await self.get_portfolio_summary()
            
            # Get market data
            market_data = await self.market_data_manager.get_market_summary(market)
            if not market_data:
                raise ValueError(f"Could not get market data for {market}")
            
            current_price = float(market_data.get('mark_price', 0))
            if current_price <= 0:
                raise ValueError(f"Invalid price for {market}: {current_price}")
            
            # Calculate position sizes
            portfolio_value = summary.total_value
            
            # Basic position sizing (can be enhanced with Kelly criterion, etc.)
            max_risk_per_trade = portfolio_value * 0.02 * risk_tolerance  # 2% base risk
            max_position_value = min(
                self.risk_limits.max_position_size_usd,
                portfolio_value * self.risk_limits.max_position_size_percent
            )
            
            # Simple volatility-based sizing (placeholder)
            volatility_adjustment = 1.0  # TODO: Calculate actual volatility
            
            recommended_size = (max_risk_per_trade / current_price) * volatility_adjustment
            max_size = max_position_value / current_price
            risk_adjusted_size = min(recommended_size, max_size)
            
            sizing = PositionSizing(
                market=market,
                recommended_size=recommended_size,
                max_size=max_size,
                risk_adjusted_size=risk_adjusted_size,
                reasoning=f"Based on {risk_tolerance:.1%} risk tolerance and current volatility",
                confidence=0.7  # Placeholder confidence score
            )
            
            self.logger.info(f"Position sizing for {market}: {risk_adjusted_size:.4f} (max: {max_size:.4f})")
            return sizing
            
        except Exception as e:
            self.logger.error(f"Error calculating position sizes for {market}: {e}")
            raise

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached data is still valid."""
        return (
            key in self._portfolio_cache and
            time.time() - self._last_cache_update < self._cache_ttl
        )

    async def calculate_portfolio_risk(self) -> Dict[str, Any]:
        """
        Calculate basic portfolio risk metrics.
        This is a placeholder - advanced risk calculations will be in RiskEngine.
        
        Returns:
            Dictionary with basic risk metrics
        """
        try:
            summary = await self.get_portfolio_summary()
            positions = await self.get_position_breakdown()
            
            # Basic risk metrics
            total_exposure = sum(abs(pos.size * pos.current_price) for pos in positions)
            concentration_risk = max(
                (abs(pos.size * pos.current_price) / summary.total_value for pos in positions),
                default=0.0
            ) if summary.total_value > 0 else 0.0
            
            risk_metrics = {
                "total_exposure": total_exposure,
                "leverage": summary.leverage,
                "health_ratio": summary.health_ratio,
                "concentration_risk": concentration_risk,
                "num_positions": len(positions),
                "largest_position": max((abs(pos.size * pos.current_price) for pos in positions), default=0.0)
            }
            
            return risk_metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio risk: {e}")
            return {}

    async def rebalance_portfolio(self, target_allocations: Dict[str, float]) -> Dict[str, Any]:
        """
        Basic portfolio rebalancing functionality.
        
        Args:
            target_allocations: Dictionary of market -> target weight
            
        Returns:
            Rebalancing result summary
        """
        try:
            # This is a placeholder for basic rebalancing
            # Advanced rebalancing will be implemented in a separate engine
            
            self.logger.info(f"Rebalancing portfolio to targets: {target_allocations}")
            
            # Get current positions
            positions = await self.get_position_breakdown()
            summary = await self.get_portfolio_summary()
            
            if summary.total_value <= 0:
                raise ValueError("Cannot rebalance portfolio with zero value")
            
            # Calculate current allocations
            current_allocations = {}
            for pos in positions:
                position_value = abs(pos.size * pos.current_price)
                current_allocations[pos.market] = position_value / summary.total_value
            
            # Calculate required trades (simplified)
            required_trades = []
            for market, target_weight in target_allocations.items():
                current_weight = current_allocations.get(market, 0.0)
                weight_diff = target_weight - current_weight
                
                if abs(weight_diff) > 0.01:  # 1% tolerance
                    target_value = target_weight * summary.total_value
                    current_value = current_weight * summary.total_value
                    trade_value = target_value - current_value
                    
                    required_trades.append({
                        "market": market,
                        "current_weight": current_weight,
                        "target_weight": target_weight,
                        "trade_value": trade_value
                    })
            
            result = {
                "trades_required": len(required_trades),
                "trades": required_trades,
                "total_turnover": sum(abs(trade["trade_value"]) for trade in required_trades),
                "status": "analysis_complete"
            }
            
            self.logger.info(f"Rebalancing analysis: {len(required_trades)} trades required")
            return result
            
        except Exception as e:
            self.logger.error(f"Error rebalancing portfolio: {e}")
            return {"error": str(e), "status": "failed"}