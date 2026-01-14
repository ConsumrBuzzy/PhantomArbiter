# main.py Migration Plan

**Date**: 2026-01-14  
**Context**: Restore `main.py` as primary entry point (currently using `run_dashboard.py`)  
**Status**: Analysis Complete - Migration plan defined

---

## Current State

| Entry Point | Status | Purpose | Issues |
|-------------|--------|---------|--------|
| `main.py` | ❌ Broken | Full-featured CLI with subcommands | Legacy imports fail |
| `run_dashboard.py` | ✅ Working | Minimal dashboard launcher | Limited functionality |

---

## Why main.py is Broken

### Critical Dependencies on Archived Code

**Line 277**: `from src.director import UnifiedDirector`
- UnifiedDirector imports from `src.legacy.arbiter.arbiter` (line 34)
- UnifiedDirector imports from `src.legacy.strategies.tactical` (line 35)
- **Both now in `archive/legacy_src/`**

**Line 436**: `from src.arbiter.core.pod_engine import ...`
- Expects arbiter in `src/arbiter/` 
- **Actually in `archive/legacy_src/arbiter/`**

**Line 453**: `ArbiterConfig` usage
- **Undefined** - came from legacy imports

**Line 505**: `PhantomArbiter(config)`
- **Undefined** - came from legacy imports

###  Broken Subcommands

| Command | Status | Blocker |
|---------|--------|---------|
| `python main.py dashboard` | ❌ | UnifiedDirector → legacy imports  |
| `python main.py arbiter` | ❌ | PhantomArbiter undefined |
| `python main.py scan` | ❌ | PhantomArbiter undefined |
| `python main.py pulse` | ⏩ | Redirects to dashboard (breaks) |
| `python main.py discover` | ❓ | May work (scraper independent) |
| `python main.py scout` | ❓ | May work (scout agent independent) |

---

## Why run_dashboard.py Works

### Clean Architecture

**No legacy dependencies**:
- Uses `src.engines.lst_depeg.logic` (modern)
- Uses `src.engines.scalp.logic` (modern)
- Uses `src.engines.arb.logic` (modern)
- Uses `src.engines.funding.logic` (modern)

**Simple structure**:
1. Launch HTTP server for frontend
2. Start price feeds (Pyth WebSocket)
3. Start LocalDashboardServer (WebSocket)
4. Instantiate engines **in-process** (not via subprocesses)
5. No complex CLI parsing

---

## Migration Strategy

### Option A: Quick Fix (Restore Legacy)

**Action**: Move archived code back temporarily

```powershell
# Restore arbiter to expected location
Move-Item archive\legacy_src\arbiter src\
Move-Item archive\legacy_src\strategies src\

# Update imports in director.py
# Line 34: from src.arbiter.arbiter import PhantomArbiter...
# Line 35: from src.strategies.tactical import TacticalStrategy...
```

**Impact**: 
- ✅ main.py works immediately
- ❌ Technical debt returns
- ⏰ Time: 10 minutes

---

### Option B: Modernize main.py (Align with run_dashboard)

**Action**: Refactor `main.py` to use modern engine architecture

**Changes Required**:

#### 1. Replace Legacy Arbiter with Modern ArbEngine

```python
# OLD (main.py lines 505-511):
from src.legacy.arbiter.arbiter import PhantomArbiter, ArbiterConfig
arbiter = PhantomArbiter(config)
await arbiter.run(...)

# NEW (like run_dashboard.py):
from src.engines.arb.logic import ArbEngine
arb_engine = ArbEngine(live_mode=args.live)
await arb_engine.start()
```

#### 2. Replace UnifiedDirector with LocalDashboardServer

```python
# OLD (main.py line 356):
from src.director import UnifiedDirector
director = UnifiedDirector(live_mode=args.live, execution_enabled=False)

# NEW (like run_dashboard.py line 51-130):
from src.interface.dashboard_server import DashboardServer
dashboard = LocalDashboardServer(engines_map)
```

#### 3. Update cmd_dashboard to match run_dashboard pattern

Simplify `cmd_dashboard()` (lines 269-395) to follow `run_dashboard.py` pattern:
- Remove UnifiedDirector
- Use LocalDashboardServer
- Inline engine initialization

**Impact**:
- ✅ Clean architecture maintained
- ✅ No legacy dependencies
- ❌ Requires code surgery
- ⏰ Time: 2-3 hours

---

### Option C: Hybrid (Recommended)

**Phase 1: Restore for Now** (10 min)
1. Move `archive/legacy_src/{arbiter,strategies}` → `src/`
2. Update `director.py` imports
3. Keep legacy marked with `# TODO: Migrate to modern engine`

**Phase 2: Gradual Migration** (Week 2)
1. Create `docs/adr/0004-main-py-modernization.md`
2. Port `cmd_arbiter()` to use `ArbEngine` (1 hour)
3. Port `cmd_dashboard()` to use `LocalDashboardServer` (2 hours)
4. Test both old and new paths side-by-side
5. Deprecate legacy once new path proven

**Impact**:
- ✅ main.py works immediately
- ✅ Clear migration path
- ✅ No rush, incremental progress
- ⏰ Time: 10 min now, 3-5 hours later

---

## Recommended Action: Option C (Hybrid)

### Immediate (Next 10 minutes)

```powershell
# 1. Restore arbiter/strategies
Move-Item archive\legacy_src\arbiter src\
Move-Item archive\legacy_src\strategies src\

# 2. Fix director.py imports (lines 34-35)
# Change:
#   from src.legacy.arbiter... → from src.arbiter...
#   from src.legacy.strategies... → from src.strategies...

# 3. Test main.py
python main.py dashboard --no-galaxy
```

### This Week (When ready)

1. Create ADR documenting modernization plan
2. Port one command at a time:
   - Start with `cmd_scan` (simplest)
   - Then `cmd_arbiter`
   - Finally `cmd_dashboard`

3. Add deprecation warnings:
   ```python
   # In legacy paths
   warnings.warn("Using legacy arbiter - migrate to ArbEngine", DeprecationWarning)
   ```

---

## File Modifications Required (Immediate)

### 1. Restore Legacy Code

```powershell
Move-Item archive\legacy_src\arbiter src\
Move-Item archive\legacy_src\strategies src\
```

### 2. Fix src/director.py

**Line 34**: Change:
```python
# OLD:
from src.legacy.arbiter.arbiter import PhantomArbiter, ArbiterConfig

# NEW:
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
```

**Line 35**: Change:
```python
# OLD:
from src.legacy.strategies.tactical import TacticalStrategy

# NEW:
from src.strategies.tactical import TacticalStrategy
```

### 3. Update main.py (if needed)

**Line 436** - Already correct (`from src.arbiter.core.pod_engine`)  
**Line 516** - Already correct (`from src.arbiter.arbiter`)

---

## Testing Checklist

After restore:

- [ ] `python main.py` (should show help)
- [ ] `python main.py dashboard --no-galaxy` (should launch)
- [ ] `python main.py pulse` (redirects to dashboard)
- [ ] `python main.py arbiter --paper --duration 1` (1 min scan)
- [ ] `python run_dashboard.py` (should still work)

---

## Long-Term Vision

**Goal**: `main.py` becomes modern CLI using run_dashboard's clean architecture

```
main.py (Modernized)
├── dashboard → LocalDashboardServer + ModernEngines
├── arbiter → ArbEngine (not PhantomArbiter)
├── scalp → ScalpEngine
├── funding → FundingEngine
└── lst → LSTEngine
```

**No more `src/legacy/`** - all engines use `src/engines/*` pattern.

---

## Next Steps

**User Decision Required**:
1. Execute Option C Phase 1 now? (Restore legacy for immediate functionality)
2. Skip to Option B? (Full modernization, 3 hours work)
3. Keep run_dashboard only? (Abandon main.py CLI features)

**PyPro Recommendation**: **Option C Phase 1** (restore now, migrate later with proper planning).
