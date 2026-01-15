# UI Separation: Galaxy vs. Web UI

**Date**: 2026-01-14  
**Change**: Separated Galaxy 3D Map and Component-Based Web UI into distinct commands  
**Status**: ✅ Complete

---

## Problem

PhantomArbiter had two different UI approaches merged into a single `dashboard` command:

1. **Galaxy Map** - Three.js 3D visualization (`apps/galaxy/`)
2. **Component-Based Web UI** - Modern dashboard with independent engines (`run_dashboard.py`)

This made it difficult to:
- Work on either UI independently
- Understand which UI was being launched
- Maintain separation of concerns

---

## Solution

### New Command Structure

| Command | Purpose | Implementation | Recommended |
|---------|---------|----------------|-------------|
| `python main.py web` | Component-Based Web UI | Delegates to `run_dashboard.py` | ✅ **Primary** |
| `python main.py galaxy` | Galaxy 3D Visualization | Launches `apps/galaxy/` with optional backend | For 3D viz |
| `python main.py dashboard` | Legacy redirect | Redirects to `web` | Deprecated |

---

## Command Details

### `web` - Component-Based Web UI (Recommended)

**Purpose**: Modern, component-based dashboard with independent engines

**Usage**:
```bash
# Standard launch
python main.py web

# Live trading mode
python main.py web --live

# Custom port
python main.py web --port 8080

# Don't open browser automatically
python main.py web --no-browser
```

**What it does**:
- Delegates to `run_dashboard.py` (single source of truth)
- Launches LocalDashboardServer (WebSocket API)
- Starts engines: Arb, Scalp, Funding, LST
- Opens browser to `http://localhost:8000`

**Benefits**:
- Clean separation of UI and engines
- Event-driven architecture (ADR-0003 compliant)
- Easy to test and maintain
- Engines run in-process (fast)

---

### `galaxy` - Galaxy 3D Visualization

**Purpose**: Three.js 3D force-directed token relationship graph

**Usage**:
```bash
# Full Galaxy with backend
python main.py galaxy

# Galaxy visualization only (no engines)
python main.py galaxy --standalone

# Live mode
python main.py galaxy --live

# Don't open browser
python main.py galaxy --no-browser
```

**What it does**:
- Launches `apps/galaxy/` via uvicorn on port 8001
- Opens browser to `http://localhost:8001/dashboard.html`
- Optionally starts UnifiedDirector for backend engines
- Runs Galaxy subprocess with EventBridge

**Use Cases**:
- Visual exploration of token relationships
- 3D arbitrage cycle visualization
- Demo/presentation mode

---

### `dashboard` - Legacy Redirect (Deprecated)

**Purpose**: Backward compatibility for existing scripts

**Behavior**: Automatically redirects to `web` command with deprecation warning

**Example**:
```bash
python main.py dashboard
# Output: ⚠️ 'dashboard' command is deprecated. Redirecting to 'web'...
# Then launches web UI
```

---

## Migration Guide

### If you were using:

**Old**:
```bash
python main.py dashboard
python main.py dashboard --live
python main.py dashboard --no-galaxy
```

**New** (recommended):
```bash
python main.py web                 # Modern UI (replaces --no-galaxy)
python main.py web --live
python main.py galaxy              # 3D visualization (old default)
```

---

## Implementation Details

### File Changes

**main.py** - 3 sections modified:

1. **Subcommand definitions** (lines 221-267):
   ```python
   # NEW: web command
   web_parser = subparsers.add_parser("web", ...)
   
   # NEW: galaxy command
   galaxy_parser = subparsers.add_parser("galaxy", ...)
   
   # UPDATED: dashboard marked as legacy
   dash_parser = subparsers.add_parser("dashboard", help="[LEGACY] Redirects...")
   ```

2. **Command handlers** (lines 428-544):
   ```python
   async def cmd_web(args):
       """Delegates to run_dashboard.py"""
       # Import and run run_dashboard.main()
   
   async def cmd_galaxy(args):
       """Launches apps/galaxy/ with optional backend"""
       # Start Galaxy subprocess
       # Optionally start UnifiedDirector
   ```

3. **Routing logic** (lines 554-583):
   ```python
   # Default: web (not dashboard)
   if len(sys.argv) == 1:
       sys.argv.append("web")
   
   # Redirect dashboard -> web
   if args.command == "dashboard":
       await cmd_web(args)
   ```

---

## Benefits of Separation

### For Development

| Aspect | Before (merged) | After (separated) |
|--------|----------------|-------------------|
| **Code Location** | Mixed in cmd_dashboard | `web` → run_dashboard.py, `galaxy` → cmd_galaxy |
| **Testing** | Test both together | Test independently |
| **Dependencies** | Shared/coupled | Clearly defined |
| **Iteration Speed** | Slower (affects both) | Faster (isolated changes) |

### For Users

| Scenario | Before | After |
|----------|--------|-------|
| Want modern UI | `dashboard --no-galaxy` | `web` |
| Want 3D visualization | `dashboard` (maybe) | `galaxy` |
| Want visualization only | Not possible | `galaxy --standalone` |
| Want both | Complex flags | Run separately |

---

## Testing Checklist

- [ ] `python main.py web` - Should launch component-based UI
- [ ] `python main.py web --no-browser` - Should not open browser
- [ ] `python main.py galaxy` - Should launch Galaxy + backend
- [ ] `python main.py galaxy --standalone` - Should launch Galaxy only
- [ ] `python main.py galaxy --no-browser` - Should not open browser
- [ ] `python main.py dashboard` - Should redirect to web with warning
- [ ] `python main.py` (no args) - Should default to web
- [ ] `python main.py live` - Should launch web in live mode

---

## Directory Structure

```
PhantomArbiter/
├── main.py                      # ✅ Routes to web or galaxy
├── run_dashboard.py             # ✅ Component-based UI implementation
├── apps/
│   └── galaxy/                  # ✅ Galaxy 3D visualization
│       └── src/
│           └── galaxy/
│               └── server.py    # FastAPI + Three.js
└── src/
    ├── interface/
    │   └── dashboard_server.py  # LocalDashboardServer (used by web)
    └── director.py              # UnifiedDirector (used by galaxy backend)
```

---

## Future Work

### Phase 2B (Modernization)

When migrating `cmd_galaxy` to use modern engines:

**Current**:
```python
# cmd_galaxy uses UnifiedDirector (legacy)
director = UnifiedDirector(live_mode=args.live)
await director.start()
```

**Future**:
```python
# cmd_galaxy uses LocalDashboardServer (modern)
dashboard = LocalDashboardServer(engines_map)
await dashboard.start()
```

This will align Galaxy with the same architecture as Web UI.

---

## Summary

**What Changed**:
- ✅ Added `web` command (component-based UI - recommended)
- ✅ Added `galaxy` command (3D visualization)
- ✅ Deprecated `dashboard` command (redirects to `web`)
- ✅ Updated default behavior (no args → `web`)

**Benefits**:
- Clear separation between 3D map and component UI
- Easier independent development
- Better user clarity about what's running
- Backward compatibility maintained

**Recommended Usage**:
```bash
python main.py web      # For normal operation (modern UI)
python main.py galaxy   # For 3D visualization demos
```

---

**PyPro Assessment**: Clean separation achieved. Both UI paths are now independent and can be developed/tested separately. Legacy compatibility maintained via redirect.
