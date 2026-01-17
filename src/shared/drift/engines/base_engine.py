"""
Base Trading Engine
==================

Abstract base class for all specialized trading engines.
Provides common functionality and interfaces.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from ..sdk.models.trading import TradeSignal, TradeResult
from ..sdk.models.portfolio import PortfolioState
from ..sdk.models.risk import RiskMetrics
from ..sdk.data.market_data_provider import MarketDataProvider
from ..sdk.data.risk_data_provider import RiskDataProvider
from ..sdk.data.portfolio_data_provider import PortfolioDataProvider
from src.shared.system.logging import Logger


class EngineStatus(Enum):
    """Trading engine status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class EngineMetrics:
    """Engine performance and operational metrics."""
    engine_name: str
    status: EngineStatus
    uptime_seconds: float
    signals_generated: int
    trades_executed: int
    total_pnl: float
    success_rate: float
    avg_execution_time_ms: float
    last_signal_time: Optional[datetime]
    last_trade_time: Optional[datetime]
    error_count: int
    last_error: Optional[str]
    calculation_time: datetime


class BaseTradingEngine(ABC):
    """
    Abstract base class for all trading engines.
    
    Provides common functionality including:
    - Engine lifecycle management
    - Signal generation interface
    - Risk validation
    - Performance tracking
    - Error handling
    """
    
    def __init__(
        self,
        engine_name: str,
        market_data_provider: MarketDataProvider,
        risk_data_provider: RiskDataProvider,
        portfolio_data_provider: PortfolioDataProvider
    ):
        """
        Initialize base trading engine.
        
        Args:
            engine_name: Unique name for this engine
            market_data_provider: Market data provider instance
            risk_data_provider: Risk data provider instance
            portfolio_data_provider: Portfolio data provider instance
        """
        self.engine_name = engine_name
        self.market_data = market_data_provider
        self.risk_data = risk_data_provider
        self.portfolio_data = portfolio_data_provider
        self.logger = Logger
        
        # Engine state
        self._status = EngineStatus.STOPPED
        self._start_time: Optional[datetime] = None
        self._error_count = 0
        self._last_error: Optional[str] = None
        
        # Performance tracking
        self._signals_generated = 0
        self._trades_executed = 0
        self._total_pnl = 0.0
        self._execution_times: List[float] = []
        self._last_signal_time: Optional[datetime] = None
        self._last_trade_time: Optional[datetime] = None
        
        # Configuration
        self._enabled = True
        self._max_signals_per_hour = 100
        self._min_signal_interval_seconds = 60
        
        self.logger.info(f"Initialized {engine_name} trading engine")
    
    # ==========================================================================
    # ABSTRACT METHODS - Must be implemented by concrete engines
    # ==========================================================================
    
    @abstractmethod
    async def generate_signals(self, **kwargs) -> List[TradeSignal]:
        """
        Generate trading signals based on engine strategy.
        
        Args:
            **kwargs: Engine-specific parameters
            
        Returns:
            List of trading signals
        """
        pass
    
    @abstractmethod
    async def validate_signal(self, signal: TradeSignal) -> bool:
        """
        Validate a trading signal before execution.
        
        Args:
            signal: Trading signal to validate
            
        Returns:
            True if signal is valid for execution
        """
        pass
    
    @abstractmethod
    async def calculate_position_size(
        self, 
        signal: TradeSignal,
        portfolio_state: PortfolioState,
        risk_metrics: RiskMetrics
    ) -> float:
        """
        Calculate appropriate position size for a signal.
        
        Args:
            signal: Trading signal
            portfolio_state: Current portfolio state
            risk_metrics: Current risk metrics
            
        Returns:
            Calculated position size
        """
        pass
    
    # ==========================================================================
    # CONCRETE METHODS - Common functionality
    # ==========================================================================
    
    async def start(self) -> bool:
        """
        Start the trading engine.
        
        Returns:
            True if started successfully
        """
        try:
            if self._status != EngineStatus.STOPPED:
                self.logger.warning(f"Engine {self.engine_name} already running")
                return False
            
            self._status = EngineStatus.STARTING
            self.logger.info(f"Starting engine {self.engine_name}")
            
            # Perform startup validation
            startup_valid = await self._validate_startup()
            if not startup_valid:
                self._status = EngineStatus.ERROR
                self._last_error = "Startup validation failed"
                return False
            
            # Initialize engine-specific components
            init_success = await self._initialize_engine()
            if not init_success:
                self._status = EngineStatus.ERROR
                self._last_error = "Engine initialization failed"
                return False
            
            self._status = EngineStatus.RUNNING
            self._start_time = datetime.now()
            
            self.logger.info(f"Engine {self.engine_name} started successfully")
            return True
            
        except Exception as e:
            self._status = EngineStatus.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self.logger.error(f"Error starting engine {self.engine_name}: {e}")
            return False
    
    async def stop(self) -> bool:
        """
        Stop the trading engine.
        
        Returns:
            True if stopped successfully
        """
        try:
            if self._status == EngineStatus.STOPPED:
                return True
            
            self._status = EngineStatus.STOPPING
            self.logger.info(f"Stopping engine {self.engine_name}")
            
            # Perform cleanup
            await self._cleanup_engine()
            
            self._status = EngineStatus.STOPPED
            self.logger.info(f"Engine {self.engine_name} stopped")
            return True
            
        except Exception as e:
            self._status = EngineStatus.ERROR
            self._last_error = str(e)
            self._error_count += 1
            self.logger.error(f"Error stopping engine {self.engine_name}: {e}")
            return False
    
    async def pause(self) -> bool:
        """
        Pause the trading engine.
        
        Returns:
            True if paused successfully
        """
        if self._status == EngineStatus.RUNNING:
            self._status = EngineStatus.PAUSED
            self.logger.info(f"Engine {self.engine_name} paused")
            return True
        return False
    
    async def resume(self) -> bool:
        """
        Resume the trading engine from paused state.
        
        Returns:
            True if resumed successfully
        """
        if self._status == EngineStatus.PAUSED:
            self._status = EngineStatus.RUNNING
            self.logger.info(f"Engine {self.engine_name} resumed")
            return True
        return False
    
    async def execute_strategy(self, **kwargs) -> List[TradeSignal]:
        """
        Execute the engine's trading strategy.
        
        Args:
            **kwargs: Strategy-specific parameters
            
        Returns:
            List of validated trading signals
        """
        try:
            if not self.is_running():
                return []
            
            # Check rate limiting
            if not self._check_rate_limits():
                return []
            
            # Generate signals
            signals = await self.generate_signals(**kwargs)
            self._signals_generated += len(signals)
            
            if signals:
                self._last_signal_time = datetime.now()
            
            # Validate signals
            validated_signals = []
            for signal in signals:
                try:
                    if await self.validate_signal(signal):
                        validated_signals.append(signal)
                    else:
                        self.logger.debug(f"Signal validation failed for {signal.signal_id}")
                except Exception as e:
                    self.logger.error(f"Error validating signal {signal.signal_id}: {e}")
            
            self.logger.info(f"Engine {self.engine_name} generated {len(validated_signals)} valid signals")
            return validated_signals
            
        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            self.logger.error(f"Error executing strategy for {self.engine_name}: {e}")
            return []
    
    async def record_trade_result(self, trade_result: TradeResult) -> None:
        """
        Record the result of a trade execution.
        
        Args:
            trade_result: Trade execution result
        """
        try:
            self._trades_executed += 1
            self._total_pnl += trade_result.estimated_pnl
            self._execution_times.append(trade_result.execution_time_ms)
            self._last_trade_time = trade_result.execution_end
            
            # Keep only recent execution times for performance calculation
            if len(self._execution_times) > 1000:
                self._execution_times = self._execution_times[-500:]
            
            self.logger.info(
                f"Recorded trade result for {self.engine_name}: "
                f"PnL ${trade_result.estimated_pnl:.2f}, "
                f"Execution time {trade_result.execution_time_ms:.1f}ms"
            )
            
        except Exception as e:
            self.logger.error(f"Error recording trade result: {e}")
    
    def get_metrics(self) -> EngineMetrics:
        """
        Get current engine metrics.
        
        Returns:
            EngineMetrics with current performance data
        """
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()
        
        success_rate = 0.0
        if self._trades_executed > 0:
            # Simplified success rate calculation
            success_rate = max(0.0, min(1.0, (self._total_pnl + abs(self._total_pnl)) / (2 * abs(self._total_pnl)) if self._total_pnl != 0 else 0.5))
        
        avg_execution_time = 0.0
        if self._execution_times:
            avg_execution_time = sum(self._execution_times) / len(self._execution_times)
        
        return EngineMetrics(
            engine_name=self.engine_name,
            status=self._status,
            uptime_seconds=uptime,
            signals_generated=self._signals_generated,
            trades_executed=self._trades_executed,
            total_pnl=self._total_pnl,
            success_rate=success_rate,
            avg_execution_time_ms=avg_execution_time,
            last_signal_time=self._last_signal_time,
            last_trade_time=self._last_trade_time,
            error_count=self._error_count,
            last_error=self._last_error,
            calculation_time=datetime.now()
        )
    
    # ==========================================================================
    # STATUS AND CONFIGURATION
    # ==========================================================================
    
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._status == EngineStatus.RUNNING
    
    def is_enabled(self) -> bool:
        """Check if engine is enabled."""
        return self._enabled
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the engine."""
        self._enabled = enabled
        self.logger.info(f"Engine {self.engine_name} {'enabled' if enabled else 'disabled'}")
    
    def get_status(self) -> EngineStatus:
        """Get current engine status."""
        return self._status
    
    def set_rate_limits(self, max_signals_per_hour: int, min_interval_seconds: int) -> None:
        """
        Set rate limiting parameters.
        
        Args:
            max_signals_per_hour: Maximum signals per hour
            min_interval_seconds: Minimum seconds between signals
        """
        self._max_signals_per_hour = max_signals_per_hour
        self._min_signal_interval_seconds = min_interval_seconds
    
    # ==========================================================================
    # PROTECTED METHODS - For use by concrete engines
    # ==========================================================================
    
    async def _validate_startup(self) -> bool:
        """
        Validate engine can start successfully.
        
        Returns:
            True if startup validation passes
        """
        try:
            # Check data provider connectivity
            portfolio_state = await self.portfolio_data.get_portfolio_state()
            if not portfolio_state:
                self.logger.error("Cannot connect to portfolio data provider")
                return False
            
            # Check market data availability
            positions = await self.portfolio_data.get_positions()
            if positions:
                # Test market data for first position
                market_data = await self.market_data.get_market_summary(positions[0].market)
                if not market_data:
                    self.logger.warning("Market data may be unavailable")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Startup validation failed: {e}")
            return False
    
    async def _initialize_engine(self) -> bool:
        """
        Initialize engine-specific components.
        Override in concrete engines for custom initialization.
        
        Returns:
            True if initialization successful
        """
        return True
    
    async def _cleanup_engine(self) -> None:
        """
        Cleanup engine-specific resources.
        Override in concrete engines for custom cleanup.
        """
        pass
    
    def _check_rate_limits(self) -> bool:
        """
        Check if engine is within rate limits.
        
        Returns:
            True if within limits
        """
        if not self._enabled:
            return False
        
        # Check minimum interval
        if self._last_signal_time:
            time_since_last = (datetime.now() - self._last_signal_time).total_seconds()
            if time_since_last < self._min_signal_interval_seconds:
                return False
        
        # Check hourly limit (simplified)
        # In production, would track signals over rolling hour
        return True
    
    def _create_signal_id(self) -> str:
        """
        Create unique signal ID.
        
        Returns:
            Unique signal identifier
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{self.engine_name}_{timestamp}"