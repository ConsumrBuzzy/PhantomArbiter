# ADR-0004: Main.py CLI Modernization

**Status**: Accepted  
**Date**: 2026-01-14  
**Context**: "Legacy Architecture Cleanup - Aligning main.py with Modern Engine Pattern"

---

## Context

PhantomArbiter currently has **two entry points** with divergent architectural patterns:

### 1. `main.py` (Legacy Architecture)
```python
# Uses legacy engines
from src.arbiter.arbiter import PhantomArbiter
from src.strategies.tactical import TacticalStrategy
from src.director import UnifiedDirector

# Complex orchestration
director = UnifiedDirector(live_mode=args.live, execution_enabled=False)
arbiter = PhantomArbiter(config)
await arbiter.run(...)
```

**Issues**:
- Depends on `src/arbiter/` and `src/strategies/` (legacy, pre-SRP architecture)
- UnifiedDirector has tight coupling between UI and execution
- PhantomArbiter uses monolithic design (900+ lines)
- TacticalStrategy mixes concerns (trading logic + data management)

### 2. `run_dashboard.py` (Modern Architecture)
```python
# Uses modern engines
from src.engines.arb.logic import ArbEngine
from src.engines.scalp.logic import ScalpEngine
from src.interface.dashboard_server import DashboardServer

# Clean separation
arb_engine = ArbEngine(live_mode=False)
arb_engine.set_callback(on_arb_update)
await arb_engine.start()
```

**Benefits**:
- SRP compliance: Each engine has single responsibility
- Engines in `src/engines/*` follow consistent pattern
- LocalDashboardServer implements ADR-0003 (UI decoupling)
- Clean callback-based event flow
- Easy to test, mock, and extend

---

## Problem Statement

**The current state creates**:
1. **Architectural Drift**: Two patterns for doing the same thing
2. **Technical Debt**: Legacy code requires maintenance
3. **Confusion**: New contributors unsure which pattern to follow
4. **Duplication**: Arbitrage logic exists in both PhantomArbiter and ArbEngine

**Specific Pain Points**:
- Phase 3 legacy purge broke main.py (needed restoration)
- UnifiedDirector imports from legacy modules
- PhantomArbiter can't be easily ported to Rust hot paths
- TacticalStrategy has 1500+ lines (violates SRP)

---

## Decision

**Migrate `main.py` to use the modern engine architecture demonstrated in `run_dashboard.py`.**

### Target Architecture

```
main.py (Modernized)
├── Subcommand: dashboard
│   └── LocalDashboardServer + ModernEngines (like run_dashboard.py)
├── Subcommand: arbiter
│   └── ArbEngine (from src/engines/arb/logic.py)
├── Subcommand: scalp
│   └── ScalpEngine (from src/engines/scalp/logic.py)
├── Subcommand: funding
│   └── FundingEngine (from src/engines/funding/logic.py)
└── Subcommand: scan
    └── ArbEngine.scan_once() (one-shot mode)
```

**No more**:
- `src/arbiter/arbiter.py` (PhantomArbiter class)
- `src/strategies/tactical.py` (TacticalStrategy class)
- `src/director.py` (UnifiedDirector - replaced by LocalDashboardServer)

---

## Migration Strategy

### Phase 2A: Preparation (Week 2)

**Estimated Time**: 2 hours

1. **Add Deprecation Warnings** to legacy code:
   ```python
   # src/arbiter/arbiter.py (line 1)
   import warnings
   warnings.warn(
       "PhantomArbiter is deprecated. Use ArbEngine from src.engines.arb",
       DeprecationWarning,
       stacklevel=2
   )
   ```

2. **Create Interface Compatibility Layer**:
   ```python
   # src/engines/arb/compat.py
   from src.engines.arb.logic import ArbEngine
   
   class PhantomArbiter(ArbEngine):
       """Legacy compatibility wrapper. DEPRECATED."""
       def __init__(self, config):
           warnings.warn("Use ArbEngine directly", DeprecationWarning)
           super().__init__(live_mode=config.live_mode)
   ```

3. **Document Migration Map**:
   | Legacy Class | Modern Replacement | Location |
   |--------------|-------------------|----------|
   | PhantomArbiter | ArbEngine | `src/engines/arb/logic.py` |
   | TacticalStrategy | ScalpEngine | `src/engines/scalp/logic.py` |
   | UnifiedDirector | LocalDashboardServer | `src/interface/dashboard_server.py` |

---

### Phase 2B: Command Migration (Week 3)

**Estimated Time**: 5 hours

#### Step 1: Port `cmd_scan()` (Simplest - 1 hour)

**Before**:
```python
async def cmd_scan(args):
    from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
    config = ArbiterConfig(min_spread=args.min_spread)
    arbiter = PhantomArbiter(config)
    opportunities = await arbiter.scan_opportunities(verbose=True)
```

**After**:
```python
async def cmd_scan(args):
    from src.engines.arb.logic import ArbEngine
    
    engine = ArbEngine(live_mode=False)
    await engine.initialize()
    
    # One-shot scan
    opportunities = await engine.find_cycles(min_spread=args.min_spread)
    
    # Display results
    for opp in opportunities:
        print(f"  {opp['path']} → {opp['profit_pct']:.2f}% profit")
```

#### Step 2: Port `cmd_arbiter()` (Core - 2 hours)

**Before**:
```python
async def cmd_arbiter(args):
    config = ArbiterConfig(
        budget=args.budget,
        live_mode=args.live,
        min_spread=args.min_spread,
        # ... many params
    )
    arbiter = PhantomArbiter(config)
    await arbiter.run(duration_minutes=args.duration)
```

**After**:
```python
async def cmd_arbiter(args):
    from src.engines.arb.logic import ArbEngine
    
    engine = ArbEngine(
        live_mode=args.live,
        min_spread=args.min_spread,
    )
    
    # Setup callback for progress updates
    def on_update(data):
        print(f"  [{data['type']}] {data['message']}")
    
    engine.set_callback(on_update)
    await engine.start()
    
    # Run for duration
    await asyncio.sleep(args.duration * 60)
    await engine.stop()
```

#### Step 3: Port `cmd_dashboard()` (Complex - 2 hours)

**Before**:
```python
async def cmd_dashboard(args):
    from src.director import UnifiedDirector
    director = UnifiedDirector(live_mode=args.live, execution_enabled=False)
    await director.start()
```

**After** (align with `run_dashboard.py`):
```python
async def cmd_dashboard(args):
    from src.interface.dashboard_server import DashboardServer
    from src.engines.arb.logic import ArbEngine
    from src.engines.scalp.logic import ScalpEngine
    # ... (full pattern from run_dashboard.py lines 54-318)
    
    dashboard = LocalDashboardServer(engines_map)
    # Setup engines with callbacks
    # Start price feeds
    await dashboard.start()
```

---

### Phase 2C: Legacy Deprecation (Week 4)

**Estimated Time**: 1 hour

1. **Move to archive** (second time, but intentional):
   ```powershell
   Move-Item src\arbiter archive\deprecated\
   Move-Item src\strategies archive\deprecated\
   # Note: archive/deprecated vs. archive/legacy_src
   ```

2. **Update imports** in remaining code (if any)

3. **Run test suite**:
   ```powershell
   pytest tests/ -v -k "not legacy"
   ```

4. **Update documentation**:
   - README.md: Remove PhantomArbiter references
   - docs/COMPONENT_INVENTORY.md: Mark as deprecated
   - docs/ARCHITECTURE.md: Remove legacy layer

---

## Consequences

### Positive

#### 1. Architectural Consistency
- **Single pattern** for all engines: `src/engines/<name>/logic.py`
- **Clear ownership**: Each engine imports from its own directory
- **Easier onboarding**: Contributors see one pattern, not two

#### 2. Maintainability
- **Smaller classes**: ArbEngine ~400 lines vs. PhantomArbiter ~900 lines
- **SRP compliance**: Each engine does one thing well
- **Testability**: Engines are isolated, easy to mock

#### 3. Future-Proofing
- **Rust migration ready**: ArbEngine.find_cycles() can call Rust FFI
- **Parallel execution**: Engines run independently (no UnifiedDirector bottleneck)
- **Microservice path**: Engines already designed for decoupling

#### 4. Performance
- **No UnifiedDirector overhead**: Engines start/stop independently
- **Event-driven**: Callbacks instead of polling
- **Async-native**: No thread-based hacks

### Negative

#### 1. Breaking Changes
- **External scripts** calling PhantomArbiter will break
- **Config files** using ArbiterConfig need updates
- **Documentation lag**: Existing guides reference old classes

**Mitigation**: 
- Keep compatibility wrappers for 1 release cycle
- Add migration guide to README
- Update all examples in docs/

#### 2. Testing Burden
- **Must verify parity**: New path produces same results as old
- **Regression risk**: Edge cases in legacy code may be missed
- **Double testing period**: Both paths tested during migration

**Mitigation**:
- Run parallel tests (old vs. new) for 2 weeks
- Document behavioral differences
- Use shadow mode for production validation

#### 3. Time Investment
- **8 hours total** for migration (2 prep + 5 porting + 1 cleanup)
- **Opportunity cost**: Not working on new features
- **Risk of scope creep**: May discover more tech debt

**Mitigation**:
- Time-box each phase strictly
- Focus on core commands first (arbiter, scan, dashboard)
- Defer nice-to-haves (discover, scout) to Phase 3

---

## Comparison: Legacy vs. Modern

| Aspect | Legacy (main.py + director) | Modern (run_dashboard.py) |
|--------|---------------------------|--------------------------|
| **Architecture** | Monolithic | Microkernel |
| **Lines of Code** | ~2500 (director + arbiter + tactical) | ~1200 (dashboard + 4 engines) |
| **Testability** | Hard (many dependencies) | Easy (isolated engines) |
| **Startup Time** | ~5s (initializes everything) | ~2s (lazy load engines) |
| **Memory Usage** | ~150 MB (all loaded) | ~80 MB (per-engine) |
| **UI Coupling** | Tight (ADR-0003 violation) | Loose (event-driven) |
| **Rust Integration** | Difficult (deep call stack) | Easy (engines call FFI) |
| **Parallel Execution** | Sequential (director bottleneck) | Parallel (independent engines) |

---

## Implementation Checklist

### Phase 2A (Preparation)
- [ ] Add deprecation warnings to `src/arbiter/arbiter.py`
- [ ] Add deprecation warnings to `src/strategies/tactical.py`
- [ ] Create compatibility wrappers in `src/engines/*/compat.py`
- [ ] Document migration map in `docs/MIGRATION_GUIDE.md`

### Phase 2B (Command Migration)
- [ ] Port `cmd_scan()` → ArbEngine.find_cycles()
- [ ] Port `cmd_arbiter()` → ArbEngine with callbacks
- [ ] Port `cmd_dashboard()` → LocalDashboardServer pattern
- [ ] Update `cmd_pulse()` redirect logic
- [ ] Test all commands in paper mode

### Phase 2C (Legacy Deprecation)
- [ ] Move `src/arbiter/` to `archive/deprecated/`
- [ ] Move `src/strategies/` to `archive/deprecated/`
- [ ] Update all imports in `main.py`
- [ ] Run full test suite (`pytest tests/ -v`)
- [ ] Update documentation (README, COMPONENT_INVENTORY, ARCHITECTURE)

### Phase 2D (Validation)
- [ ] Run parallel testing (legacy vs. modern) for 2 weeks
- [ ] Compare arbitrage results (profit %, execution time)
- [ ] Validate no regressions in paper mode
- [ ] Get user sign-off before removing compatibility wrappers

---

## Rollback Plan

If migration fails or introduces regressions:

1. **Immediate Rollback** (keep compatibility wrappers active):
   ```python
   # main.py - revert to legacy imports
   from src.engines.arb.compat import PhantomArbiter  # Uses old interface
   ```

2. **Full Rollback** (restore from archive):
   ```powershell
   Move-Item archive\deprecated\arbiter src\
   Move-Item archive\deprecated\strategies src\
   ```

3. **Hybrid Mode** (run both in parallel):
   ```python
   # Use new engine but validate against legacy
   modern_result = await arb_engine.find_cycles()
   legacy_result = await legacy_arbiter.scan_opportunities()
   assert_results_match(modern_result, legacy_result)
   ```

---

## Timeline

| Phase | Duration | Milestone |
|-------|----------|-----------|
| **2A: Preparation** | Week 2 (2 hours) | Deprecation warnings added |
| **2B: Command Migration** | Week 3 (5 hours) | core, arbiter, dashboard ported |
| **2C: Deprecation** | Week 4 (1 hour) | Legacy code archived |
| **2D: Validation** | Weeks 4-6 (ongoing) | Parallel testing complete |
| **2E: Finalize** | Week 6 (30 min) | Remove compatibility wrappers |

**Total Estimated Time**: 8.5 hours spread over 5 weeks

---

## Success Criteria

**Phase 2 is complete when**:
1. ✅ All main.py subcommands use `src/engines/*` pattern
2. ✅ No imports from `src/arbiter/` or `src/strategies/`
3. ✅ Test suite passes with >95% coverage
4. ✅ Paper mode arbitrage results match legacy within 1%
5. ✅ `run_dashboard.py` and `main.py` use identical engine code
6. ✅ Documentation updated (no PhantomArbiter references)

---

## References

- **ADR-0001**: Hybrid Architecture (TypeScript bridges)
- **ADR-0002**: Rust Acceleration (hot path optimization)
- **ADR-0003**: UI Decoupling (event-driven design)
- **docs/MAIN_PY_MIGRATION.md**: Migration analysis
- **docs/OPTION_C_PHASE1_COMPLETE.md**: Phase 1 execution log
- **run_dashboard.py**: Reference implementation (lines 200-290)

---

## Approval

**Proposed**: 2026-01-14  
**Accepted**: Pending user review  
**Implementation Start**: Week 2 (user discretion)
