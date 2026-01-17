"""
Risk Data Provider
=================

Shared risk data interface for all trading engines.
Provides consistent access to risk calculations and metrics.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..models.risk import RiskMetrics, RiskAlert, RiskLimits
from ..models.portfolio import PortfolioState
from ..math.var_calculator import VaRCalculator, VaRResult
from ..math.correlation_calculator import CorrelationCalculator
from ..math.volatility_calculator import VolatilityCalculator
from ..math.performance_calculator import PerformanceCalculator
from src.shared.system.logging import Logger


class RiskDataProvider(ABC):
    """
    Abstract base class for risk data providers.
    
    Provides a consistent interface for risk calculations and monitoring
    across all trading engines.
    """
    
    def __init__(self):
        self.logger = Logger
        self._risk_limits = RiskLimits()
        self._calculation_cache = {}
        self._cache_ttl = 300  # 5 minutes for risk calculations
    
    # ==========================================================================
    # ABSTRACT METHODS - Must be implemented by concrete providers
    # ==========================================================================
    
    @abstractmethod
    async def get_portfolio_returns(self, days: int = 252) -> List[float]:
        """
        Get historical portfolio returns.
        
        Args:
            days: Number of days of return history
            
        Returns:
            List of daily portfolio returns
        """
        pass
    
    @abstractmethod
    async def get_asset_returns(self, asset: str, days: int = 252) -> List[float]:
        """
        Get historical returns for a specific asset.
        
        Args:
            asset: Asset identifier
            days: Number of days of return history
            
        Returns:
            List of daily asset returns
        """
        pass
    
    @abstractmethod
    async def get_portfolio_value_history(self, days: int = 252) -> List[Dict[str, Any]]:
        """
        Get historical portfolio values.
        
        Args:
            days: Number of days of history
            
        Returns:
            List of portfolio value snapshots with dates
        """
        pass
    
    # ==========================================================================
    # CONCRETE METHODS - Risk calculations using shared libraries
    # ==========================================================================
    
    async def calculate_portfolio_risk(
        self, 
        portfolio_state: PortfolioState,
        confidence_level: float = 0.95
    ) -> RiskMetrics:
        """
        Calculate comprehensive portfolio risk metrics.
        
        Args:
            portfolio_state: Current portfolio state
            confidence_level: Confidence level for VaR calculations
            
        Returns:
            Complete RiskMetrics object
        """
        try:
            # Get portfolio returns
            returns = await self.get_portfolio_returns(252)  # 1 year of data
            
            if not returns or len(returns) < 30:
                self.logger.warning("Insufficient return data for risk calculation")
                return self._empty_risk_metrics()
            
            # Calculate VaR
            var_result = VaRCalculator.calculate_var(
                returns=returns,
                portfolio_value=portfolio_state.total_value,
                confidence_level=confidence_level,
                method="historical_simulation"
            )
            
            # Calculate volatility
            volatility_result = VolatilityCalculator.historical_volatility(returns)
            
            # Calculate performance metrics
            performance_metrics = PerformanceCalculator.calculate_performance_metrics(returns)
            
            # Calculate drawdown analysis
            drawdown_analysis = PerformanceCalculator.calculate_drawdown_analysis(returns)
            
            # Calculate correlation matrix for positions
            correlation_matrix = await self._calculate_position_correlations(portfolio_state)
            
            # Calculate concentration and diversification
            concentration = self._calculate_portfolio_concentration(portfolio_state)
            diversification = self._calculate_diversification_ratio(portfolio_state, correlation_matrix)
            
            # Calculate sector exposures
            sector_exposures = self._calculate_sector_exposures(portfolio_state)
            
            # Calculate liquidity metrics
            liquidity_score, days_to_liquidate = await self._calculate_liquidity_metrics(portfolio_state)
            
            # Calculate tail risk measures
            expected_shortfall = self._calculate_expected_shortfall(returns, confidence_level)
            tail_ratio = self._calculate_tail_ratio(returns)
            
            # Determine volatility regime
            volatility_regime = self._determine_volatility_regime(volatility_result.volatility)
            
            # Create risk metrics
            risk_metrics = RiskMetrics(
                var_1d=var_result.var_1d,
                var_7d=var_result.var_7d,
                var_method=var_result.method,
                portfolio_volatility=volatility_result.volatility,
                volatility_regime=volatility_regime,
                max_drawdown=drawdown_analysis.max_drawdown,
                current_drawdown=drawdown_analysis.current_drawdown,
                drawdown_duration_days=drawdown_analysis.drawdown_duration,
                sharpe_ratio=performance_metrics.sharpe_ratio,
                sortino_ratio=performance_metrics.sortino_ratio,
                calmar_ratio=performance_metrics.calmar_ratio,
                correlation_matrix=correlation_matrix,
                portfolio_concentration=concentration,
                diversification_ratio=diversification,
                gross_leverage=portfolio_state.leverage,
                net_leverage=portfolio_state.leverage,  # Simplified
                sector_exposures=sector_exposures,
                liquidity_score=liquidity_score,
                days_to_liquidate=days_to_liquidate,
                expected_shortfall=expected_shortfall,
                tail_ratio=tail_ratio,
                calculation_date=datetime.now(),
                data_quality_score=self._calculate_data_quality(returns),
                confidence_level=confidence_level
            )
            
            return risk_metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio risk: {e}")
            return self._empty_risk_metrics()
    
    async def monitor_risk_changes(
        self, 
        current_risk: RiskMetrics,
        previous_risk: Optional[RiskMetrics] = None
    ) -> List[RiskAlert]:
        """
        Monitor for significant risk changes and generate alerts.
        
        Args:
            current_risk: Current risk metrics
            previous_risk: Previous risk metrics for comparison
            
        Returns:
            List of risk alerts
        """
        alerts = []
        
        try:
            # Check risk limit breaches
            limit_breaches = self._risk_limits.check_all_breaches(current_risk)
            
            for breach in limit_breaches:
                alert = RiskAlert(
                    alert_id=f"limit_breach_{datetime.now().timestamp()}",
                    alert_type="limit_breach",
                    severity="critical",
                    message=breach,
                    current_value=0.0,  # Would need specific values
                    threshold_value=0.0,
                    breach_percentage=0.0,
                    alert_time=datetime.now()
                )
                alerts.append(alert)
            
            # Check for significant changes if previous risk available
            if previous_risk:
                change_alerts = self._detect_risk_changes(current_risk, previous_risk)
                alerts.extend(change_alerts)
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error monitoring risk changes: {e}")
            return []
    
    async def calculate_var_forecast(
        self, 
        portfolio_state: PortfolioState,
        forecast_days: int = 1,
        confidence_level: float = 0.95
    ) -> VaRResult:
        """
        Calculate forecasted VaR.
        
        Args:
            portfolio_state: Current portfolio state
            forecast_days: Number of days to forecast
            confidence_level: Confidence level
            
        Returns:
            VaR forecast result
        """
        try:
            returns = await self.get_portfolio_returns(252)
            
            if not returns:
                return VaRResult(
                    var_1d=0.0,
                    var_7d=0.0,
                    confidence_level=confidence_level,
                    method="forecast",
                    portfolio_value=portfolio_state.total_value,
                    calculation_date=datetime.now()
                )
            
            # Use EWMA for forecasting
            var_result = VaRCalculator.calculate_var(
                returns=returns,
                portfolio_value=portfolio_state.total_value,
                confidence_level=confidence_level,
                horizon_days=forecast_days,
                method="monte_carlo"
            )
            
            return var_result
            
        except Exception as e:
            self.logger.error(f"Error calculating VaR forecast: {e}")
            return VaRResult(
                var_1d=0.0,
                var_7d=0.0,
                confidence_level=confidence_level,
                method="forecast_error",
                portfolio_value=portfolio_state.total_value,
                calculation_date=datetime.now()
            )
    
    async def detect_regime_changes(self, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Detect market regime changes based on correlation and volatility shifts.
        
        Args:
            threshold: Minimum change threshold for regime detection
            
        Returns:
            List of detected regime changes
        """
        try:
            regime_changes = []
            
            # Get recent portfolio returns
            recent_returns = await self.get_portfolio_returns(60)  # 2 months
            older_returns = await self.get_portfolio_returns(120)  # 4 months
            
            if len(recent_returns) < 30 or len(older_returns) < 60:
                return regime_changes
            
            # Compare recent vs historical volatility
            recent_vol = VolatilityCalculator.historical_volatility(recent_returns[-30:])
            historical_vol = VolatilityCalculator.historical_volatility(older_returns[:-30])
            
            vol_change = abs(recent_vol.volatility - historical_vol.volatility) / historical_vol.volatility
            
            if vol_change > threshold:
                regime_changes.append({
                    'type': 'volatility_regime_change',
                    'change_magnitude': vol_change,
                    'recent_volatility': recent_vol.volatility,
                    'historical_volatility': historical_vol.volatility,
                    'detection_date': datetime.now()
                })
            
            return regime_changes
            
        except Exception as e:
            self.logger.error(f"Error detecting regime changes: {e}")
            return []
    
    # ==========================================================================
    # PRIVATE HELPER METHODS
    # ==========================================================================
    
    async def _calculate_position_correlations(self, portfolio_state: PortfolioState) -> Dict[str, Dict[str, float]]:
        """Calculate correlation matrix for portfolio positions."""
        try:
            if not portfolio_state.positions:
                return {}
            
            # Get returns for each position's market
            market_returns = {}
            for position in portfolio_state.positions:
                market = position.market
                returns = await self.get_asset_returns(market, 60)  # 2 months
                if returns:
                    market_returns[market] = returns
            
            if len(market_returns) < 2:
                return {}
            
            # Calculate correlation matrix
            correlation_result = CorrelationCalculator.correlation_matrix(market_returns)
            return correlation_result.matrix
            
        except Exception as e:
            self.logger.error(f"Error calculating position correlations: {e}")
            return {}
    
    def _calculate_portfolio_concentration(self, portfolio_state: PortfolioState) -> float:
        """Calculate portfolio concentration using Herfindahl-Hirschman Index."""
        try:
            if not portfolio_state.positions:
                return 0.0
            
            total_value = sum(abs(pos.notional_value) for pos in portfolio_state.positions)
            
            if total_value == 0:
                return 0.0
            
            # Calculate HHI
            hhi = sum((abs(pos.notional_value) / total_value) ** 2 for pos in portfolio_state.positions)
            
            return hhi
            
        except Exception as e:
            self.logger.error(f"Error calculating concentration: {e}")
            return 0.0
    
    def _calculate_diversification_ratio(
        self, 
        portfolio_state: PortfolioState,
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> float:
        """Calculate portfolio diversification ratio."""
        try:
            if not portfolio_state.positions or not correlation_matrix:
                return 0.0
            
            # Simplified diversification calculation
            # In practice, would use proper portfolio theory
            
            n_positions = len(portfolio_state.positions)
            if n_positions <= 1:
                return 0.0
            
            # Average correlation
            total_correlation = 0.0
            correlation_count = 0
            
            for pos1 in portfolio_state.positions:
                for pos2 in portfolio_state.positions:
                    if pos1.market != pos2.market:
                        corr = correlation_matrix.get(pos1.market, {}).get(pos2.market, 0.0)
                        total_correlation += abs(corr)
                        correlation_count += 1
            
            if correlation_count == 0:
                return 1.0
            
            avg_correlation = total_correlation / correlation_count
            
            # Diversification ratio (simplified)
            diversification = 1.0 - avg_correlation
            
            return max(0.0, min(1.0, diversification))
            
        except Exception as e:
            self.logger.error(f"Error calculating diversification ratio: {e}")
            return 0.0
    
    def _calculate_sector_exposures(self, portfolio_state: PortfolioState) -> Dict[str, float]:
        """Calculate exposure by sector/asset class."""
        try:
            sector_exposures = {}
            total_exposure = sum(abs(pos.notional_value) for pos in portfolio_state.positions)
            
            if total_exposure == 0:
                return sector_exposures
            
            for position in portfolio_state.positions:
                # Extract sector from market (simplified)
                if 'SOL' in position.market:
                    sector = 'Solana'
                elif 'BTC' in position.market:
                    sector = 'Bitcoin'
                elif 'ETH' in position.market:
                    sector = 'Ethereum'
                else:
                    sector = 'Other'
                
                exposure = abs(position.notional_value) / total_exposure
                sector_exposures[sector] = sector_exposures.get(sector, 0.0) + exposure
            
            return sector_exposures
            
        except Exception as e:
            self.logger.error(f"Error calculating sector exposures: {e}")
            return {}
    
    async def _calculate_liquidity_metrics(self, portfolio_state: PortfolioState) -> tuple[float, float]:
        """Calculate portfolio liquidity score and days to liquidate."""
        try:
            if not portfolio_state.positions:
                return 1.0, 0.0
            
            # Simplified liquidity calculation
            # In practice, would use market depth and volume data
            
            total_value = sum(abs(pos.notional_value) for pos in portfolio_state.positions)
            weighted_liquidity = 0.0
            
            for position in portfolio_state.positions:
                # Assign liquidity scores based on market
                if 'SOL' in position.market or 'BTC' in position.market:
                    liquidity_score = 0.9  # High liquidity
                elif 'ETH' in position.market:
                    liquidity_score = 0.8  # Good liquidity
                else:
                    liquidity_score = 0.5  # Moderate liquidity
                
                weight = abs(position.notional_value) / total_value if total_value > 0 else 0
                weighted_liquidity += weight * liquidity_score
            
            # Estimate days to liquidate based on liquidity
            days_to_liquidate = (1.0 - weighted_liquidity) * 10  # 0-10 days
            
            return weighted_liquidity, days_to_liquidate
            
        except Exception as e:
            self.logger.error(f"Error calculating liquidity metrics: {e}")
            return 0.5, 5.0
    
    def _calculate_expected_shortfall(self, returns: List[float], confidence_level: float) -> float:
        """Calculate Expected Shortfall (Conditional VaR)."""
        try:
            if not returns:
                return 0.0
            
            # Sort returns
            sorted_returns = sorted(returns)
            
            # Find VaR threshold
            var_index = int((1 - confidence_level) * len(sorted_returns))
            var_index = max(0, min(var_index, len(sorted_returns) - 1))
            
            # Calculate expected shortfall (average of losses beyond VaR)
            tail_losses = sorted_returns[:var_index + 1]
            
            if not tail_losses:
                return 0.0
            
            expected_shortfall = -sum(tail_losses) / len(tail_losses)
            
            return expected_shortfall
            
        except Exception as e:
            self.logger.error(f"Error calculating expected shortfall: {e}")
            return 0.0
    
    def _calculate_tail_ratio(self, returns: List[float]) -> float:
        """Calculate tail ratio (95th percentile / 5th percentile)."""
        try:
            if len(returns) < 20:
                return 1.0
            
            sorted_returns = sorted(returns)
            
            # 95th percentile (gains)
            p95_index = int(0.95 * len(sorted_returns))
            p95 = sorted_returns[min(p95_index, len(sorted_returns) - 1)]
            
            # 5th percentile (losses)
            p5_index = int(0.05 * len(sorted_returns))
            p5 = sorted_returns[p5_index]
            
            if p5 == 0:
                return float('inf') if p95 > 0 else 1.0
            
            tail_ratio = abs(p95 / p5)
            
            return tail_ratio
            
        except Exception as e:
            self.logger.error(f"Error calculating tail ratio: {e}")
            return 1.0
    
    def _determine_volatility_regime(self, volatility: float) -> str:
        """Determine volatility regime based on current volatility."""
        if volatility < 0.15:  # <15% annualized
            return "low"
        elif volatility < 0.25:  # <25% annualized
            return "normal"
        elif volatility < 0.40:  # <40% annualized
            return "high"
        else:
            return "crisis"
    
    def _calculate_data_quality(self, returns: List[float]) -> float:
        """Calculate data quality score based on available data."""
        if not returns:
            return 0.0
        
        score = 0.5  # Base score
        
        # Data completeness
        if len(returns) >= 252:  # Full year
            score += 0.3
        elif len(returns) >= 60:  # Quarter
            score += 0.2
        elif len(returns) >= 30:  # Month
            score += 0.1
        
        # Data consistency (no extreme outliers)
        from statistics import stdev, mean
        if len(returns) > 1:
            vol = stdev(returns)
            avg = mean(returns)
            
            # Check for reasonable values
            extreme_returns = [r for r in returns if abs(r - avg) > 5 * vol]
            if len(extreme_returns) / len(returns) < 0.05:  # <5% extreme values
                score += 0.2
        
        return min(1.0, score)
    
    def _detect_risk_changes(self, current_risk: RiskMetrics, previous_risk: RiskMetrics) -> List[RiskAlert]:
        """Detect significant changes in risk metrics."""
        alerts = []
        
        # VaR increase alert
        var_change = (current_risk.var_1d - previous_risk.var_1d) / previous_risk.var_1d if previous_risk.var_1d > 0 else 0
        if var_change > 0.5:  # 50% increase
            alerts.append(RiskAlert(
                alert_id=f"var_increase_{datetime.now().timestamp()}",
                alert_type="var_increase",
                severity="warning",
                message=f"VaR increased by {var_change:.1%}",
                current_value=current_risk.var_1d,
                threshold_value=previous_risk.var_1d * 1.5,
                breach_percentage=var_change * 100,
                alert_time=datetime.now()
            ))
        
        # Volatility spike alert
        vol_change = (current_risk.portfolio_volatility - previous_risk.portfolio_volatility) / previous_risk.portfolio_volatility if previous_risk.portfolio_volatility > 0 else 0
        if vol_change > 1.0:  # 100% increase
            alerts.append(RiskAlert(
                alert_id=f"volatility_spike_{datetime.now().timestamp()}",
                alert_type="volatility_spike",
                severity="warning",
                message=f"Volatility spiked by {vol_change:.1%}",
                current_value=current_risk.portfolio_volatility,
                threshold_value=previous_risk.portfolio_volatility * 2.0,
                breach_percentage=vol_change * 100,
                alert_time=datetime.now()
            ))
        
        return alerts
    
    def _empty_risk_metrics(self) -> RiskMetrics:
        """Return empty risk metrics for error cases."""
        return RiskMetrics(
            var_1d=0.0,
            var_7d=0.0,
            var_method="none",
            portfolio_volatility=0.0,
            volatility_regime="unknown",
            max_drawdown=0.0,
            current_drawdown=0.0,
            drawdown_duration_days=0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            correlation_matrix={},
            portfolio_concentration=0.0,
            diversification_ratio=0.0,
            gross_leverage=0.0,
            net_leverage=0.0,
            sector_exposures={},
            liquidity_score=0.0,
            days_to_liquidate=0.0,
            expected_shortfall=0.0,
            tail_ratio=1.0,
            calculation_date=datetime.now(),
            data_quality_score=0.0,
            confidence_level=0.95
        )
    
    # ==========================================================================
    # CONFIGURATION METHODS
    # ==========================================================================
    
    def set_risk_limits(self, risk_limits: RiskLimits) -> None:
        """Set risk limits for monitoring."""
        self._risk_limits = risk_limits
    
    def get_risk_limits(self) -> RiskLimits:
        """Get current risk limits."""
        return self._risk_limits