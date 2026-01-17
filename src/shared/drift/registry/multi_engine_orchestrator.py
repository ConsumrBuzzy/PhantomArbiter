"""
Multi-Engine Orchestrator
=========================

Orchestrates execution of multiple trading engines with conflict resolution.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio

from .trading_engine_registry import TradingEngineRegistry
from .signal_conflict_resolver import SignalConflictResolver, ConflictResolution
from ..engines.base_engine import EngineResult
from ..sdk.models.trading import TradeSignal
from ..risk_management.portfolio_risk_monitor import PortfolioRiskMonitor
from src.shared.system.logging import Logger


@dataclass
class OrchestrationResult:
    """Result of multi-engine orchestration."""
    
    # Execution summary
    total_engines_executed: int
    successful_engines: int
    failed_engines: int
    
    # Signal summary
    total_signals_generated: int
    signals_after_conflict_resolution: int
    signals_after_risk_validation: int
    final_signals_executed: int
    
    # Performance summary
    total_pnl: float
    total_execution_time_ms: float
    
    # Conflict resolution
    conflicts_detected: int
    conflicts_resolved: int
    conflict_resolutions: List[ConflictResolution]
    
    # Engine results
    engine_results: Dict[str, EngineResult]
    
    # Risk metrics
    risk_violations: int
    risk_warnings: int
    
    # Metadata
    orchestration_start_time: datetime
    orchestration_end_time: datetime
    orchestration_id: str
    
    @property
    def success_rate(self) -> float:
        """Calculate engine success rate."""
        if self.total_engines_executed == 0:
            return 0.0
        return self.successful_engines / self.total_engines_executed
    
    @property
    def signal_efficiency(self) -> float:
        """Calculate signal efficiency (executed / generated)."""
        if self.total_signals_generated == 0:
            return 0.0
        return self.final_signals_executed / self.total_signals_generated
    
    @property
    def orchestration_duration_ms(self) -> float:
        """Calculate total orchestration duration."""
        return (self.orchestration_end_time - self.orchestration_start_time).total_seconds() * 1000


class MultiEngineOrchestrator:
    """
    Orchestrates multiple trading engines with conflict resolution.
    
    Coordinates execution of multiple trading engines, resolves conflicts
    between their signals, and ensures portfolio-wide risk compliance.
    """
    
    def __init__(
        self,
        engine_registry: TradingEngineRegistry,
        conflict_resolver: SignalConflictResolver,
        risk_monitor: PortfolioRiskMonitor
    ):
        """
        Initialize multi-engine orchestrator.
        
        Args:
            engine_registry: Trading engine registry
            conflict_resolver: Signal conflict resolver
            risk_monitor: Portfolio risk monitor
        """
        self.engine_registry = engine_registry
        self.conflict_resolver = conflict_resolver
        self.risk_monitor = risk_monitor
        self.logger = Logger
        
        # Orchestration state
        self._orchestration_history: List[OrchestrationResult] = []
        self._max_history_size = 100
        
        # Configuration
        self.max_concurrent_engines = 5
        self.engine_timeout_seconds = 300  # 5 minutes
        self.enable_conflict_resolution = True
        self.enable_risk_validation = True
        
        self.logger.info("Multi-Engine Orchestrator initialized")
    
    async def run_all_strategies(self, **kwargs) -> OrchestrationResult:
        """
        Run all active trading strategies with full orchestration.
        
        Args:
            **kwargs: Strategy parameters passed to all engines
            
        Returns:
            Orchestration result with comprehensive execution summary
        """
        orchestration_id = f"orchestration_{datetime.now().timestamp()}"
        start_time = datetime.now()
        
        self.logger.info(f"🚀 Starting orchestration: {orchestration_id}")
        
        try:
            # Phase 1: Execute all engines
            self.logger.info("Phase 1: Executing all active engines")
            engine_results = await self._execute_all_engines(**kwargs)
            
            # Phase 2: Collect all signals
            self.logger.info("Phase 2: Collecting signals from engines")
            all_signals = self._collect_signals_from_results(engine_results)
            
            # Phase 3: Resolve conflicts
            conflict_resolutions = []
            signals_after_conflicts = all_signals
            
            if self.enable_conflict_resolution and len(all_signals) > 1:
                self.logger.info("Phase 3: Resolving signal conflicts")
                conflict_resolutions = await self._resolve_signal_conflicts(all_signals)
                signals_after_conflicts = await self._apply_conflict_resolutions(
                    all_signals, conflict_resolutions
                )
            
            # Phase 4: Risk validation
            validated_signals = signals_after_conflicts
            risk_violations = 0
            risk_warnings = 0
            
            if self.enable_risk_validation:
                self.logger.info("Phase 4: Validating signals against risk limits")
                validated_signals, risk_violations, risk_warnings = await self._validate_signals_risk(
                    signals_after_conflicts
                )
            
            # Phase 5: Execute final signals
            self.logger.info("Phase 5: Executing final validated signals")
            final_execution_results = await self._execute_final_signals(validated_signals)
            
            # Calculate summary metrics
            end_time = datetime.now()
            
            successful_engines = sum(1 for result in engine_results.values() if result.success)
            total_pnl = sum(result.total_pnl for result in engine_results.values())
            total_execution_time = sum(result.execution_time_ms for result in engine_results.values())
            
            # Create orchestration result
            orchestration_result = OrchestrationResult(
                total_engines_executed=len(engine_results),
                successful_engines=successful_engines,
                failed_engines=len(engine_results) - successful_engines,
                total_signals_generated=len(all_signals),
                signals_after_conflict_resolution=len(signals_after_conflicts),
                signals_after_risk_validation=len(validated_signals),
                final_signals_executed=len(final_execution_results),
                total_pnl=total_pnl,
                total_execution_time_ms=total_execution_time,
                conflicts_detected=len(conflict_resolutions),
                conflicts_resolved=len([cr for cr in conflict_resolutions if cr.resolved_signals]),
                conflict_resolutions=conflict_resolutions,
                engine_results=engine_results,
                risk_violations=risk_violations,
                risk_warnings=risk_warnings,
                orchestration_start_time=start_time,
                orchestration_end_time=end_time,
                orchestration_id=orchestration_id
            )
            
            # Store in history
            self._store_orchestration_result(orchestration_result)
            
            # Log summary
            self._log_orchestration_summary(orchestration_result)
            
            return orchestration_result
            
        except Exception as e:
            self.logger.error(f"Error in orchestration {orchestration_id}: {e}")
            
            # Return error result
            return OrchestrationResult(
                total_engines_executed=0,
                successful_engines=0,
                failed_engines=0,
                total_signals_generated=0,
                signals_after_conflict_resolution=0,
                signals_after_risk_validation=0,
                final_signals_executed=0,
                total_pnl=0.0,
                total_execution_time_ms=0.0,
                conflicts_detected=0,
                conflicts_resolved=0,
                conflict_resolutions=[],
                engine_results={},
                risk_violations=0,
                risk_warnings=0,
                orchestration_start_time=start_time,
                orchestration_end_time=datetime.now(),
                orchestration_id=orchestration_id
            )
    
    async def run_specific_engines(
        self, 
        engine_names: List[str], 
        **kwargs
    ) -> OrchestrationResult:
        """
        Run specific engines with orchestration.
        
        Args:
            engine_names: List of engine names to execute
            **kwargs: Strategy parameters
            
        Returns:
            Orchestration result
        """
        orchestration_id = f"specific_orchestration_{datetime.now().timestamp()}"
        start_time = datetime.now()
        
        self.logger.info(f"🎯 Starting specific orchestration: {orchestration_id} for engines: {engine_names}")
        
        try:
            # Execute specific engines
            engine_results = {}
            for engine_name in engine_names:
                try:
                    result = await self.engine_registry.execute_engine_strategy(engine_name, **kwargs)
                    engine_results[engine_name] = result
                except Exception as e:
                    self.logger.error(f"Error executing engine {engine_name}: {e}")
                    engine_results[engine_name] = EngineResult(
                        engine_name=engine_name,
                        success=False,
                        signals_generated=0,
                        trades_executed=0,
                        total_pnl=0.0,
                        execution_time_ms=0.0,
                        message=f"Execution error: {e}",
                        metadata={}
                    )
            
            # Continue with normal orchestration flow
            all_signals = self._collect_signals_from_results(engine_results)
            
            # Apply conflict resolution and risk validation
            conflict_resolutions = []
            if self.enable_conflict_resolution and len(all_signals) > 1:
                conflict_resolutions = await self._resolve_signal_conflicts(all_signals)
                all_signals = await self._apply_conflict_resolutions(all_signals, conflict_resolutions)
            
            validated_signals = all_signals
            risk_violations = 0
            risk_warnings = 0
            
            if self.enable_risk_validation:
                validated_signals, risk_violations, risk_warnings = await self._validate_signals_risk(all_signals)
            
            final_execution_results = await self._execute_final_signals(validated_signals)
            
            # Create result
            end_time = datetime.now()
            successful_engines = sum(1 for result in engine_results.values() if result.success)
            total_pnl = sum(result.total_pnl for result in engine_results.values())
            total_execution_time = sum(result.execution_time_ms for result in engine_results.values())
            
            orchestration_result = OrchestrationResult(
                total_engines_executed=len(engine_results),
                successful_engines=successful_engines,
                failed_engines=len(engine_results) - successful_engines,
                total_signals_generated=len(self._collect_signals_from_results(engine_results)),
                signals_after_conflict_resolution=len(all_signals),
                signals_after_risk_validation=len(validated_signals),
                final_signals_executed=len(final_execution_results),
                total_pnl=total_pnl,
                total_execution_time_ms=total_execution_time,
                conflicts_detected=len(conflict_resolutions),
                conflicts_resolved=len([cr for cr in conflict_resolutions if cr.resolved_signals]),
                conflict_resolutions=conflict_resolutions,
                engine_results=engine_results,
                risk_violations=risk_violations,
                risk_warnings=risk_warnings,
                orchestration_start_time=start_time,
                orchestration_end_time=end_time,
                orchestration_id=orchestration_id
            )
            
            self._store_orchestration_result(orchestration_result)
            self._log_orchestration_summary(orchestration_result)
            
            return orchestration_result
            
        except Exception as e:
            self.logger.error(f"Error in specific orchestration {orchestration_id}: {e}")
            return self._create_error_result(orchestration_id, start_time)
    
    async def get_orchestration_status(self) -> Dict[str, Any]:
        """
        Get current orchestration status and metrics.
        
        Returns:
            Dictionary with orchestration status
        """
        try:
            # Get recent orchestration history
            recent_orchestrations = self._orchestration_history[-10:] if self._orchestration_history else []
            
            # Calculate performance metrics
            if recent_orchestrations:
                avg_success_rate = sum(o.success_rate for o in recent_orchestrations) / len(recent_orchestrations)
                avg_signal_efficiency = sum(o.signal_efficiency for o in recent_orchestrations) / len(recent_orchestrations)
                total_pnl = sum(o.total_pnl for o in recent_orchestrations)
                avg_duration = sum(o.orchestration_duration_ms for o in recent_orchestrations) / len(recent_orchestrations)
            else:
                avg_success_rate = 0.0
                avg_signal_efficiency = 0.0
                total_pnl = 0.0
                avg_duration = 0.0
            
            # Get engine registry status
            registry_summary = self.engine_registry.get_registry_summary()
            
            status = {
                'orchestrator_config': {
                    'max_concurrent_engines': self.max_concurrent_engines,
                    'engine_timeout_seconds': self.engine_timeout_seconds,
                    'conflict_resolution_enabled': self.enable_conflict_resolution,
                    'risk_validation_enabled': self.enable_risk_validation
                },
                'recent_performance': {
                    'orchestrations_count': len(recent_orchestrations),
                    'avg_success_rate': avg_success_rate,
                    'avg_signal_efficiency': avg_signal_efficiency,
                    'total_pnl': total_pnl,
                    'avg_duration_ms': avg_duration
                },
                'engine_registry': registry_summary,
                'last_orchestration': {
                    'orchestration_id': recent_orchestrations[-1].orchestration_id if recent_orchestrations else None,
                    'end_time': recent_orchestrations[-1].orchestration_end_time.isoformat() if recent_orchestrations else None,
                    'success_rate': recent_orchestrations[-1].success_rate if recent_orchestrations else 0.0,
                    'total_pnl': recent_orchestrations[-1].total_pnl if recent_orchestrations else 0.0
                },
                'status_timestamp': datetime.now().isoformat()
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting orchestration status: {e}")
            return {}
    
    # ==========================================================================
    # PRIVATE ORCHESTRATION METHODS
    # ==========================================================================
    
    async def _execute_all_engines(self, **kwargs) -> Dict[str, EngineResult]:
        """Execute all active engines."""
        return await self.engine_registry.execute_all_active_engines(**kwargs)
    
    def _collect_signals_from_results(self, engine_results: Dict[str, EngineResult]) -> List[tuple]:
        """Collect all signals from engine results."""
        all_signals = []
        
        for engine_name, result in engine_results.items():
            # Extract signals from result metadata
            if 'signals' in result.metadata:
                for signal in result.metadata['signals']:
                    all_signals.append((engine_name, signal))
        
        return all_signals
    
    async def _resolve_signal_conflicts(self, engine_signals: List[tuple]) -> List[ConflictResolution]:
        """Resolve conflicts between signals."""
        try:
            # Get engine priorities from registry
            engine_priorities = {}
            for engine_name in set(engine_name for engine_name, _ in engine_signals):
                engine_status = self.engine_registry.get_engine_status(engine_name)
                if engine_status:
                    engine_priorities[engine_name] = engine_status.get('priority', 1)
            
            return await self.conflict_resolver.resolve_conflicts(engine_signals, engine_priorities)
            
        except Exception as e:
            self.logger.error(f"Error resolving signal conflicts: {e}")
            return []
    
    async def _apply_conflict_resolutions(
        self, 
        original_signals: List[tuple],
        resolutions: List[ConflictResolution]
    ) -> List[TradeSignal]:
        """Apply conflict resolutions to get final signals."""
        try:
            return await self.conflict_resolver.get_final_signals(
                original_signals,
                {engine_name: 1 for engine_name, _ in original_signals}  # Default priorities
            )
        except Exception as e:
            self.logger.error(f"Error applying conflict resolutions: {e}")
            return [signal for _, signal in original_signals]
    
    async def _validate_signals_risk(
        self, 
        signals: List[TradeSignal]
    ) -> tuple[List[TradeSignal], int, int]:
        """Validate signals against risk limits."""
        validated_signals = []
        risk_violations = 0
        risk_warnings = 0
        
        for signal in signals:
            try:
                validation_result = await self.risk_monitor.validate_trade_signal(signal)
                
                if validation_result.is_approved:
                    validated_signals.append(signal)
                    if validation_result.has_warnings:
                        risk_warnings += 1
                else:
                    risk_violations += 1
                    self.logger.warning(f"Signal {signal.signal_id} rejected by risk validation")
                    
            except Exception as e:
                self.logger.error(f"Error validating signal {signal.signal_id}: {e}")
                risk_violations += 1
        
        return validated_signals, risk_violations, risk_warnings
    
    async def _execute_final_signals(self, signals: List[TradeSignal]) -> List[Dict[str, Any]]:
        """Execute final validated signals."""
        execution_results = []
        
        for signal in signals:
            try:
                # This would integrate with actual trading system
                # For now, simulate execution
                execution_result = {
                    'signal_id': signal.signal_id,
                    'market': signal.market,
                    'side': signal.side.value,
                    'size': signal.size,
                    'executed': True,
                    'execution_time': datetime.now().isoformat()
                }
                execution_results.append(execution_result)
                
            except Exception as e:
                self.logger.error(f"Error executing signal {signal.signal_id}: {e}")
                execution_results.append({
                    'signal_id': signal.signal_id,
                    'executed': False,
                    'error': str(e)
                })
        
        return execution_results
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    def _store_orchestration_result(self, result: OrchestrationResult) -> None:
        """Store orchestration result in history."""
        self._orchestration_history.append(result)
        
        # Trim history if too large
        if len(self._orchestration_history) > self._max_history_size:
            self._orchestration_history = self._orchestration_history[-self._max_history_size:]
    
    def _log_orchestration_summary(self, result: OrchestrationResult) -> None:
        """Log orchestration summary."""
        self.logger.info(f"🎯 Orchestration {result.orchestration_id} completed:")
        self.logger.info(f"   ✅ Engines: {result.successful_engines}/{result.total_engines_executed} successful")
        self.logger.info(f"   📊 Signals: {result.final_signals_executed}/{result.total_signals_generated} executed")
        self.logger.info(f"   💰 PnL: ${result.total_pnl:.2f}")
        self.logger.info(f"   ⚡ Duration: {result.orchestration_duration_ms:.0f}ms")
        self.logger.info(f"   🔧 Conflicts: {result.conflicts_resolved}/{result.conflicts_detected} resolved")
        self.logger.info(f"   ⚠️  Risk: {result.risk_violations} violations, {result.risk_warnings} warnings")
    
    def _create_error_result(self, orchestration_id: str, start_time: datetime) -> OrchestrationResult:
        """Create error orchestration result."""
        return OrchestrationResult(
            total_engines_executed=0,
            successful_engines=0,
            failed_engines=0,
            total_signals_generated=0,
            signals_after_conflict_resolution=0,
            signals_after_risk_validation=0,
            final_signals_executed=0,
            total_pnl=0.0,
            total_execution_time_ms=0.0,
            conflicts_detected=0,
            conflicts_resolved=0,
            conflict_resolutions=[],
            engine_results={},
            risk_violations=0,
            risk_warnings=0,
            orchestration_start_time=start_time,
            orchestration_end_time=datetime.now(),
            orchestration_id=orchestration_id
        )
    
    # ==========================================================================
    # CONFIGURATION METHODS
    # ==========================================================================
    
    def configure_orchestration(
        self,
        max_concurrent_engines: Optional[int] = None,
        engine_timeout_seconds: Optional[int] = None,
        enable_conflict_resolution: Optional[bool] = None,
        enable_risk_validation: Optional[bool] = None
    ) -> None:
        """Configure orchestration parameters."""
        if max_concurrent_engines is not None:
            self.max_concurrent_engines = max_concurrent_engines
        
        if engine_timeout_seconds is not None:
            self.engine_timeout_seconds = engine_timeout_seconds
        
        if enable_conflict_resolution is not None:
            self.enable_conflict_resolution = enable_conflict_resolution
        
        if enable_risk_validation is not None:
            self.enable_risk_validation = enable_risk_validation
        
        self.logger.info("Orchestration configuration updated")
    
    def get_orchestration_history(self, limit: int = 10) -> List[OrchestrationResult]:
        """Get recent orchestration history."""
        return self._orchestration_history[-limit:] if self._orchestration_history else []