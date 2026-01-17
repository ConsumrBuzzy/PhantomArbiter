"""
Delta Neutral Hedging Engine
===========================

Specialized engine for delta-neutral hedging strategies.
Maintains target portfolio delta through intelligent hedging.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..base_engine import BaseTradingEngine, EngineResult
from ...sdk.models.portfolio import PortfolioState
from ...sdk.models.trading import TradeSignal, SignalType, OrderSide
from ...sdk.models.risk import RiskMetrics
from ...sdk.data.market_data_provider import MarketDataProvider
from ...sdk.data.portfolio_data_provider import PortfolioDataProvider
from ...sdk.data.risk_data_provider import RiskDataProvider

from .delta_calculator import DeltaCalculator
from .hedge_executor import HedgeExecutor
from .effectiveness_monitor import EffectivenessMonitor, HedgeEffectivenessResult

from src.shared.system.logging import Logger


@dataclass
class DeltaNeutralConfig:
    """Configuration for delta neutral hedging engine."""
    
    # Delta targeting
    target_delta: float = 0.0  # Target portfolio delta
    delta_tolerance: float = 0.01  # 1% tolerance
    
    # Hedging parameters
    min_hedge_size: float = 100.0  # Minimum hedge size in USD
    max_hedge_size: float = 50000.0  # Maximum single hedge size
    hedge_frequency_minutes: int = 30  # Minimum minutes between hedges
    
    # Risk controls
    max_portfolio_leverage: float = 3.0  # Maximum allowed leverage
    emergency_hedge_threshold: float = 0.05  # 5% delta triggers emergency hedge
    
    # Execution parameters
    max_slippage: float = 0.005  # 0.5% maximum slippage
    execution_timeout_seconds: int = 30  # Order timeout
    
    # Effectiveness monitoring
    effectiveness_analysis_days: int = 30  # Days for effectiveness analysis
    min_effectiveness_score: float = 0.6  # Minimum acceptable effectiveness


class DeltaNeutralHedgingEngine(BaseTradingEngine):
    """
    Specialized engine for delta-neutral hedging strategies.
    
    Maintains portfolio delta near target through intelligent hedging,
    using shared SDK components for calculations and risk management.
    """
    
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        portfolio_data_provider: PortfolioDataProvider,
        risk_data_provider: RiskDataProvider,
        config: Optional[DeltaNeutralConfig] = None
    ):
        """
        Initialize delta neutral hedging engine.
        
        Args:
            market_data_provider: Market data provider
            portfolio_data_provider: Portfolio data provider  
            risk_data_provider: Risk data provider
            config: Engine configuration
        """
        super().__init__(
            engine_name="DeltaNeutralHedgingEngine",
            market_data_provider=market_data_provider,
            portfolio_data_provider=portfolio_data_provider,
            risk_data_provider=risk_data_provider
        )
        
        self.config = config or DeltaNeutralConfig()
        
        # Initialize components using shared SDK
        self.delta_calculator = DeltaCalculator(
            market_data_provider=market_data_provider,
            portfolio_data_provider=portfolio_data_provider
        )
        
        self.hedge_executor = HedgeExecutor(
            market_data_provider=market_data_provider,
            portfolio_data_provider=portfolio_data_provider,
            max_slippage=self.config.max_slippage,
            execution_timeout=self.config.execution_timeout_seconds
        )
        
        self.effectiveness_monitor = EffectivenessMonitor(
            market_data_provider=market_data_provider,
            portfolio_data_provider=portfolio_data_provider
        )
        
        # Engine state
        self._last_hedge_time = None
        self._hedge_history = []
        self._effectiveness_cache = {}
        
        self.logger.info(f"Delta Neutral Hedging Engine initialized with target delta {self.config.target_delta}")
    
    async def generate_signals(self, **kwargs) -> List[TradeSignal]:
        """
        Generate hedge signals based on current portfolio delta.
        
        Returns:
            List of hedge trade signals
        """
        try:
            self.logger.debug("Generating delta neutral hedge signals")
            
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                self.logger.warning("No portfolio state available for signal generation")
                return []
            
            # Check if hedging is needed
            hedge_requirements = await self._assess_hedge_requirements(portfolio_state)
            
            if not hedge_requirements['hedging_needed']:
                self.logger.debug(f"No hedging needed: delta deviation {hedge_requirements['delta_deviation']:.4f} within tolerance")
                return []
            
            # Check cooldown period
            if not self._is_hedge_allowed():
                self.logger.debug("Hedging blocked by cooldown period")
                return []
            
            # Calculate hedge trades
            hedge_trades = await self.hedge_executor.calculate_hedge_trades(
                current_delta=hedge_requirements['current_delta'],
                target_delta=self.config.target_delta,
                portfolio_state=portfolio_state,
                max_trade_size=self.config.max_hedge_size
            )
            
            # Convert to trade signals
            signals = []
            for i, trade in enumerate(hedge_trades):
                signal = TradeSignal(
                    signal_id=f"delta_hedge_{datetime.now().timestamp()}_{i}",
                    engine_name=self.engine_name,
                    signal_type=SignalType.HEDGE,
                    market=trade.market,
                    side=OrderSide.BUY if trade.side == "buy" else OrderSide.SELL,
                    size=trade.size,
                    signal_strength=trade.confidence_score,
                    target_price=trade.estimated_price,
                    max_slippage=self.config.max_slippage,
                    urgency=self._calculate_urgency(hedge_requirements),
                    risk_score=self._calculate_signal_risk(trade, portfolio_state),
                    created_at=datetime.now(),
                    reasoning=f"Delta hedge: current={hedge_requirements['current_delta']:.4f}, target={self.config.target_delta:.4f}, deviation={hedge_requirements['delta_deviation']:.4f}",
                    metadata={
                        'hedge_type': 'delta_neutral',
                        'target_delta': self.config.target_delta,
                        'current_delta': hedge_requirements['current_delta'],
                        'hedge_ratio': trade.hedge_ratio,
                        'priority': trade.priority
                    }
                )
                signals.append(signal)
            
            self.logger.info(f"Generated {len(signals)} delta hedge signals")
            return signals
            
        except Exception as e:
            self.logger.error(f"Error generating hedge signals: {e}")
            return []
    
    async def execute_strategy(self, **kwargs) -> EngineResult:
        """
        Execute complete delta neutral hedging strategy.
        
        Returns:
            EngineResult with execution summary
        """
        try:
            self.logger.info("Executing delta neutral hedging strategy")
            
            start_time = datetime.now()
            
            # Generate signals
            signals = await self.generate_signals(**kwargs)
            
            if not signals:
                return EngineResult(
                    engine_name=self.engine_name,
                    success=True,
                    signals_generated=0,
                    trades_executed=0,
                    total_pnl=0.0,
                    execution_time_ms=0.0,
                    message="No hedging required - portfolio delta within tolerance",
                    metadata={}
                )
            
            # Execute signals (this would integrate with actual trading system)
            execution_results = []
            total_pnl = 0.0
            
            for signal in signals:
                # In practice, this would submit orders to the trading system
                # For now, we'll simulate execution
                execution_result = await self._simulate_signal_execution(signal)
                execution_results.append(execution_result)
                total_pnl += execution_result.get('pnl', 0.0)
            
            # Update hedge history
            self._last_hedge_time = datetime.now()
            self._hedge_history.append({
                'timestamp': self._last_hedge_time,
                'signals_count': len(signals),
                'total_pnl': total_pnl,
                'execution_results': execution_results
            })
            
            # Calculate execution time
            execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            result = EngineResult(
                engine_name=self.engine_name,
                success=True,
                signals_generated=len(signals),
                trades_executed=len(execution_results),
                total_pnl=total_pnl,
                execution_time_ms=execution_time_ms,
                message=f"Executed {len(signals)} hedge trades with total PnL ${total_pnl:.2f}",
                metadata={
                    'hedge_type': 'delta_neutral',
                    'target_delta': self.config.target_delta,
                    'execution_results': execution_results
                }
            )
            
            self.logger.info(f"Delta neutral strategy executed: {len(signals)} signals, PnL=${total_pnl:.2f}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing delta neutral strategy: {e}")
            return EngineResult(
                engine_name=self.engine_name,
                success=False,
                signals_generated=0,
                trades_executed=0,
                total_pnl=0.0,
                execution_time_ms=0.0,
                message=f"Strategy execution failed: {e}",
                metadata={}
            )
    
    async def get_engine_status(self) -> Dict[str, Any]:
        """
        Get current engine status and metrics.
        
        Returns:
            Dictionary with engine status information
        """
        try:
            # Get current portfolio state
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            
            # Calculate current delta
            current_delta = 0.0
            if portfolio_state:
                current_delta = await self.delta_calculator.calculate_portfolio_delta(portfolio_state)
            
            # Get recent effectiveness analysis
            effectiveness_result = await self.effectiveness_monitor.analyze_hedge_effectiveness(
                analysis_days=7  # Last week
            )
            
            # Get real-time monitoring data
            monitoring_data = await self.effectiveness_monitor.monitor_real_time_effectiveness()
            
            status = {
                'engine_name': self.engine_name,
                'is_active': True,
                'configuration': {
                    'target_delta': self.config.target_delta,
                    'delta_tolerance': self.config.delta_tolerance,
                    'hedge_frequency_minutes': self.config.hedge_frequency_minutes,
                    'max_hedge_size': self.config.max_hedge_size
                },
                'current_state': {
                    'current_delta': current_delta,
                    'delta_deviation': abs(current_delta - self.config.target_delta),
                    'within_tolerance': abs(current_delta - self.config.target_delta) <= self.config.delta_tolerance,
                    'last_hedge_time': self._last_hedge_time.isoformat() if self._last_hedge_time else None,
                    'hedge_allowed': self._is_hedge_allowed()
                },
                'effectiveness_metrics': {
                    'effectiveness_score': effectiveness_result.effectiveness_score,
                    'hedge_ratio_stability': effectiveness_result.hedge_ratio_stability,
                    'tracking_error': effectiveness_result.tracking_error,
                    'cost_efficiency': effectiveness_result.hedge_cost_efficiency,
                    'recommendations': effectiveness_result.recommended_adjustments
                },
                'recent_activity': {
                    'hedges_last_24h': len([h for h in self._hedge_history if h['timestamp'] > datetime.now() - timedelta(days=1)]),
                    'total_hedges': len(self._hedge_history),
                    'monitoring_data': monitoring_data
                },
                'status_timestamp': datetime.now().isoformat()
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting engine status: {e}")
            return {
                'engine_name': self.engine_name,
                'is_active': False,
                'error': str(e),
                'status_timestamp': datetime.now().isoformat()
            }
    
    async def analyze_hedge_effectiveness(self, days: int = 30) -> HedgeEffectivenessResult:
        """
        Analyze hedge effectiveness over specified period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Comprehensive effectiveness analysis
        """
        return await self.effectiveness_monitor.analyze_hedge_effectiveness(days)
    
    # ==========================================================================
    # PRIVATE HELPER METHODS
    # ==========================================================================
    
    async def _assess_hedge_requirements(self, portfolio_state: PortfolioState) -> Dict[str, Any]:
        """Assess whether hedging is currently needed."""
        try:
            # Calculate current delta
            current_delta = await self.delta_calculator.calculate_portfolio_delta(portfolio_state)
            
            # Calculate deviation from target
            delta_deviation = abs(current_delta - self.config.target_delta)
            
            # Check if hedging is needed
            hedging_needed = delta_deviation > self.config.delta_tolerance
            
            # Check for emergency hedging
            emergency_hedge = delta_deviation > self.config.emergency_hedge_threshold
            
            # Check portfolio health
            portfolio_healthy = portfolio_state.health_ratio > 0.2  # 20% minimum health
            leverage_acceptable = portfolio_state.leverage <= self.config.max_portfolio_leverage
            
            return {
                'current_delta': current_delta,
                'target_delta': self.config.target_delta,
                'delta_deviation': delta_deviation,
                'hedging_needed': hedging_needed,
                'emergency_hedge': emergency_hedge,
                'portfolio_healthy': portfolio_healthy,
                'leverage_acceptable': leverage_acceptable,
                'can_hedge': portfolio_healthy and leverage_acceptable
            }
            
        except Exception as e:
            self.logger.error(f"Error assessing hedge requirements: {e}")
            return {
                'current_delta': 0.0,
                'target_delta': self.config.target_delta,
                'delta_deviation': 0.0,
                'hedging_needed': False,
                'emergency_hedge': False,
                'portfolio_healthy': False,
                'leverage_acceptable': False,
                'can_hedge': False
            }
    
    def _is_hedge_allowed(self) -> bool:
        """Check if hedging is allowed based on cooldown period."""
        if not self._last_hedge_time:
            return True
        
        time_since_last_hedge = datetime.now() - self._last_hedge_time
        cooldown_period = timedelta(minutes=self.config.hedge_frequency_minutes)
        
        return time_since_last_hedge >= cooldown_period
    
    def _calculate_urgency(self, hedge_requirements: Dict[str, Any]) -> float:
        """Calculate signal urgency based on hedge requirements."""
        # Base urgency on delta deviation
        deviation = hedge_requirements['delta_deviation']
        tolerance = self.config.delta_tolerance
        
        if hedge_requirements['emergency_hedge']:
            return 1.0  # Maximum urgency
        
        # Scale urgency based on deviation relative to tolerance
        urgency = min(1.0, deviation / (tolerance * 3))  # 3x tolerance = max urgency
        
        return max(0.1, urgency)  # Minimum 10% urgency
    
    def _calculate_signal_risk(self, trade, portfolio_state: PortfolioState) -> float:
        """Calculate risk score for a hedge signal."""
        # Risk factors
        risk_factors = []
        
        # Size risk (larger trades = higher risk)
        size_risk = min(1.0, trade.size * trade.estimated_price / portfolio_state.total_value)
        risk_factors.append(size_risk)
        
        # Market risk (based on volatility - simplified)
        market_risk = 0.3  # Default moderate market risk
        risk_factors.append(market_risk)
        
        # Execution risk (based on slippage tolerance)
        execution_risk = self.config.max_slippage * 10  # Scale slippage to risk
        risk_factors.append(min(1.0, execution_risk))
        
        # Average risk factors
        return sum(risk_factors) / len(risk_factors)
    
    async def _simulate_signal_execution(self, signal: TradeSignal) -> Dict[str, Any]:
        """Simulate signal execution (placeholder for actual trading integration)."""
        # This is a placeholder - in practice would integrate with actual trading system
        
        # Simulate execution with some randomness
        import random
        
        fill_rate = random.uniform(0.95, 1.0)  # 95-100% fill rate
        executed_size = signal.size * fill_rate
        slippage = random.uniform(0, signal.max_slippage)
        
        # Estimate PnL (simplified)
        estimated_pnl = random.uniform(-50, 100)  # Random PnL for simulation
        
        return {
            'signal_id': signal.signal_id,
            'market': signal.market,
            'side': signal.side.value,
            'requested_size': signal.size,
            'executed_size': executed_size,
            'fill_rate': fill_rate,
            'slippage': slippage,
            'pnl': estimated_pnl,
            'execution_time': datetime.now().isoformat(),
            'success': True
        }
    
    # ==========================================================================
    # CONFIGURATION METHODS
    # ==========================================================================
    
    def update_config(self, new_config: DeltaNeutralConfig) -> None:
        """Update engine configuration."""
        self.config = new_config
        self.logger.info(f"Updated delta neutral engine configuration: target_delta={new_config.target_delta}")
    
    def set_target_delta(self, target_delta: float) -> None:
        """Set new target delta."""
        self.config.target_delta = target_delta
        self.logger.info(f"Updated target delta to {target_delta}")
    
    def set_delta_tolerance(self, tolerance: float) -> None:
        """Set new delta tolerance."""
        self.config.delta_tolerance = tolerance
        self.logger.info(f"Updated delta tolerance to {tolerance}")
    
    def get_hedge_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get recent hedge history."""
        cutoff_time = datetime.now() - timedelta(days=days)
        return [h for h in self._hedge_history if h['timestamp'] > cutoff_time]