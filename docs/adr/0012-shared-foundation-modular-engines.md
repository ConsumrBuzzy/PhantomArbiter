# ADR-0012: Shared Foundation with Modular Trading Engines

## Status
Proposed (Supersedes ADR-0009, ADR-0010, ADR-0011)

## Context

The current monolithic `DriftHedgingEngine` and `DriftRiskEngine` violate SRP, but complete decomposition risks losing component cohesion and introducing unnecessary complexity. We need an architecture that:

1. **Maintains Component Cohesion**: Related functionality stays together
2. **Respects SRP**: Each engine has a single, well-defined responsibility  
3. **Enables Strategy Diversity**: Multiple trading strategies can coexist
4. **Leverages DriftSDK**: Common foundation reduces duplication
5. **Supports Future Growth**: Easy to add new engines/strategies

## Decision

We will implement a **Shared Foundation + Specialized Engine** architecture where:
- **DriftSDK** provides the shared foundation (data, calculations, utilities)
- **Specialized Engines** implement specific trading strategies
- **Common Interfaces** enable interoperability and testing
- **Modular Components** within engines respect SRP while maintaining cohesion

## Proposed Architecture

```
DriftSDK (Shared Foundation)
├── Core Data Models (Pydantic)
├── Mathematical Libraries
├── Market Data Abstractions
├── Trading Primitives
└── Shared Utilities

Trading Engines (Strategy-Specific)
├── DeltaNeutralHedgingEngine
├── VolatilityArbitrageEngine  
├── RiskParityEngine
├── MomentumTradingEngine
└── [Future Strategy Engines]

Risk Management Layer (Cross-Cutting)
├── PortfolioRiskMonitor
├── LiquidationProtector
└── ComplianceValidator
```

### **Shared Foundation: DriftSDK Enhancement**

#### Core Mathematical Libraries
```python
# src/shared/drift/sdk/math/
class VaRCalculator:
    """Shared VaR calculations for all engines."""
    @staticmethod
    def historical_simulation(returns: List[float], confidence: float) -> float
    @staticmethod  
    def parametric_var(returns: List[float], confidence: float) -> float
    @staticmethod
    def monte_carlo_var(returns: List[float], confidence: float, simulations: int) -> float

class CorrelationCalculator:
    """Shared correlation calculations."""
    @staticmethod
    def pearson_correlation(x: List[float], y: List[float]) -> float
    @staticmethod
    def rolling_correlation(x: List[float], y: List[float], window: int) -> List[float]
    @staticmethod
    def correlation_matrix(returns_dict: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]

class VolatilityCalculator:
    """Shared volatility calculations."""
    @staticmethod
    def ewma_volatility(returns: List[float], lambda_param: float = 0.94) -> float
    @staticmethod
    def garch_volatility(returns: List[float]) -> float
    @staticmethod
    def realized_volatility(returns: List[float]) -> float
```

#### Shared Data Models
```python
# src/shared/drift/sdk/models/
@dataclass
class PortfolioState:
    """Shared portfolio state across all engines."""
    positions: List[Position]
    total_value: float
    unrealized_pnl: float
    margin_used: float
    health_ratio: float
    last_updated: datetime

@dataclass
class RiskMetrics:
    """Shared risk metrics."""
    var_1d: float
    var_7d: float
    portfolio_volatility: float
    max_drawdown: float
    sharpe_ratio: float
    correlation_matrix: Dict[str, Dict[str, float]]

@dataclass
class TradeSignal:
    """Shared trade signal format."""
    market: str
    side: str  # "buy" or "sell"
    size: float
    signal_type: str  # "hedge", "arbitrage", "momentum", etc.
    confidence: float
    reasoning: str
    metadata: Dict[str, Any]
```

#### Market Data Abstractions
```python
# src/shared/drift/sdk/data/
class MarketDataProvider:
    """Shared market data interface."""
    async def get_portfolio_state(self) -> PortfolioState
    async def get_market_summary(self, market: str) -> MarketSummary
    async def get_historical_returns(self, asset: str, days: int) -> List[float]
    async def get_orderbook_snapshot(self, market: str) -> OrderbookSnapshot

class RiskDataProvider:
    """Shared risk data calculations."""
    async def calculate_portfolio_risk(self) -> RiskMetrics
    async def get_correlation_matrix(self, assets: List[str], window: int) -> Dict[str, Dict[str, float]]
    async def detect_regime_changes(self, threshold: float) -> List[RegimeChange]
```

### **Specialized Trading Engines**

#### 1. Delta Neutral Hedging Engine
```python
# src/shared/drift/engines/delta_neutral/
class DeltaNeutralHedgingEngine:
    """Specialized engine for delta-neutral hedging strategies."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.delta_calculator = DeltaCalculator(drift_sdk)
        self.hedge_executor = HedgeExecutor(drift_sdk)
        self.effectiveness_monitor = EffectivenessMonitor(drift_sdk)
    
    async def calculate_hedge_requirements(self, target_delta: float = 0.0) -> HedgeRequirements:
        """Calculate hedge requirements using shared SDK components."""
        portfolio_state = await self.sdk.data.get_portfolio_state()
        current_delta = await self.delta_calculator.calculate_portfolio_delta(portfolio_state)
        
        if abs(current_delta - target_delta) <= self.delta_tolerance:
            return HedgeRequirements.no_hedging_needed()
        
        correlation_matrix = await self.sdk.data.get_correlation_matrix(
            [pos.market for pos in portfolio_state.positions], window=30
        )
        
        return await self.hedge_executor.calculate_optimal_hedges(
            current_delta, target_delta, correlation_matrix
        )

# Components within the engine maintain cohesion
class DeltaCalculator:
    """Delta calculation component - cohesive with hedging logic."""
    def __init__(self, sdk: DriftSDK):
        self.sdk = sdk
    
    async def calculate_portfolio_delta(self, portfolio_state: PortfolioState) -> float
    async def calculate_position_deltas(self, positions: List[Position]) -> Dict[str, float]

class HedgeExecutor:
    """Hedge execution component - cohesive with hedging logic."""
    async def calculate_optimal_hedges(self, current_delta: float, target_delta: float, correlations: Dict) -> HedgeRequirements
    async def execute_hedge_trades(self, requirements: HedgeRequirements) -> HedgeResult
```

#### 2. Volatility Arbitrage Engine
```python
# src/shared/drift/engines/volatility_arbitrage/
class VolatilityArbitrageEngine:
    """Specialized engine for volatility arbitrage strategies."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.vol_analyzer = VolatilityAnalyzer(drift_sdk)
        self.arbitrage_detector = ArbitrageDetector(drift_sdk)
        self.position_manager = VolArbitragePositionManager(drift_sdk)
    
    async def scan_for_opportunities(self) -> List[ArbitrageOpportunity]:
        """Scan for volatility arbitrage opportunities."""
        # Uses shared volatility calculations from SDK
        vol_surface = await self.vol_analyzer.calculate_volatility_surface()
        implied_vols = await self.vol_analyzer.get_implied_volatilities()
        
        return await self.arbitrage_detector.find_mispricing(vol_surface, implied_vols)
```

#### 3. Risk Parity Engine
```python
# src/shared/drift/engines/risk_parity/
class RiskParityEngine:
    """Specialized engine for risk parity strategies."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.risk_calculator = RiskParityCalculator(drift_sdk)
        self.rebalancer = RiskParityRebalancer(drift_sdk)
    
    async def calculate_target_allocations(self) -> Dict[str, float]:
        """Calculate risk parity target allocations."""
        # Uses shared risk calculations from SDK
        risk_metrics = await self.sdk.data.calculate_portfolio_risk()
        correlation_matrix = risk_metrics.correlation_matrix
        
        return await self.risk_calculator.optimize_risk_parity_weights(
            correlation_matrix, risk_metrics.portfolio_volatility
        )
```

### **Cross-Cutting Risk Management Layer**

#### Portfolio Risk Monitor (Shared Across All Engines)
```python
# src/shared/drift/risk_management/
class PortfolioRiskMonitor:
    """Cross-cutting risk monitoring for all engines."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.risk_limits = RiskLimits()
        self.alert_manager = AlertManager()
    
    async def validate_trade_signal(self, signal: TradeSignal) -> ValidationResult:
        """Validate any trade signal against risk limits."""
        portfolio_state = await self.sdk.data.get_portfolio_state()
        
        # Check position limits
        if self._would_exceed_position_limit(signal, portfolio_state):
            return ValidationResult.rejected("Position limit exceeded")
        
        # Check portfolio risk limits using shared calculations
        projected_risk = await self._calculate_projected_risk(signal, portfolio_state)
        if projected_risk.var_1d > self.risk_limits.max_var_1d:
            return ValidationResult.rejected("VaR limit exceeded")
        
        return ValidationResult.approved()
    
    async def monitor_real_time_risk(self) -> List[RiskAlert]:
        """Monitor portfolio risk in real-time."""
        current_risk = await self.sdk.data.calculate_portfolio_risk()
        
        alerts = []
        if current_risk.var_1d > self.risk_limits.max_var_1d:
            alerts.append(RiskAlert.var_breach(current_risk.var_1d, self.risk_limits.max_var_1d))
        
        return alerts
```

### **Engine Registry and Orchestration**

#### Engine Registry
```python
# src/shared/drift/registry/
class TradingEngineRegistry:
    """Registry for all trading engines."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.engines: Dict[str, TradingEngine] = {}
        self.risk_monitor = PortfolioRiskMonitor(drift_sdk)
    
    def register_engine(self, name: str, engine: TradingEngine) -> None:
        """Register a trading engine."""
        self.engines[name] = engine
    
    async def execute_strategy(self, engine_name: str, **kwargs) -> StrategyResult:
        """Execute a specific trading strategy with risk validation."""
        engine = self.engines[engine_name]
        
        # Generate trade signals
        signals = await engine.generate_signals(**kwargs)
        
        # Validate all signals through risk monitor
        validated_signals = []
        for signal in signals:
            validation = await self.risk_monitor.validate_trade_signal(signal)
            if validation.approved:
                validated_signals.append(signal)
        
        # Execute validated signals
        return await engine.execute_signals(validated_signals)
```

#### Multi-Engine Orchestrator
```python
# src/shared/drift/orchestrator/
class MultiEngineOrchestrator:
    """Orchestrate multiple trading engines."""
    
    def __init__(self, drift_sdk: DriftSDK):
        self.sdk = drift_sdk
        self.registry = TradingEngineRegistry(drift_sdk)
        self.conflict_resolver = SignalConflictResolver()
    
    async def run_all_strategies(self) -> OrchestrationResult:
        """Run all registered strategies and resolve conflicts."""
        all_signals = []
        
        # Collect signals from all engines
        for engine_name, engine in self.registry.engines.items():
            try:
                signals = await engine.generate_signals()
                all_signals.extend([(engine_name, signal) for signal in signals])
            except Exception as e:
                self.logger.error(f"Engine {engine_name} failed: {e}")
        
        # Resolve conflicts between engines
        resolved_signals = await self.conflict_resolver.resolve_conflicts(all_signals)
        
        # Execute resolved signals
        return await self._execute_resolved_signals(resolved_signals)
```

## **Benefits of This Architecture**

### **Maintains Component Cohesion**
- Related functionality (delta calculation + hedging) stays together
- Each engine is a cohesive unit focused on one strategy
- Shared components avoid duplication

### **Respects SRP at Engine Level**
- `DeltaNeutralHedgingEngine`: Single responsibility = delta-neutral hedging
- `VolatilityArbitrageEngine`: Single responsibility = volatility arbitrage
- `RiskParityEngine`: Single responsibility = risk parity allocation

### **Enables Strategy Diversity**
- Easy to add new trading strategies as separate engines
- Strategies can coexist and be orchestrated together
- Each strategy can have different risk parameters

### **Leverages DriftSDK Foundation**
- Mathematical calculations shared across all engines
- Common data models ensure consistency
- Shared utilities reduce code duplication

### **Supports Future Growth**
- New engines plug into existing infrastructure
- Cross-cutting concerns (risk, compliance) handled centrally
- Easy to test and validate new strategies

## **Implementation Strategy**

### **Phase 1: Enhance DriftSDK Foundation (Week 1-2)**
1. Extract mathematical libraries to SDK
2. Create shared data models
3. Implement market data abstractions
4. Add comprehensive unit tests

### **Phase 2: Create First Specialized Engine (Week 3-4)**
1. Implement `DeltaNeutralHedgingEngine` using SDK
2. Migrate existing hedging logic to new engine
3. Maintain backward compatibility through facade
4. Validate mathematical accuracy

### **Phase 3: Add Risk Management Layer (Week 5)**
1. Implement `PortfolioRiskMonitor`
2. Create engine registry and orchestration
3. Add cross-cutting risk validation
4. Test multi-engine scenarios

### **Phase 4: Additional Engines (Week 6-8)**
1. Implement `VolatilityArbitrageEngine`
2. Implement `RiskParityEngine`
3. Add conflict resolution between engines
4. Performance optimization

### **Phase 5: Production Migration (Week 9-10)**
1. Shadow mode testing with all engines
2. Gradual traffic migration
3. Performance monitoring and optimization
4. Documentation and training

## **Risk Mitigation**

### **Low-Risk Migration Path**
- Existing functionality preserved in first engine
- SDK enhancements don't affect production
- Shadow mode testing before any production changes
- Instant rollback capability maintained

### **Mathematical Accuracy**
- All SDK calculations validated against existing implementations
- Comprehensive test suite with statistical validation
- Shared libraries reduce risk of calculation errors

### **Performance Safety**
- Shared components optimized once, benefit all engines
- Lazy loading of unused engines
- Performance monitoring at engine level

## **Success Metrics**

### **Architecture Quality**
- **<300 LOC** per engine component (SRP compliance)
- **>95%** code reuse through SDK foundation
- **<5** dependencies per engine (loose coupling)
- **100%** test coverage for shared SDK components

### **Business Value**
- **Multiple trading strategies** operational simultaneously
- **<1 week** to implement new trading strategies
- **Zero production incidents** during migration
- **Improved risk management** across all strategies

## **Conclusion**

This architecture achieves the best of both worlds: **SRP compliance through specialized engines** while **maintaining component cohesion** within each strategy. The shared DriftSDK foundation eliminates duplication while enabling rapid development of new trading strategies.

The modular approach supports the long-term vision of multiple coexisting trading engines while maintaining the reliability and performance requirements of a production trading system.