# ADR-0006: Modular Drift Engine Architecture

**Status**: Proposed  
**Date**: 2026-01-15  
**Context**: "Strategy-Agnostic Perpetual Trading Engine"

---

## Context

PhantomArbiter currently has a **tightly-coupled** implementation for Drift Protocol trading in `src/delta_neutral/`. This module works well for the Delta Neutral funding rate strategy but creates barriers for implementing additional perpetual trading strategies.

### Current State

```
src/delta_neutral/
├── engine.py              ← DeltaNeutralEngine (strategy-specific)
├── neutrality_monitor.py  ← Delta drift detection (strategy-specific)
├── sync_execution.py      ← Jito bundling (REUSABLE)
├── drift_order_builder.py ← Order primitives (REUSABLE)
├── safety_gates.py        ← Risk controls (REUSABLE)
└── types.py               ← Data types (REUSABLE)
```

### The Problem

1. **Single Strategy Lock-in**: Engine is hardcoded to delta-neutral logic
2. **Code Duplication Risk**: New strategies would duplicate execution/risk code
3. **Dashboard Integration Gap**: No unified engine interface for UI pipeline
4. **Testing Complexity**: Can't test strategies in isolation from execution

### Drift Protocol Strategies Worth Supporting

| Strategy | Description | Risk Profile |
|:---------|:------------|:-------------|
| Delta Neutral | Spot + Perp hedge, collect funding | Low |
| Funding Farm | Directional based on 8-hour funding rates | Medium |
| Basis Trade | Arb spot vs perp price divergence | Low-Medium |
| Directional | Long/short on signals (e.g., sentiment) | High |
| Market Making | Provide liquidity on Drift CLOB | Medium |

---

## Decision

### Adopt Strategy Pattern with Layered Architecture

```
src/drift_engine/
├── core/                          ← Layer 1: Protocol Primitives
│   ├── client.py                  ← DriftClient (RPC + Gateway API)
│   ├── position_manager.py        ← Position CRUD operations
│   ├── margin_monitor.py          ← Health/liquidation metrics
│   └── types.py                   ← Shared dataclasses
│
├── strategies/                    ← Layer 2: Strategy Implementations
│   ├── base.py                    ← DriftStrategy (ABC interface)
│   ├── delta_neutral/             ← Migrated from src/delta_neutral/
│   │   ├── strategy.py
│   │   └── neutrality_monitor.py
│   ├── funding_farm/              ← Future
│   │   └── strategy.py
│   └── directional/               ← Future
│       └── strategy.py
│
├── execution/                     ← Layer 3: Trade Execution
│   ├── sync_executor.py           ← Atomic Jito bundling
│   ├── safety_gates.py            ← Risk controls
│   └── latency_monitor.py
│
└── engine.py                      ← Layer 4: Orchestrator
```

### Interface Design

```python
# strategies/base.py
class DriftStrategy(ABC):
    """Interface for all Drift trading strategies."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier (e.g., 'delta_neutral', 'funding_farm')."""
        ...
    
    @abstractmethod
    async def on_tick(self, state: MarketState) -> Optional[TradeSignal]:
        """Analyze market state, return signal if action needed."""
        ...
    
    @abstractmethod
    async def on_execute(self, signal: TradeSignal) -> TradeResult:
        """Execute the trade signal."""
        ...
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return strategy-specific status for dashboard."""
        ...
```

```python
# engine.py - Strategy-Agnostic Orchestrator
class DriftEngine(BaseEngine):
    """
    Modular Drift trading engine.
    
    Usage:
        strategy = DeltaNeutralStrategy(config)
        engine = DriftEngine(strategy=strategy, live_mode=True)
        await engine.start()
    """
    
    def __init__(
        self,
        strategy: DriftStrategy,
        live_mode: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name=f"drift-{strategy.name}", live_mode=live_mode)
        self.strategy = strategy  # Composition over inheritance
        self._margin_monitor = MarginMonitor()
        self._executor = SyncExecutor() if live_mode else MockExecutor()
    
    async def tick(self):
        """Risk-first tick loop."""
        # 1. Always check margin health first
        margin = await self._margin_monitor.check()
        if margin.health_score < 0.15:
            await self._emergency_close()
            return
        
        # 2. Get market state
        state = await self._get_market_state()
        
        # 3. Delegate to strategy
        signal = await self.strategy.on_tick(state)
        
        # 4. Execute if signal generated
        if signal:
            result = await self.strategy.on_execute(signal)
            self._track_pnl(result)
```

---

## Implementation Phases

### Phase 1: Wire Existing Engine (Immediate)

**Goal**: Get Delta Neutral trading visible in dashboard without refactoring.

**Changes**:
- Update `EngineManager._get_engine_command()` to spawn `src.delta_neutral.engine`
- Wire `DeltaNeutralEngine.get_status()` to heartbeat collector
- Remove duplicate `src/engines/drift/` created prematurely

**Effort**: 1-2 hours

---

### Phase 2: Extract Core Layer (Week 1)

**Goal**: Separate reusable protocol primitives from strategy logic.

**Changes**:
1. Create `src/drift_engine/core/client.py` from `drift_order_builder.py`
2. Create `src/drift_engine/core/margin_monitor.py` from heartbeat collector logic
3. Create `src/drift_engine/core/types.py` consolidated dataclasses

**Files Affected**:
- `src/delta_neutral/drift_order_builder.py` → refactored
- `src/interface/heartbeat_collector.py` → extracts margin logic

**Effort**: 4-6 hours

---

### Phase 3: Introduce Strategy Interface (Week 2)

**Goal**: Create `DriftStrategy` ABC and migrate Delta Neutral.

**Changes**:
1. Create `src/drift_engine/strategies/base.py`
2. Create `src/drift_engine/strategies/delta_neutral/strategy.py`
3. Wrap `NeutralityMonitor` as strategy component
4. Create new `DriftEngine` orchestrator

**Migration**:
```
src/delta_neutral/engine.py 
  → src/drift_engine/strategies/delta_neutral/strategy.py
  
src/delta_neutral/neutrality_monitor.py
  → src/drift_engine/strategies/delta_neutral/monitor.py
```

**Effort**: 8-12 hours

---

### Phase 4: Deprecate Legacy Module (Week 3)

**Goal**: Remove `src/delta_neutral/` after migration.

**Changes**:
1. Update all imports to use `src/drift_engine/`
2. Move execution code to `src/drift_engine/execution/`
3. Add deprecation warnings to old module
4. Delete after 2-week deprecation period

---

### Phase 5: Additional Strategies (Future)

**Goal**: Implement Funding Farm and Directional strategies.

**Prerequisites**: Phases 1-4 complete

---

## Consequences

### Positive

1. **Strategy Extensibility**: Add new strategies without touching execution code
2. **Testability**: Unit test strategies with mock executors
3. **Dashboard Unified**: Single engine interface for all Drift strategies
4. **Risk Centralization**: Margin monitoring shared across strategies

### Negative

1. **Migration Effort**: ~20 hours total across all phases
2. **Temporary Complexity**: Two modules exist during migration
3. **Learning Curve**: Contributors must understand Strategy Pattern

### Risks & Mitigations

| Risk | Mitigation |
|:-----|:-----------|
| Breaking live trading | Phase 1 wires existing code—no logic changes |
| Strategy interface too rigid | Design for common cases, allow override |
| Performance regression | Maintain <5ms tick latency via profiling |

---

## Alternatives Considered

| Approach | Reason Rejected |
|:---------|:----------------|
| Keep monolithic engine | Blocks additional strategies |
| Fork for each strategy | Massive code duplication |
| Plugin architecture | Over-engineered for 3-5 strategies |
| External strategy config (YAML) | Too limiting for complex logic |

---

## Success Metrics

- [ ] Phase 1: Delta Neutral visible in dashboard (`drift` engine status)
- [ ] Phase 2: `DriftClient` used by both heartbeat and engine
- [ ] Phase 3: `DriftStrategy` interface with 1+ implementation
- [ ] Phase 4: `src/delta_neutral/` deleted, all tests pass
- [ ] Phase 5: Funding Farm strategy operational

---

## References

- [drift_engine_implementation.md](../drift_engine_implementation.md) - UI/UX spec
- [architecture.md](../architecture.md) - System overview
- ADR-0003: UI Decoupling (SignalBus pattern)
- `src/delta_neutral/` - Current implementation
- `src/engines/base_engine.py` - BaseEngine interface
