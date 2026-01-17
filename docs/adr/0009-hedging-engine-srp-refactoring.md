# ADR-0009: Hedging Engine SRP Refactoring

## Status
Proposed

## Context

The `DriftHedgingEngine` class has grown into a monolithic component with over 1,900 lines of code, violating the Single Responsibility Principle (SRP). The current implementation handles multiple distinct responsibilities:

1. **Delta Calculation & Portfolio Analysis** (8 methods, ~300 LOC)
2. **Hedge Requirement Calculation** (6 methods, ~400 LOC) 
3. **Trade Execution & Order Management** (8 methods, ~500 LOC)
4. **Correlation Monitoring & Analysis** (7 methods, ~350 LOC)
5. **Performance Monitoring & Statistics** (5 methods, ~200 LOC)
6. **Risk Integration & Configuration** (4 methods, ~150 LOC)

This monolithic structure creates several problems:
- **Testing Complexity**: Difficult to unit test individual responsibilities
- **Maintenance Burden**: Changes to one area risk breaking others
- **Code Reusability**: Components cannot be used independently
- **Cognitive Load**: Developers must understand entire system to modify any part
- **Deployment Risk**: Single point of failure for all hedging operations

## Decision

We will refactor the `DriftHedgingEngine` into a modular architecture following SOLID principles, specifically focusing on Single Responsibility Principle and Interface Segregation.

### Proposed Architecture

```
DriftHedgingEngine (Orchestrator)
├── PortfolioDeltaCalculator
├── HedgeRequirementsCalculator  
├── HedgeTradeExecutor
├── CorrelationMonitor
├── HedgePerformanceTracker
└── RiskEngineIntegrator
```

### Component Breakdown

#### 1. PortfolioDeltaCalculator
**Responsibility**: Calculate and cache portfolio delta metrics
```python
class PortfolioDeltaCalculator:
    async def calculate_portfolio_delta() -> float
    async def get_position_deltas() -> Dict[str, float]
    async def validate_delta_calculation() -> bool
    def clear_delta_cache() -> None
```

#### 2. HedgeRequirementsCalculator  
**Responsibility**: Determine optimal hedge trades and sizing
```python
class HedgeRequirementsCalculator:
    async def calculate_hedge_requirements(target_delta: float) -> HedgeRequirements
    async def calculate_hedge_trades(positions: List[Dict]) -> List[HedgeTrade]
    async def select_hedge_market(positions: List[Dict]) -> str
    async def calculate_hedge_ratio(hedge_market: str) -> float
    async def estimate_hedge_cost(trades: List[HedgeTrade]) -> float
    async def calculate_confidence_score(trades: List[HedgeTrade]) -> float
```

#### 3. HedgeTradeExecutor
**Responsibility**: Execute hedge trades with intelligent order management
```python
class HedgeTradeExecutor:
    async def execute_hedge_trades(requirements: HedgeRequirements) -> HedgeResult
    async def execute_single_trade(trade: HedgeTrade) -> Dict[str, Any]
    async def select_optimal_order_type(trade: HedgeTrade) -> Tuple[str, float]
    async def optimize_execution_size(trade: HedgeTrade) -> List[Dict]
    async def execute_trade_chunk(chunk: Dict) -> Dict[str, Any]
    async def calculate_adaptive_backoff(retry_count: int) -> float
    async def emergency_hedge(max_trades: int) -> EmergencyHedgeResult
```

#### 4. CorrelationMonitor
**Responsibility**: Monitor correlation changes and adjust hedge ratios
```python
class CorrelationMonitor:
    async def monitor_correlation_changes(risk_engine) -> Dict[str, Any]
    async def adjust_hedge_ratios(new_correlations: Dict) -> bool
    async def analyze_correlation_changes(old_corr: Dict, new_corr: Dict) -> Dict
    async def assess_correlation_stability(hedge_market: str) -> float
    async def detect_recent_correlation_changes() -> int
    def enable_automatic_monitoring(risk_engine) -> bool
    def get_monitoring_status() -> Dict[str, Any]
```

#### 5. HedgePerformanceTracker
**Responsibility**: Track and analyze hedge effectiveness
```python
class HedgePerformanceTracker:
    async def monitor_hedge_effectiveness() -> HedgeMonitoring
    async def calculate_hedge_effectiveness() -> float
    def get_hedge_statistics() -> Dict[str, Any]
    def clear_hedge_history() -> None
    async def calculate_concentration_risk(positions: List[Dict]) -> float
    async def calculate_volatility_adjustment(hedge_market: str) -> float
```

#### 6. RiskEngineIntegrator
**Responsibility**: Integrate with risk engine and manage external dependencies
```python
class RiskEngineIntegrator:
    async def integrate_with_risk_engine(risk_engine) -> bool
    async def run_correlation_monitoring_if_due() -> Optional[Dict]
    async def check_correlation_monitoring_due() -> bool
    async def get_correlation_matrix(positions: List[Dict]) -> Optional[Dict]
    async def get_asset_returns(asset: str, days: int) -> List[float]
```

### Orchestrator Pattern

The main `DriftHedgingEngine` becomes a lightweight orchestrator:

```python
class DriftHedgingEngine:
    def __init__(self, drift_adapter, trading_manager, market_data_manager):
        self.delta_calculator = PortfolioDeltaCalculator(drift_adapter, market_data_manager)
        self.requirements_calculator = HedgeRequirementsCalculator(self.delta_calculator)
        self.trade_executor = HedgeTradeExecutor(trading_manager)
        self.correlation_monitor = CorrelationMonitor()
        self.performance_tracker = HedgePerformanceTracker()
        self.risk_integrator = RiskEngineIntegrator()
    
    async def calculate_hedge_requirements(self, target_delta: float = 0.0) -> HedgeRequirements:
        return await self.requirements_calculator.calculate_hedge_requirements(target_delta)
    
    async def execute_hedge_trades(self, requirements: HedgeRequirements) -> HedgeResult:
        return await self.trade_executor.execute_hedge_trades(requirements)
```

## Implementation Strategy

### Phase 1: Extract Core Calculators (Week 1)
1. Create `PortfolioDeltaCalculator` with delta calculation methods
2. Create `HedgeRequirementsCalculator` with hedge sizing logic
3. Update tests to use new components
4. Maintain backward compatibility through orchestrator

### Phase 2: Extract Execution Engine (Week 2)  
1. Create `HedgeTradeExecutor` with all execution logic
2. Move intelligent order management to executor
3. Implement emergency hedging in executor
4. Update integration tests

### Phase 3: Extract Monitoring Components (Week 3)
1. Create `CorrelationMonitor` with correlation analysis
2. Create `HedgePerformanceTracker` with effectiveness monitoring
3. Implement automatic monitoring workflows
4. Add comprehensive monitoring tests

### Phase 4: Extract Integration Layer (Week 4)
1. Create `RiskEngineIntegrator` for external dependencies
2. Implement clean interfaces for risk engine integration
3. Add configuration management
4. Complete end-to-end testing

### Phase 5: Optimization & Documentation (Week 5)
1. Optimize component interactions
2. Add comprehensive documentation
3. Performance testing and tuning
4. Migration guide for existing code

## Benefits

### Immediate Benefits
- **Testability**: Each component can be unit tested independently
- **Maintainability**: Changes isolated to specific responsibilities
- **Reusability**: Components can be used in other contexts
- **Readability**: Smaller, focused classes are easier to understand

### Long-term Benefits
- **Scalability**: Components can be optimized or replaced independently
- **Extensibility**: New hedge strategies can be added without modifying core logic
- **Reliability**: Failures isolated to specific components
- **Performance**: Targeted optimization of bottleneck components

## Risks and Mitigations

### Risk: Integration Complexity
**Mitigation**: Maintain orchestrator pattern with clean interfaces

### Risk: Performance Overhead
**Mitigation**: Use dependency injection and avoid unnecessary object creation

### Risk: Breaking Changes
**Mitigation**: Maintain backward compatibility through facade pattern during transition

### Risk: Testing Complexity
**Mitigation**: Implement comprehensive integration tests alongside unit tests

## Dependencies

- **Pydantic v2**: For data validation across component boundaries
- **Loguru**: For structured logging in each component  
- **Existing Trading Infrastructure**: No changes to external dependencies

## Success Metrics

- **Code Coverage**: >95% for each component
- **Cyclomatic Complexity**: <10 per method
- **Class Size**: <300 LOC per component
- **Test Execution Time**: <30s for full test suite
- **Memory Usage**: No increase in baseline memory consumption

## Migration Path

### For Existing Code
```python
# Before
hedging_engine = DriftHedgingEngine(adapter, trading_manager, market_data_manager)
requirements = await hedging_engine.calculate_hedge_requirements()

# After (backward compatible)
hedging_engine = DriftHedgingEngine(adapter, trading_manager, market_data_manager)
requirements = await hedging_engine.calculate_hedge_requirements()  # Same interface

# New usage (optional)
delta_calc = hedging_engine.delta_calculator
portfolio_delta = await delta_calc.calculate_portfolio_delta()
```

### Configuration Changes
- No configuration changes required
- Optional: Component-specific configuration for advanced users

## Conclusion

This refactoring will transform the monolithic `DriftHedgingEngine` into a maintainable, testable, and extensible system while preserving all existing functionality and maintaining backward compatibility. The modular architecture will enable future enhancements and optimizations without risking system stability.