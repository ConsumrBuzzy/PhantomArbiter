# ADR 008: Comprehensive Drift SDK Integration

**Status**: Proposed  
**Date**: 2026-01-16  
**Deciders**: Development Team  
**Technical Story**: Extend Drift Protocol integration for full trading platform capabilities

## Context

### Current State

Following the implementation of ADR 003 (Drift SDK Singleton Manager), we have successfully:
- ✅ Eliminated HTTP 429 rate limiting issues
- ✅ Fixed data loading/disappearing problems  
- ✅ Implemented singleton pattern with caching
- ✅ Established stable market data access

However, our current Drift SDK integration covers only **~30%** of the protocol's capabilities:

**Currently Implemented**:
- Basic market data (funding rates, prices)
- Simple position management (open/close)
- Account state fetching
- Basic deposit/withdraw operations

**Missing Critical Features**:
- Advanced order types (limit, stop-loss, take-profit)
- Portfolio management and analytics
- Risk management tools
- Liquidation protection
- Advanced market data (orderbook, trades, candles)
- Cross-margin and isolated margin modes
- Subaccount management
- Insurance fund interactions
- Governance and staking features

### Business Impact

Our limited SDK coverage restricts the platform's trading capabilities:

1. **Trading Limitations**
   - Only market orders supported
   - No advanced risk management
   - Limited position sizing strategies
   - No automated stop-losses

2. **User Experience Gaps**
   - Missing portfolio analytics
   - No liquidation warnings
   - Limited market depth visibility
   - No historical data access

3. **Competitive Disadvantage**
   - Other platforms offer full Drift integration
   - Users expect professional trading features
   - Limited arbitrage opportunities

4. **Technical Debt**
   - Workarounds for missing features
   - Inconsistent data access patterns
   - Manual implementations of SDK features

## Decision

We will implement a **Comprehensive Drift SDK Integration** that provides:

### 1. Full Trading Capabilities
- All order types (market, limit, stop, conditional)
- Advanced position management
- Risk management tools
- Portfolio analytics

### 2. Complete Market Data Access
- Real-time orderbook data
- Trade history and analytics
- OHLCV candle data
- Market statistics and metrics

### 3. Advanced Account Management
- Multi-subaccount support
- Cross-margin and isolated margin
- Liquidation protection
- Insurance fund monitoring

### 4. Professional Trading Features
- Automated risk management
- Portfolio rebalancing
- Performance analytics
- Backtesting capabilities

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PhantomArbiter Platform                      │
├─────────────────────────────────────────────────────────────────┤
│                     Trading Engines                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │   Funding   │ │     LST     │ │    Scalp    │ │    Arb    │ │
│  │   Engine    │ │   Engine    │ │   Engine    │ │  Engine   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                  Enhanced Drift Integration                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              DriftSDKManager (Singleton)                   │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────┐ │ │
│  │  │   Trading   │ │   Market    │ │  Account    │ │ Risk  │ │ │
│  │  │  Manager    │ │    Data     │ │  Manager    │ │  Mgmt │ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────┘ │ │
│  └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      Data Layer                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │   Cache     │ │  Database   │ │   Events    │ │  Metrics  │ │
│  │  Manager    │ │   Layer     │ │   System    │ │ Tracking  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                    Drift Protocol                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  DriftClient (Single)                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Components

### Component 1: Enhanced Trading Manager

```python
# src/shared/drift/trading_manager.py

class DriftTradingManager:
    """Comprehensive trading operations manager."""
    
    async def place_limit_order(
        self, 
        market: str, 
        side: str, 
        size: float, 
        price: float,
        time_in_force: str = "GTC",
        post_only: bool = False
    ) -> str:
        """Place limit order with advanced options."""
        
    async def place_stop_order(
        self,
        market: str,
        side: str, 
        size: float,
        trigger_price: float,
        limit_price: Optional[float] = None
    ) -> str:
        """Place stop-loss or take-profit order."""
        
    async def place_conditional_order(
        self,
        market: str,
        conditions: List[OrderCondition],
        order_params: OrderParams
    ) -> str:
        """Place conditional order with multiple triggers."""
        
    async def modify_order(
        self,
        order_id: str,
        new_price: Optional[float] = None,
        new_size: Optional[float] = None
    ) -> bool:
        """Modify existing order."""
        
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel specific order."""
        
    async def cancel_all_orders(self, market: Optional[str] = None) -> int:
        """Cancel all orders, optionally filtered by market."""
        
    async def get_open_orders(self, market: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        
    async def get_order_history(
        self, 
        market: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """Get order history with pagination."""
```
### Component 2: Advanced Market Data Manager

```python
# src/shared/drift/market_data_manager.py

class DriftMarketDataManager:
    """Comprehensive market data access."""
    
    async def get_orderbook(
        self, 
        market: str, 
        depth: int = 20
    ) -> OrderBook:
        """Get L2 orderbook with specified depth."""
        
    async def get_recent_trades(
        self,
        market: str,
        limit: int = 100
    ) -> List[Trade]:
        """Get recent trade history."""
        
    async def get_candles(
        self,
        market: str,
        resolution: str,  # "1m", "5m", "1h", "1d"
        from_time: datetime,
        to_time: datetime
    ) -> List[Candle]:
        """Get OHLCV candle data."""
        
    async def get_market_stats(self, market: str) -> MarketStats:
        """Get 24h market statistics."""
        
    async def get_funding_history(
        self,
        market: str,
        limit: int = 100
    ) -> List[FundingPayment]:
        """Get historical funding payments."""
        
    async def subscribe_to_trades(
        self,
        market: str,
        callback: Callable[[Trade], None]
    ) -> str:
        """Subscribe to real-time trade updates."""
        
    async def subscribe_to_orderbook(
        self,
        market: str,
        callback: Callable[[OrderBook], None]
    ) -> str:
        """Subscribe to real-time orderbook updates."""
```

### Component 3: Portfolio & Risk Manager

```python
# src/shared/drift/portfolio_manager.py

class DriftPortfolioManager:
    """Portfolio analytics and risk management."""
    
    async def get_portfolio_summary(self) -> PortfolioSummary:
        """Get comprehensive portfolio overview."""
        
    async def calculate_portfolio_risk(self) -> RiskMetrics:
        """Calculate VaR, max drawdown, Sharpe ratio, etc."""
        
    async def get_pnl_breakdown(
        self,
        period: str = "24h"
    ) -> PnLBreakdown:
        """Get P&L breakdown by market and time."""
        
    async def set_risk_limits(self, limits: RiskLimits) -> bool:
        """Set portfolio-wide risk limits."""
        
    async def check_risk_limits(self) -> List[RiskViolation]:
        """Check current positions against risk limits."""
        
    async def auto_hedge_portfolio(
        self,
        target_delta: float = 0.0,
        max_trades: int = 5
    ) -> List[str]:
        """Automatically hedge portfolio to target delta."""
        
    async def calculate_liquidation_risk(self) -> LiquidationRisk:
        """Calculate liquidation prices and risk levels."""
        
    async def suggest_position_sizes(
        self,
        market: str,
        strategy: str,
        risk_tolerance: float
    ) -> PositionSizing:
        """Suggest optimal position sizes based on risk."""
```

### Component 4: Advanced Account Manager

```python
# src/shared/drift/account_manager.py

class DriftAccountManager:
    """Advanced account and subaccount management."""
    
    async def create_subaccount(self, name: str) -> int:
        """Create new subaccount."""
        
    async def list_subaccounts(self) -> List[SubAccount]:
        """List all subaccounts with balances."""
        
    async def transfer_between_subaccounts(
        self,
        from_subaccount: int,
        to_subaccount: int,
        asset: str,
        amount: float
    ) -> str:
        """Transfer assets between subaccounts."""
        
    async def set_margin_mode(
        self,
        subaccount: int,
        mode: str  # "cross" or "isolated"
    ) -> bool:
        """Set margin mode for subaccount."""
        
    async def get_margin_requirements(
        self,
        subaccount: int
    ) -> MarginRequirements:
        """Get detailed margin requirements."""
        
    async def simulate_liquidation(
        self,
        price_changes: Dict[str, float]
    ) -> LiquidationSimulation:
        """Simulate liquidation under price scenarios."""
        
    async def get_insurance_fund_status(self) -> InsuranceFundStatus:
        """Get insurance fund balance and health."""
```

## Implementation Plan

### Phase 1: Enhanced Trading Operations (Week 1)
**Priority**: High - Core trading functionality

**Tasks**:
1. Implement `DriftTradingManager` with all order types
2. Add order modification and cancellation
3. Implement order history and status tracking
4. Add comprehensive error handling
5. Create property-based tests for trading operations

**Deliverables**:
- Full order lifecycle management
- Support for limit, stop, and conditional orders
- Order book integration
- Trading analytics

### Phase 2: Advanced Market Data (Week 2)  
**Priority**: High - Essential for informed trading

**Tasks**:
1. Implement `DriftMarketDataManager`
2. Add real-time orderbook subscriptions
3. Implement trade history and candle data
4. Add market statistics and metrics
5. Create data streaming infrastructure

**Deliverables**:
- Real-time market data feeds
- Historical data access
- Market depth analysis
- Trading volume analytics

### Phase 3: Portfolio & Risk Management (Week 3)
**Priority**: Medium - Risk management and analytics

**Tasks**:
1. Implement `DriftPortfolioManager`
2. Add risk calculation engines
3. Implement automated hedging
4. Add liquidation risk monitoring
5. Create portfolio analytics dashboard

**Deliverables**:
- Comprehensive risk metrics
- Automated portfolio rebalancing
- Liquidation protection
- Performance analytics

### Phase 4: Advanced Account Features (Week 4)
**Priority**: Medium - Advanced account management

**Tasks**:
1. Implement `DriftAccountManager`
2. Add subaccount management
3. Implement margin mode controls
4. Add insurance fund monitoring
5. Create account analytics

**Deliverables**:
- Multi-subaccount support
- Advanced margin controls
- Account risk monitoring
- Insurance fund integration

### Phase 5: Integration & Testing (Week 5)
**Priority**: High - System integration and validation

**Tasks**:
1. Integrate all components with existing engines
2. Comprehensive testing suite
3. Performance optimization
4. Documentation and examples
5. Production deployment

**Deliverables**:
- Fully integrated system
- Complete test coverage
- Performance benchmarks
- User documentation

## Technical Specifications

### Data Models

```python
# Core data structures for enhanced integration

@dataclass
class OrderBook:
    market: str
    bids: List[Tuple[float, float]]  # [(price, size), ...]
    asks: List[Tuple[float, float]]
    timestamp: datetime
    sequence: int

@dataclass  
class Trade:
    market: str
    price: float
    size: float
    side: str  # "buy" or "sell"
    timestamp: datetime
    trade_id: str

@dataclass
class Candle:
    market: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    resolution: str

@dataclass
class PortfolioSummary:
    total_value: float
    unrealized_pnl: float
    realized_pnl: float
    margin_used: float
    margin_available: float
    positions: List[Position]
    open_orders: List[Order]

@dataclass
class RiskMetrics:
    var_1d: float  # 1-day Value at Risk
    var_7d: float  # 7-day Value at Risk
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    beta: float
    correlation_matrix: Dict[str, Dict[str, float]]

@dataclass
class LiquidationRisk:
    health_ratio: float
    liquidation_price: Dict[str, float]  # per market
    time_to_liquidation: Optional[timedelta]
    risk_level: str  # "low", "medium", "high", "critical"
```

### API Extensions

```python
# Extended DriftAdapter with full capabilities

class EnhancedDriftAdapter(DriftAdapter):
    """Enhanced adapter with full Drift SDK coverage."""
    
    def __init__(self, network: str = "mainnet"):
        super().__init__(network)
        self.trading = DriftTradingManager(self)
        self.market_data = DriftMarketDataManager(self)
        self.portfolio = DriftPortfolioManager(self)
        self.account = DriftAccountManager(self)
    
    # Backward compatibility maintained
    # All existing methods continue to work
    
    # New comprehensive capabilities
    async def get_comprehensive_state(self) -> ComprehensiveState:
        """Get complete account and market state."""
        
    async def execute_strategy(
        self,
        strategy: TradingStrategy,
        parameters: Dict[str, Any]
    ) -> StrategyResult:
        """Execute complex trading strategy."""
        
    async def backtest_strategy(
        self,
        strategy: TradingStrategy,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestResult:
        """Backtest strategy on historical data."""
```

## Integration with Existing Systems

### Engine Integration

```python
# Enhanced Funding Engine with full capabilities

class EnhancedFundingEngine(FundingEngine):
    """Funding engine with advanced Drift integration."""
    
    async def start(self):
        # Use enhanced adapter
        self.drift_adapter = EnhancedDriftAdapter(network="mainnet")
        await super().start()
    
    async def execute_advanced_rebalancing(self):
        """Advanced rebalancing with limit orders and risk management."""
        
        # Get comprehensive portfolio state
        portfolio = await self.drift_adapter.portfolio.get_portfolio_summary()
        risk_metrics = await self.drift_adapter.portfolio.calculate_portfolio_risk()
        
        # Check risk limits before trading
        violations = await self.drift_adapter.portfolio.check_risk_limits()
        if violations:
            Logger.warning(f"Risk violations detected: {violations}")
            return
        
        # Calculate optimal rebalancing with advanced sizing
        sizing = await self.drift_adapter.portfolio.suggest_position_sizes(
            market="SOL-PERP",
            strategy="delta_neutral",
            risk_tolerance=0.02
        )
        
        # Execute with limit orders for better fills
        if sizing.recommended_size > 0:
            order_id = await self.drift_adapter.trading.place_limit_order(
                market="SOL-PERP",
                side="sell" if sizing.direction == "short" else "buy",
                size=sizing.recommended_size,
                price=sizing.optimal_price,
                post_only=True  # Maker order for rebates
            )
            
            # Set stop-loss for risk management
            await self.drift_adapter.trading.place_stop_order(
                market="SOL-PERP",
                side="buy" if sizing.direction == "short" else "sell",
                size=sizing.recommended_size,
                trigger_price=sizing.stop_loss_price
            )
```

### Dashboard Integration

```python
# Enhanced dashboard with comprehensive data

class EnhancedDashboardServer(DashboardServer):
    """Dashboard with full Drift integration."""
    
    async def get_enhanced_market_data(self):
        """Get comprehensive market data for dashboard."""
        
        markets = []
        for market in ["SOL-PERP", "BTC-PERP", "ETH-PERP"]:
            # Get enhanced market data
            orderbook = await drift_adapter.market_data.get_orderbook(market)
            trades = await drift_adapter.market_data.get_recent_trades(market)
            stats = await drift_adapter.market_data.get_market_stats(market)
            funding_history = await drift_adapter.market_data.get_funding_history(market)
            
            markets.append({
                "symbol": market,
                "orderbook": orderbook,
                "recent_trades": trades,
                "stats": stats,
                "funding_history": funding_history
            })
        
        return markets
    
    async def get_portfolio_analytics(self):
        """Get comprehensive portfolio analytics."""
        
        portfolio = await drift_adapter.portfolio.get_portfolio_summary()
        risk_metrics = await drift_adapter.portfolio.calculate_portfolio_risk()
        liquidation_risk = await drift_adapter.portfolio.calculate_liquidation_risk()
        
        return {
            "portfolio": portfolio,
            "risk": risk_metrics,
            "liquidation": liquidation_risk
        }
```

## Performance Considerations

### Caching Strategy

```python
# Enhanced caching for comprehensive data

class EnhancedCacheManager(CacheManager):
    """Enhanced caching with different TTLs for different data types."""
    
    CACHE_TTLS = {
        # Real-time data (short TTL)
        "orderbook": 1,      # 1 second
        "trades": 5,         # 5 seconds  
        "prices": 2,         # 2 seconds
        
        # Market data (medium TTL)
        "funding_rates": 30,  # 30 seconds
        "market_stats": 60,   # 1 minute
        "candles": 300,       # 5 minutes
        
        # Account data (longer TTL)
        "portfolio": 10,      # 10 seconds
        "positions": 5,       # 5 seconds
        "orders": 2,          # 2 seconds
        
        # Static data (long TTL)
        "market_info": 3600,  # 1 hour
        "risk_params": 1800,  # 30 minutes
    }
```

### Rate Limiting

```python
# Intelligent rate limiting for API calls

class RateLimitManager:
    """Manage API rate limits intelligently."""
    
    def __init__(self):
        self.limits = {
            "market_data": RateLimit(100, 60),    # 100 calls per minute
            "trading": RateLimit(50, 60),         # 50 trades per minute  
            "account": RateLimit(200, 60),        # 200 account calls per minute
        }
    
    async def acquire(self, category: str) -> bool:
        """Acquire rate limit token."""
        
    async def wait_if_needed(self, category: str):
        """Wait if rate limit exceeded."""
```

## Testing Strategy

### Property-Based Testing

```python
# Comprehensive property-based tests

class TestEnhancedDriftIntegration:
    """Property-based tests for enhanced integration."""
    
    @given(
        market=st.sampled_from(["SOL-PERP", "BTC-PERP", "ETH-PERP"]),
        side=st.sampled_from(["buy", "sell"]),
        size=st.floats(min_value=0.001, max_value=10.0),
        price=st.floats(min_value=1.0, max_value=1000.0)
    )
    async def test_limit_order_properties(self, market, side, size, price):
        """Test limit order properties hold for all inputs."""
        
        # Property: Order placement should always return valid order ID
        order_id = await trading_manager.place_limit_order(market, side, size, price)
        assert isinstance(order_id, str)
        assert len(order_id) > 0
        
        # Property: Order should appear in open orders
        open_orders = await trading_manager.get_open_orders(market)
        assert any(order.id == order_id for order in open_orders)
        
        # Property: Order cancellation should succeed
        success = await trading_manager.cancel_order(order_id)
        assert success is True
    
    @given(
        portfolio_value=st.floats(min_value=100.0, max_value=100000.0),
        risk_tolerance=st.floats(min_value=0.01, max_value=0.1)
    )
    async def test_risk_management_properties(self, portfolio_value, risk_tolerance):
        """Test risk management properties."""
        
        # Property: Risk limits should never be exceeded
        limits = RiskLimits(max_portfolio_risk=risk_tolerance)
        await portfolio_manager.set_risk_limits(limits)
        
        violations = await portfolio_manager.check_risk_limits()
        
        # Property: No violations should exist after setting limits
        assert len(violations) == 0
```

### Integration Testing

```python
# End-to-end integration tests

class TestFullIntegration:
    """Test complete system integration."""
    
    async def test_complete_trading_workflow(self):
        """Test complete trading workflow from market data to execution."""
        
        # 1. Get market data
        orderbook = await market_data_manager.get_orderbook("SOL-PERP")
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        
        # 2. Calculate position size
        sizing = await portfolio_manager.suggest_position_sizes(
            market="SOL-PERP",
            strategy="mean_reversion",
            risk_tolerance=0.02
        )
        
        # 3. Place order
        order_id = await trading_manager.place_limit_order(
            market="SOL-PERP",
            side="buy",
            size=sizing.recommended_size,
            price=sizing.optimal_price
        )
        
        # 4. Monitor execution
        order = await trading_manager.get_order_status(order_id)
        assert order.status in ["open", "filled", "cancelled"]
        
        # 5. Risk management
        risk = await portfolio_manager.calculate_portfolio_risk()
        assert risk.var_1d < sizing.max_risk
```

## Migration Path

### Phase 1: Non-Breaking Extension (Week 1)
- Add new managers alongside existing code
- No changes to current functionality
- Comprehensive testing of new components

### Phase 2: Gradual Integration (Week 2-3)  
- Update engines to use enhanced features optionally
- Maintain backward compatibility
- Feature flags for gradual rollout

### Phase 3: Full Migration (Week 4-5)
- Replace old implementations with enhanced versions
- Remove deprecated code paths
- Complete documentation update

## Success Metrics

### Coverage Metrics
- **Before**: ~30% of Drift SDK capabilities
- **After**: ~95% of Drift SDK capabilities

### Performance Metrics
- **Order Execution**: <100ms average latency
- **Market Data**: <50ms update latency  
- **Risk Calculations**: <200ms for full portfolio
- **Cache Hit Rate**: >90% for frequently accessed data

### Reliability Metrics
- **Uptime**: >99.9% for trading operations
- **Error Rate**: <0.1% for API calls
- **Data Accuracy**: 100% consistency with Drift Protocol

### Business Metrics
- **Trading Volume**: 10x increase in supported strategies
- **Risk Management**: 50% reduction in liquidation risk
- **User Satisfaction**: Professional-grade trading capabilities
- **Competitive Position**: Feature parity with leading platforms

## Risks and Mitigations

### Technical Risks

1. **Complexity Increase**
   - **Risk**: System becomes harder to maintain
   - **Mitigation**: Comprehensive documentation, modular design, extensive testing

2. **Performance Impact**  
   - **Risk**: More features = slower performance
   - **Mitigation**: Intelligent caching, rate limiting, performance monitoring

3. **Integration Challenges**
   - **Risk**: New components don't integrate smoothly
   - **Mitigation**: Phased rollout, backward compatibility, feature flags

### Business Risks

1. **Development Time**
   - **Risk**: Takes longer than expected
   - **Mitigation**: Phased delivery, MVP approach, parallel development

2. **User Adoption**
   - **Risk**: Users don't utilize new features
   - **Mitigation**: User education, gradual feature introduction, feedback loops

3. **Maintenance Overhead**
   - **Risk**: More code to maintain
   - **Mitigation**: Automated testing, monitoring, documentation

## Alternatives Considered

### Alternative 1: Gradual Feature Addition
**Description**: Add features one by one as needed

**Pros**: Lower risk, incremental value
**Cons**: Inconsistent architecture, technical debt

**Rejected**: Leads to fragmented implementation

### Alternative 2: Third-Party Integration Layer
**Description**: Use existing Drift integration library

**Pros**: Faster implementation, maintained by others
**Cons**: Less control, potential vendor lock-in

**Rejected**: Need custom features for our use case

### Alternative 3: Minimal Integration
**Description**: Keep current limited integration

**Pros**: No additional complexity
**Cons**: Competitive disadvantage, limited capabilities

**Rejected**: Business requirements demand full capabilities

## Conclusion

This comprehensive Drift SDK integration will transform PhantomArbiter from a basic trading platform into a professional-grade trading system with full Drift Protocol capabilities. The phased implementation approach ensures minimal risk while delivering maximum value.

The enhanced integration will enable:
- **Advanced Trading Strategies**: Full order type support and risk management
- **Professional Analytics**: Comprehensive portfolio and risk metrics  
- **Competitive Advantage**: Feature parity with leading trading platforms
- **Future Growth**: Foundation for additional protocol integrations

**Estimated Timeline**: 5 weeks for complete implementation
**Estimated Effort**: 200-250 developer hours
**Expected ROI**: 10x increase in platform capabilities

---

**Approved By**: _Pending_  
**Implementation Start**: _Pending_  
**Implementation Complete**: _Pending_  
**Deployed to Production**: _Pending_

## References

- [Drift Protocol Documentation](https://docs.drift.trade/)
- [driftpy SDK Reference](https://github.com/drift-labs/driftpy)
- ADR 003: Drift SDK Singleton Manager
- Current Implementation: `src/shared/drift/`
- Related Specs: `.kiro/specs/drift-sdk-singleton/`

## Appendix

### A. Current vs Proposed Feature Matrix

| Feature Category | Current | Proposed | Impact |
|-----------------|---------|----------|---------|
| Order Types | Market only | All types | High |
| Market Data | Basic | Comprehensive | High |
| Risk Management | None | Full suite | Critical |
| Portfolio Analytics | Basic | Professional | High |
| Account Management | Single | Multi-subaccount | Medium |
| Historical Data | None | Full access | Medium |
| Real-time Feeds | Limited | Complete | High |

### B. Implementation Checklist

- [ ] Phase 1: Enhanced Trading Operations
  - [ ] DriftTradingManager implementation
  - [ ] All order types support
  - [ ] Order lifecycle management
  - [ ] Error handling and recovery
  - [ ] Property-based testing

- [ ] Phase 2: Advanced Market Data
  - [ ] DriftMarketDataManager implementation  
  - [ ] Real-time data subscriptions
  - [ ] Historical data access
  - [ ] Market analytics
  - [ ] Performance optimization

- [ ] Phase 3: Portfolio & Risk Management
  - [ ] DriftPortfolioManager implementation
  - [ ] Risk calculation engines
  - [ ] Automated hedging
  - [ ] Liquidation protection
  - [ ] Analytics dashboard

- [ ] Phase 4: Advanced Account Features
  - [ ] DriftAccountManager implementation
  - [ ] Subaccount management
  - [ ] Margin controls
  - [ ] Insurance fund integration
  - [ ] Account analytics

- [ ] Phase 5: Integration & Testing
  - [ ] Engine integration
  - [ ] Dashboard integration
  - [ ] Comprehensive testing
  - [ ] Performance benchmarking
  - [ ] Documentation
  - [ ] Production deployment

### C. Performance Benchmarks

| Operation | Current | Target | Improvement |
|-----------|---------|--------|-------------|
| Market Data Fetch | 500ms | 50ms | 10x faster |
| Order Placement | 1000ms | 100ms | 10x faster |
| Portfolio Calc | N/A | 200ms | New capability |
| Risk Analysis | N/A | 100ms | New capability |
| Cache Hit Rate | 70% | 90% | 20% improvement |