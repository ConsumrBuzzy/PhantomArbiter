# Migration Guide: Legacy to Modern Architecture

**Target Audience**: Contributors, maintainers  
**Context**: PhantomArbiter is migrating from legacy engines to modern SRP-compliant architecture  
**Status**: Phase 1 complete, Phase 2 planned

---

## Quick Reference

| I want to... | Legacy (Deprecated) | Modern (Use This) |
|--------------|---------------------|-------------------|
| Run arbitrage scanner | `PhantomArbiter` | `ArbEngine` from `src/engines/arb/logic.py` |
| Run scalping strategy | `TacticalStrategy` | `ScalpEngine` from `src/engines/scalp/logic.py` |
| Run funding arbitrage | N/A | `FundingEngine` from `src/engines/funding/logic.py` |
| Launch dashboard | `UnifiedDirector` | `LocalDashboardServer` from `run_dashboard.py` |
| Orchestrate multiple engines | `UnifiedDirector` | Independent engines + callbacks |

---

## Migration Patterns

### Pattern 1: Simple Engine Replacement

**Before** (Legacy):
```python
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig

config = ArbiterConfig(
    budget=50.0,
    live_mode=False,
    min_spread=0.5
)
arbiter = PhantomArbiter(config)
await arbiter.run(duration_minutes=60)
```

**After** (Modern):
```python
from src.engines.arb.logic import ArbEngine

engine = ArbEngine(
    live_mode=False,
    min_spread=0.5
)

# Set callback for updates
async def on_update(data):
    print(f"Opportunity: {data}")

engine.set_callback(on_update)
await engine.start()

# Run for duration
await asyncio.sleep(60 * 60)
await engine.stop()
```

---

### Pattern 2: Callback-Based Updates

**Before** (Legacy - polling):
```python
# PhantomArbiter internally polls and blocks
await arbiter.run()  # Blocks until complete
```

**After** (Modern - event-driven):
```python
# Engine emits events via callback
async def on_arb_opportunity(data):
    profit = data['est_profit']
    path = data['path']
    print(f"Found: {path} → ${profit:.2f} profit")

engine.set_callback(on_arb_opportunity)
await engine.start()  # Non-blocking
```

---

### Pattern 3: Dashboard Integration

**Before** (Legacy - tight coupling):
```python
from src.director import UnifiedDirector

director = UnifiedDirector(live_mode=False, execution_enabled=True)
await director.start()  # Starts everything, blocks
```

**After** (Modern - loose coupling):
```python
from src.interface.dashboard_server import DashboardServer
from src.engines.arb.logic import ArbEngine

dashboard = DashboardServer()

# Create engine
arb_engine = ArbEngine(live_mode=False)

# Connect engine to dashboard
async def on_arb_update(data):
    await dashboard.broadcast({
        "type": "ARB_OPP",
        "data": data
    })

arb_engine.set_callback(on_arb_update)

# Start independently
await arb_engine.start()
await dashboard.start()
```

---

## Code Location Map

### Legacy (Deprecated - Will be archived)

```
src/
├── arbiter/              # ⚠️ DEPRECATED
│   ├── arbiter.py        # → Use ArbEngine
│   └── core/
│       └── pod_engine.py # → Use HopGraphEngine
├── strategies/           # ⚠️ DEPRECATED
│   └── tactical.py       # → Use ScalpEngine
└── director.py           # ⚠️ DEPRECATED → Use LocalDashboardServer
```

### Modern (Active Development)

```
src/
├── engines/              # ✅ MODERN
│   ├── arb/
│   │   └── logic.py      # ArbEngine
│   ├── scalp/
│   │   └── logic.py      # ScalpEngine
│   ├── funding/
│   │   └── logic.py      # FundingEngine
│   └── lst_depeg/
│       └── logic.py      # LSTEngine
└── interface/
    └── dashboard_server.py  # DashboardServer, LocalDashboardServer
```

---

## API Comparison

### ArbiterConfig → Engine Constructor

**Legacy**:
```python
config = ArbiterConfig(
    budget=50.0,
    gas_budget=5.0,
    min_spread=0.5,
    max_trade=0,
    live_mode=False,
    full_wallet=False,
    pairs=CORE_PAIRS,
    use_unified_engine=True
)
arbiter = PhantomArbiter(config)
```

**Modern**:
```python
# Simpler - only essential params
engine = ArbEngine(
    live_mode=False,
    min_spread=0.5
)
# Other config via engine methods:
# engine.set_budget(50.0)
# engine.set_pairs(CORE_PAIRS)
```

---

### scan_opportunities() → find_cycles()

**Legacy**:
```python
arbiter = PhantomArbiter(config)
opps = await arbiter.scan_opportunities(verbose=True)
```

**Modern**:
```python
engine = ArbEngine(live_mode=False)
await engine.initialize()  # Load pools
cycles = await engine.find_cycles(min_spread=0.5)
```

---

### run() → start()/stop()

**Legacy**:
```python
# Blocking call
await arbiter.run(duration_minutes=60, scan_interval=2)
```

**Modern**:
```python
# Non-blocking, event-driven
await engine.start()
# ... engine runs in background ...
await asyncio.sleep(60 * 60)  # Your duration control
await engine.stop()
```

---

## Common Migration Tasks

### Task 1: Update Imports

**Search and replace** in your code:

| Find | Replace |
|------|---------|
| `from src.arbiter.arbiter import PhantomArbiter` | `from src.engines.arb.logic import ArbEngine` |
| `from src.strategies.tactical import TacticalStrategy` | `from src.engines.scalp.logic import ScalpEngine` |
| `from src.director import UnifiedDirector` | `from src.interface.dashboard_server import DashboardServer` |

### Task 2: Update Config

**Before**:
```python
config = ArbiterConfig(**kwargs)
engine = PhantomArbiter(config)
```

**After**:
```python
engine = ArbEngine(**essential_kwargs)
# Configure via methods if needed
```

### Task 3: Replace Blocking Calls

**Before**:
```python
await arbiter.run(duration_minutes=60)
```

**After**:
```python
await engine.start()
await asyncio.sleep(60 * 60)
await engine.stop()
```

---

## Testing Your Migration

### Unit Test Pattern

**Before**:
```python
def test_arbiter():
    config = ArbiterConfig(live_mode=False, min_spread=1.0)
    arbiter = PhantomArbiter(config)
    # Test logic
```

**After**:
```python
@pytest.mark.asyncio
async def test_arb_engine():
    engine = ArbEngine(live_mode=False, min_spread=1.0)
    
    # Mock callback
    results = []
    engine.set_callback(lambda data: results.append(data))
    
    await engine.start()
    await asyncio.sleep(1)
    await engine.stop()
    
    assert len(results) > 0
```

### Integration Test Pattern

**Test both paths in parallel** during migration:

```python
async def test_parity():
    # Legacy
    legacy_arbiter = PhantomArbiter(ArbiterConfig(min_spread=0.5))
    legacy_result = await legacy_arbiter.scan_opportunities()
    
    # Modern
    modern_engine = ArbEngine(min_spread=0.5)
    modern_result = await modern_engine.find_cycles()
    
    # Compare
    assert len(legacy_result) == len(modern_result)
    assert legacy_result[0]['profit'] ≈ modern_result[0]['est_profit']
```

---

## Deprecation Timeline

| Version | Status | Action |
|---------|--------|--------|
| **0.1.0** (Current) | ⚠️ Deprecated | Warnings added to legacy code |
| **0.2.0** (Week 3) | 📋 Planned | Compatibility wrappers available |
| **0.3.0** (Week 6) | 🗑️ Archived | Legacy code moved to `archive/deprecated/` |
| **1.0.0** (Future) | ❌ Removed | Compatibility wrappers removed |

---

## Getting Help

### If you see deprecation warnings:

```
DeprecationWarning: PhantomArbiter is deprecated. Use ArbEngine from src.engines.arb
```

**Action**:
1. Read this migration guide
2. Update your imports (Pattern 1 above)
3. Test your code
4. Submit PR if fixing shared code

### If your code breaks after migration:

1. **Check compatibility wrapper** exists:
   ```python
   from src.engines.arb.compat import PhantomArbiter  # Temporary fix
   ```

2. **Review ADR-0004** for detailed migration plan

3. **Ask for help** in GitHub Discussions (if enabled)

---

## Examples

### Example 1: Quick Arbitrage Scan

```python
from src.engines.arb.logic import ArbEngine

async def quick_scan():
    engine = ArbEngine(live_mode=False, min_spread=0.5)
    await engine.initialize()
    
    cycles = await engine.find_cycles()
    
    for cycle in cycles:
        print(f"Path: {' → '.join(cycle['path'])}")
        print(f"Profit: {cycle['est_profit']:.2f} USD")
    
    return cycles

# Run
import asyncio
asyncio.run(quick_scan())
```

### Example 2: Long-Running Engine with Callback

```python
from src.engines.arb.logic import ArbEngine
import asyncio

async def monitor_arbitrage():
    engine = ArbEngine(live_mode=False)
    
    # Callback for opportunities
    async def on_opportunity(data):
        print(f"[{data['timestamp']}] Found: {data['path']}")
        print(f"  Profit: ${data['est_profit']:.2f}")
    
    engine.set_callback(on_opportunity)
    
    print("Starting engine...")
    await engine.start()
    
    # Run for 1 hour
    await asyncio.sleep(3600)
    
    await engine.stop()
    print("Engine stopped.")

asyncio.run(monitor_arbitrage())
```

---

## References

- **ADR-0004**: Main.py Modernization ([docs/adr/0004-main-py-modernization.md](../adr/0004-main-py-modernization.md))
- **run_dashboard.py**: Reference implementation
- **DEVELOPMENT.md**: PyPro coding standards
- **ARCHITECTURE.md**: System design overview
