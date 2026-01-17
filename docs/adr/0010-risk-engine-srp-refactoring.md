# ADR-0010: Risk Engine SRP Refactoring

## Status
Proposed

## Context

The `DriftRiskEngine` class has grown into a monolithic component with over 1,800 lines of code, violating the Single Responsibility Principle (SRP). The current implementation handles multiple distinct responsibilities:

1. **Value at Risk (VaR) Calculations** (6 methods, ~400 LOC)
2. **Performance Metrics & Drawdown Analysis** (3 methods, ~300 LOC)
3. **Correlation Analysis & Regime Detection** (8 methods, ~450 LOC)
4. **Volatility Modeling & Forecasting** (7 methods, ~350 LOC)
5. **Beta Analysis & Multi-Factor Models** (8 methods, ~400 LOC)
6. **Risk Monitoring & Alerting** (2 methods, ~100 LOC)
7. **Data Management & Utilities** (4 methods, ~200 LOC)

This monolithic structure creates several problems:
- **Mathematical Complexity**: Different risk models mixed in single class
- **Testing Challenges**: Difficult to test individual risk calculations
- **Performance Issues**: All calculations loaded even when only subset needed
- **Model Validation**: Hard to validate individual risk models independently
- **Extensibility**: Adding new risk models requires modifying core class

## Decision

We will refactor the `DriftRiskEngine` into a modular architecture following SOLID principles, with specialized components for different risk calculation domains.

### Proposed Architecture

```
DriftRiskEngine (Orchestrator)
├── VaRCalculationEngine
├── PerformanceAnalyzer
├── CorrelationAnalyzer
├── VolatilityModeler
├── BetaAnalyzer
├── RiskMonitor
└── MarketDataProvider
```

### Component Breakdown

#### 1. VaRCalculationEngine
**Responsibility**: All Value at Risk calculations and backtesting
```python
class VaRCalculationEngine:
    async def calculate_var(confidence_level: float, horizon_days: int, method: str) -> VaRResult
    def calculate_historical_var(returns: List[float], confidence_level: float) -> float
    def calculate_parametric_var(returns: List[float], confidence_level: float) -> float
    def calculate_monte_carlo_var(returns: List[float], confidence_level: float) -> float
    async def backtest_var(var_results: List[VaRResult], actual_returns: List[float]) -> Dict
    def kupiec_test(violations: int, observations: int, expected_rate: float) -> Tuple[float, float]
```

#### 2. PerformanceAnalyzer
**Responsibility**: Performance metrics and drawdown analysis
```python
class PerformanceAnalyzer:
    async def calculate_performance_metrics() -> PerformanceMetrics
    async def calculate_drawdown_analysis() -> DrawdownAnalysis
    def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float) -> float
    def calculate_sortino_ratio(returns: List[float], risk_free_rate: float) -> float
    def calculate_calmar_ratio(returns: List[float], max_drawdown: float) -> float
    def calculate_information_ratio(returns: List[float], benchmark_returns: List[float]) -> float
```

#### 3. CorrelationAnalyzer
**Responsibility**: Correlation calculations and regime detection
```python
class CorrelationAnalyzer:
    async def calculate_correlation_matrix(window_days: int, method: str) -> CorrelationMatrix
    def calculate_correlation(returns1: List[float], returns2: List[float], method: str) -> float
    def calculate_ranks(values: List[float]) -> List[float]  # For Spearman
    def store_correlation_history(correlation_matrix: CorrelationMatrix) -> None
    async def get_correlation_trends(asset1: str, asset2: str, lookback_periods: int) -> Dict
    async def detect_correlation_regime_changes(threshold: float) -> List[Dict[str, Any]]
    def calculate_rolling_correlation(returns_x: List[float], returns_y: List[float]) -> List[float]
    def calculate_dynamic_correlation(returns_matrix: np.ndarray) -> np.ndarray
```

#### 4. VolatilityModeler
**Responsibility**: Volatility calculations, modeling, and forecasting
```python
class VolatilityModeler:
    async def calculate_volatility_metrics(method: str) -> VolatilityMetrics
    def calculate_ewma_volatility(returns: List[float], lambda_param: float) -> float
    def calculate_garch_volatility(returns: List[float]) -> float
    def forecast_volatility(returns: List[float], method: str, horizon_days: int) -> float
    async def calculate_volatility_surface(assets: List[str]) -> Dict[str, Dict[str, float]]
    async def detect_volatility_regime_changes(threshold_multiplier: float) -> List[Dict[str, Any]]
    def calculate_realized_volatility(high_freq_returns: List[float]) -> float
```

#### 5. BetaAnalyzer
**Responsibility**: Beta calculations and multi-factor models
```python
class BetaAnalyzer:
    async def calculate_beta_analysis(window_days: int) -> BetaAnalysis
    def calculate_beta(portfolio_returns: List[float], benchmark_returns: List[float]) -> Tuple[float, float, float]
    async def calculate_rolling_beta(benchmark: str, window_days: int, step_days: int) -> Dict[str, List[float]]
    async def analyze_beta_stability(lookback_periods: int) -> Dict[str, Any]
    async def calculate_multi_factor_beta() -> Dict[str, Any]
    async def create_size_factor(length: int) -> List[float]
    async def create_momentum_factor(length: int) -> List[float]
    def calculate_factor_loadings(returns: List[float], factors: Dict[str, List[float]]) -> Dict[str, float]
```

#### 6. RiskMonitor
**Responsibility**: Risk change monitoring and alerting
```python
class RiskMonitor:
    async def monitor_risk_changes() -> List[RiskChangeAlert]
    def set_alert_thresholds(thresholds: Dict[str, float]) -> None
    def generate_risk_alert(alert_type: str, current_value: float, previous_value: float) -> RiskChangeAlert
    async def assess_portfolio_stress(stress_scenarios: List[Dict]) -> Dict[str, Any]
    def calculate_risk_contribution(positions: List[Dict]) -> Dict[str, float]
```

#### 7. MarketDataProvider
**Responsibility**: Data management and utilities
```python
class MarketDataProvider:
    async def get_portfolio_returns() -> List[float]
    async def get_portfolio_value_history() -> List[Dict[str, Any]]
    async def get_benchmark_returns(benchmark: str, window_days: int) -> List[float]
    async def get_asset_returns(asset: str, window_days: int) -> List[float]
    def validate_return_data(returns: List[float]) -> bool
    def clean_return_data(returns: List[float]) -> List[float]
    def cache_market_data(key: str, data: Any, ttl: int) -> None
    def get_cached_data(key: str) -> Optional[Any]
```

### Orchestrator Pattern

The main `DriftRiskEngine` becomes a lightweight orchestrator:

```python
class DriftRiskEngine:
    def __init__(self, drift_adapter, lookback_days: int = 252):
        self.data_provider = MarketDataProvider(drift_adapter, lookback_days)
        self.var_engine = VaRCalculationEngine(self.data_provider)
        self.performance_analyzer = PerformanceAnalyzer(self.data_provider)
        self.correlation_analyzer = CorrelationAnalyzer(self.data_provider)
        self.volatility_modeler = VolatilityModeler(self.data_provider)
        self.beta_analyzer = BetaAnalyzer(self.data_provider)
        self.risk_monitor = RiskMonitor()
    
    async def calculate_var(self, confidence_level: float = 0.95, horizon_days: int = 1, method: str = "historical_simulation") -> VaRResult:
        return await self.var_engine.calculate_var(confidence_level, horizon_days, method)
    
    async def calculate_performance_metrics(self) -> PerformanceMetrics:
        return await self.performance_analyzer.calculate_performance_metrics()
```

## Implementation Strategy

### Phase 1: Extract Mathematical Engines (Week 1)
1. Create `VaRCalculationEngine` with all VaR methods and backtesting
2. Create `VolatilityModeler` with EWMA, GARCH, and forecasting
3. Implement comprehensive unit tests for mathematical accuracy
4. Validate against existing calculations

### Phase 2: Extract Analysis Components (Week 2)
1. Create `PerformanceAnalyzer` with metrics and drawdown analysis
2. Create `BetaAnalyzer` with beta calculations and multi-factor models
3. Add statistical validation tests
4. Benchmark performance against current implementation

### Phase 3: Extract Correlation & Monitoring (Week 3)
1. Create `CorrelationAnalyzer` with correlation calculations and regime detection
2. Create `RiskMonitor` with alerting and change detection
3. Implement regime change detection tests
4. Add correlation stability validation

### Phase 4: Extract Data Layer (Week 4)
1. Create `MarketDataProvider` with all data management
2. Implement caching and data validation
3. Add data quality checks and cleaning
4. Optimize data access patterns

### Phase 5: Integration & Optimization (Week 5)
1. Optimize component interactions and data flow
2. Implement lazy loading for expensive calculations
3. Add comprehensive integration tests
4. Performance tuning and memory optimization

## Advanced Features

### Calculation Pipelines
```python
class RiskCalculationPipeline:
    def __init__(self, components: List[RiskComponent]):
        self.components = components
    
    async def execute_pipeline(self, portfolio_data: Dict) -> RiskReport:
        results = {}
        for component in self.components:
            results[component.name] = await component.calculate(portfolio_data)
        return RiskReport(results)
```

### Model Validation Framework
```python
class ModelValidator:
    def validate_var_model(self, var_engine: VaRCalculationEngine, test_data: List[float]) -> ValidationResult
    def validate_volatility_model(self, vol_modeler: VolatilityModeler, test_data: List[float]) -> ValidationResult
    def cross_validate_models(self, models: List[RiskModel], data: List[float]) -> Dict[str, ValidationResult]
```

### Risk Model Registry
```python
class RiskModelRegistry:
    def register_var_model(self, name: str, model: VaRModel) -> None
    def register_volatility_model(self, name: str, model: VolatilityModel) -> None
    def get_model(self, model_type: str, model_name: str) -> RiskModel
    def list_available_models(self, model_type: str) -> List[str]
```

## Benefits

### Immediate Benefits
- **Mathematical Accuracy**: Isolated risk models easier to validate
- **Performance**: Load only needed components
- **Testability**: Unit test individual risk calculations
- **Maintainability**: Changes to one model don't affect others

### Long-term Benefits
- **Model Innovation**: Easy to add new risk models
- **Regulatory Compliance**: Individual model validation and documentation
- **Scalability**: Components can be distributed or cached independently
- **Research Integration**: Academic risk models can be plugged in easily

## Risks and Mitigations

### Risk: Mathematical Consistency
**Mitigation**: Comprehensive cross-validation tests between components

### Risk: Performance Degradation
**Mitigation**: Implement intelligent caching and lazy evaluation

### Risk: Model Validation Complexity
**Mitigation**: Automated validation framework with statistical tests

### Risk: Data Consistency
**Mitigation**: Centralized data provider with validation and cleaning

## Dependencies

- **NumPy**: For mathematical operations (existing)
- **SciPy**: For statistical functions (existing, optional)
- **Pydantic v2**: For data validation across components
- **Loguru**: For structured logging in each component

## Success Metrics

- **Mathematical Accuracy**: All models pass statistical validation tests
- **Performance**: <20% overhead compared to monolithic implementation
- **Code Coverage**: >98% for mathematical components
- **Model Validation**: Automated backtesting for all VaR models
- **Memory Efficiency**: Lazy loading reduces baseline memory by 40%

## Migration Path

### For Existing Code
```python
# Before
risk_engine = DriftRiskEngine(drift_adapter)
var_result = await risk_engine.calculate_var()

# After (backward compatible)
risk_engine = DriftRiskEngine(drift_adapter)
var_result = await risk_engine.calculate_var()  # Same interface

# New usage (optional)
var_engine = risk_engine.var_engine
custom_var = await var_engine.calculate_monte_carlo_var(returns, 0.99, 1, 50000)
```

### Advanced Usage
```python
# Custom risk pipeline
pipeline = RiskCalculationPipeline([
    risk_engine.var_engine,
    risk_engine.volatility_modeler,
    risk_engine.correlation_analyzer
])
risk_report = await pipeline.execute_pipeline(portfolio_data)

# Model validation
validator = ModelValidator()
var_validation = validator.validate_var_model(risk_engine.var_engine, test_returns)
```

## Regulatory Considerations

### Model Risk Management
- Each component maintains model documentation
- Automated backtesting and validation
- Model performance monitoring
- Change control for model updates

### Audit Trail
- All calculations logged with input parameters
- Model version tracking
- Performance metrics stored for regulatory review
- Exception handling and error reporting

## Conclusion

This refactoring will transform the monolithic `DriftRiskEngine` into a sophisticated, modular risk management system that meets both current needs and future regulatory requirements. The component-based architecture enables advanced features like model validation, custom risk pipelines, and regulatory compliance while maintaining mathematical accuracy and performance.