"""
Trading Engine Registry
=======================

Registry for managing multiple trading engines and their execution.
"""

from typing import Dict, List, Any, Optional, Type
from datetime import datetime
from dataclasses import dataclass

from ..engines.base_engine import BaseTradingEngine, EngineResult
from ..sdk.models.trading import TradeSignal
from ..risk_management.portfolio_risk_monitor import PortfolioRiskMonitor, RiskValidationResult
from src.shared.system.logging import Logger


@dataclass
class EngineRegistration:
    """Engine registration information."""
    
    engine: BaseTradingEngine
    engine_class: Type[BaseTradingEngine]
    registration_time: datetime
    is_active: bool = True
    priority: int = 1  # Higher number = higher priority
    max_concurrent_signals: int = 10
    
    # Performance tracking
    total_executions: int = 0
    successful_executions: int = 0
    total_pnl: float = 0.0
    avg_execution_time_ms: float = 0.0
    
    # Risk tracking
    risk_violations: int = 0
    last_execution_time: Optional[datetime] = None


class TradingEngineRegistry:
    """
    Registry for managing multiple trading engines.
    
    Provides centralized management of trading engines including
    registration, execution coordination, and risk validation.
    """
    
    def __init__(self, risk_monitor: PortfolioRiskMonitor):
        """
        Initialize trading engine registry.
        
        Args:
            risk_monitor: Portfolio risk monitor for signal validation
        """
        self.risk_monitor = risk_monitor
        self.logger = Logger
        
        # Engine registry
        self._engines: Dict[str, EngineRegistration] = {}
        self._execution_queue: List[Dict[str, Any]] = []
        
        # Configuration
        self._max_concurrent_engines = 5
        self._execution_timeout_seconds = 300  # 5 minutes
        
        self.logger.info("Trading Engine Registry initialized")
    
    def register_engine(
        self, 
        name: str, 
        engine: BaseTradingEngine,
        priority: int = 1,
        max_concurrent_signals: int = 10
    ) -> bool:
        """
        Register a trading engine.
        
        Args:
            name: Unique engine name
            engine: Trading engine instance
            priority: Engine priority (higher = more important)
            max_concurrent_signals: Maximum concurrent signals from this engine
            
        Returns:
            True if registration successful
        """
        try:
            if name in self._engines:
                self.logger.warning(f"Engine {name} already registered, updating...")
            
            registration = EngineRegistration(
                engine=engine,
                engine_class=type(engine),
                registration_time=datetime.now(),
                priority=priority,
                max_concurrent_signals=max_concurrent_signals
            )
            
            self._engines[name] = registration
            
            self.logger.info(f"✅ Registered engine: {name} (priority: {priority})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering engine {name}: {e}")
            return False
    
    def unregister_engine(self, name: str) -> bool:
        """
        Unregister a trading engine.
        
        Args:
            name: Engine name to unregister
            
        Returns:
            True if unregistration successful
        """
        try:
            if name not in self._engines:
                self.logger.warning(f"Engine {name} not found for unregistration")
                return False
            
            del self._engines[name]
            
            self.logger.info(f"✅ Unregistered engine: {name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error unregistering engine {name}: {e}")
            return False
    
    def activate_engine(self, name: str) -> bool:
        """Activate an engine."""
        if name in self._engines:
            self._engines[name].is_active = True
            self.logger.info(f"Activated engine: {name}")
            return True
        return False
    
    def deactivate_engine(self, name: str) -> bool:
        """Deactivate an engine."""
        if name in self._engines:
            self._engines[name].is_active = False
            self.logger.info(f"Deactivated engine: {name}")
            return True
        return False
    
    async def execute_engine_strategy(self, engine_name: str, **kwargs) -> EngineResult:
        """
        Execute a specific engine's strategy with risk validation.
        
        Args:
            engine_name: Name of engine to execute
            **kwargs: Strategy parameters
            
        Returns:
            Engine execution result
        """
        try:
            # Check if engine exists and is active
            if engine_name not in self._engines:
                return EngineResult(
                    engine_name=engine_name,
                    success=False,
                    signals_generated=0,
                    trades_executed=0,
                    total_pnl=0.0,
                    execution_time_ms=0.0,
                    message=f"Engine {engine_name} not found",
                    metadata={}
                )
            
            registration = self._engines[engine_name]
            
            if not registration.is_active:
                return EngineResult(
                    engine_name=engine_name,
                    success=False,
                    signals_generated=0,
                    trades_executed=0,
                    total_pnl=0.0,
                    execution_time_ms=0.0,
                    message=f"Engine {engine_name} is inactive",
                    metadata={}
                )
            
            start_time = datetime.now()
            
            # Generate signals from engine
            self.logger.info(f"Executing strategy for engine: {engine_name}")
            signals = await registration.engine.generate_signals(**kwargs)
            
            # Validate all signals through risk monitor
            validated_signals = []
            validation_results = []
            
            for signal in signals:
                validation_result = await self.risk_monitor.validate_trade_signal(signal)
                validation_results.append(validation_result)
                
                if validation_result.is_approved:
                    validated_signals.append(signal)
                elif validation_result.status.value == 'warning':
                    # Include signals with warnings but log them
                    validated_signals.append(signal)
                    self.logger.warning(f"Signal {signal.signal_id} approved with warnings: {', '.join(validation_result.warnings)}")
                else:
                    self.logger.warning(f"Signal {signal.signal_id} rejected: {', '.join(validation_result.failed_checks)}")
                    registration.risk_violations += 1
            
            # Execute validated signals through the engine
            if validated_signals:
                # Update the engine's signals to only include validated ones
                execution_result = await registration.engine.execute_strategy(**kwargs)
                
                # Override with our validation results
                execution_result.signals_generated = len(signals)
                execution_result.metadata['validation_results'] = [
                    {
                        'signal_id': vr.signal_id,
                        'status': vr.status.value,
                        'risk_score': vr.risk_score,
                        'warnings': vr.warnings,
                        'failed_checks': vr.failed_checks
                    }
                    for vr in validation_results
                ]
                execution_result.metadata['validated_signals'] = len(validated_signals)
                execution_result.metadata['rejected_signals'] = len(signals) - len(validated_signals)
            else:
                # No validated signals
                execution_result = EngineResult(
                    engine_name=engine_name,
                    success=True,
                    signals_generated=len(signals),
                    trades_executed=0,
                    total_pnl=0.0,
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    message=f"All {len(signals)} signals rejected by risk validation",
                    metadata={
                        'validation_results': [
                            {
                                'signal_id': vr.signal_id,
                                'status': vr.status.value,
                                'risk_score': vr.risk_score,
                                'warnings': vr.warnings,
                                'failed_checks': vr.failed_checks
                            }
                            for vr in validation_results
                        ],
                        'validated_signals': 0,
                        'rejected_signals': len(signals)
                    }
                )
            
            # Update registration statistics
            self._update_engine_stats(registration, execution_result)
            
            return execution_result
            
        except Exception as e:
            self.logger.error(f"Error executing engine {engine_name}: {e}")
            return EngineResult(
                engine_name=engine_name,
                success=False,
                signals_generated=0,
                trades_executed=0,
                total_pnl=0.0,
                execution_time_ms=0.0,
                message=f"Execution error: {e}",
                metadata={}
            )
    
    async def execute_all_active_engines(self, **kwargs) -> Dict[str, EngineResult]:
        """
        Execute all active engines.
        
        Args:
            **kwargs: Strategy parameters passed to all engines
            
        Returns:
            Dictionary mapping engine name to execution result
        """
        results = {}
        
        # Sort engines by priority (highest first)
        sorted_engines = sorted(
            [(name, reg) for name, reg in self._engines.items() if reg.is_active],
            key=lambda x: x[1].priority,
            reverse=True
        )
        
        for engine_name, registration in sorted_engines:
            try:
                result = await self.execute_engine_strategy(engine_name, **kwargs)
                results[engine_name] = result
                
                # Log execution summary
                if result.success:
                    self.logger.info(f"✅ {engine_name}: {result.signals_generated} signals, {result.trades_executed} trades, PnL: ${result.total_pnl:.2f}")
                else:
                    self.logger.error(f"❌ {engine_name}: {result.message}")
                    
            except Exception as e:
                self.logger.error(f"Error executing engine {engine_name}: {e}")
                results[engine_name] = EngineResult(
                    engine_name=engine_name,
                    success=False,
                    signals_generated=0,
                    trades_executed=0,
                    total_pnl=0.0,
                    execution_time_ms=0.0,
                    message=f"Execution error: {e}",
                    metadata={}
                )
        
        return results
    
    def get_engine_status(self, engine_name: str) -> Optional[Dict[str, Any]]:
        """
        Get status information for a specific engine.
        
        Args:
            engine_name: Name of engine
            
        Returns:
            Engine status dictionary or None if not found
        """
        if engine_name not in self._engines:
            return None
        
        registration = self._engines[engine_name]
        
        # Calculate success rate
        success_rate = 0.0
        if registration.total_executions > 0:
            success_rate = registration.successful_executions / registration.total_executions
        
        return {
            'engine_name': engine_name,
            'engine_class': registration.engine_class.__name__,
            'is_active': registration.is_active,
            'priority': registration.priority,
            'registration_time': registration.registration_time.isoformat(),
            'performance': {
                'total_executions': registration.total_executions,
                'successful_executions': registration.successful_executions,
                'success_rate': success_rate,
                'total_pnl': registration.total_pnl,
                'avg_execution_time_ms': registration.avg_execution_time_ms,
                'risk_violations': registration.risk_violations,
                'last_execution_time': registration.last_execution_time.isoformat() if registration.last_execution_time else None
            }
        }
    
    def get_all_engine_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all registered engines."""
        return {
            name: self.get_engine_status(name)
            for name in self._engines.keys()
        }
    
    def get_registry_summary(self) -> Dict[str, Any]:
        """Get summary of the entire registry."""
        active_engines = sum(1 for reg in self._engines.values() if reg.is_active)
        total_executions = sum(reg.total_executions for reg in self._engines.values())
        total_pnl = sum(reg.total_pnl for reg in self._engines.values())
        total_risk_violations = sum(reg.risk_violations for reg in self._engines.values())
        
        return {
            'total_engines': len(self._engines),
            'active_engines': active_engines,
            'inactive_engines': len(self._engines) - active_engines,
            'total_executions': total_executions,
            'total_pnl': total_pnl,
            'total_risk_violations': total_risk_violations,
            'engines': list(self._engines.keys())
        }
    
    # ==========================================================================
    # PRIVATE METHODS
    # ==========================================================================
    
    def _update_engine_stats(self, registration: EngineRegistration, result: EngineResult) -> None:
        """Update engine performance statistics."""
        registration.total_executions += 1
        registration.last_execution_time = datetime.now()
        
        if result.success:
            registration.successful_executions += 1
        
        registration.total_pnl += result.total_pnl
        
        # Update average execution time
        if registration.total_executions == 1:
            registration.avg_execution_time_ms = result.execution_time_ms
        else:
            # Running average
            old_avg = registration.avg_execution_time_ms
            n = registration.total_executions
            registration.avg_execution_time_ms = ((n - 1) * old_avg + result.execution_time_ms) / n
    
    # ==========================================================================
    # ENGINE MANAGEMENT METHODS
    # ==========================================================================
    
    def set_engine_priority(self, engine_name: str, priority: int) -> bool:
        """Set engine priority."""
        if engine_name in self._engines:
            self._engines[engine_name].priority = priority
            self.logger.info(f"Set priority for {engine_name} to {priority}")
            return True
        return False
    
    def get_engines_by_priority(self) -> List[str]:
        """Get engine names sorted by priority (highest first)."""
        return [
            name for name, reg in sorted(
                self._engines.items(),
                key=lambda x: x[1].priority,
                reverse=True
            )
        ]
    
    def reset_engine_stats(self, engine_name: str) -> bool:
        """Reset performance statistics for an engine."""
        if engine_name in self._engines:
            reg = self._engines[engine_name]
            reg.total_executions = 0
            reg.successful_executions = 0
            reg.total_pnl = 0.0
            reg.avg_execution_time_ms = 0.0
            reg.risk_violations = 0
            reg.last_execution_time = None
            
            self.logger.info(f"Reset statistics for engine: {engine_name}")
            return True
        return False
    
    def get_engine_instance(self, engine_name: str) -> Optional[BaseTradingEngine]:
        """Get engine instance by name."""
        if engine_name in self._engines:
            return self._engines[engine_name].engine
        return None