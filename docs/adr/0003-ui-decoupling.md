# ADR-0003: UI Decoupling from Trading Core

**Status**: Accepted  
**Date**: 2026-01-05  
**Context**: "Preventing UI Latency from Impacting Trade Execution"

---

## Context

PhantomArbiter has two primary user interfaces:

1. **Rich TUI** (`src/dashboard/tui_app.py`): Terminal-based dashboard using the `textual` library
2. **Galaxy Dashboard** (`apps/galaxy/`): Web-based 3D visualization using Three.js

### The Problem

Initial architecture (Phase 2-3) had **tight coupling** between the trading core and UI:

```python
# ❌ ANTI-PATTERN: UI blocking trade execution
class TradingCore:
    def on_price_update(self, token, price):
        # Business logic
        self._check_signals(token, price)
        
        # UI update IN THE SAME THREAD
        self.dashboard.update_price_widget(token, price)  # <-- Blocks if UI is slow!
```

**Observed Issues**:
- UI rendering lag (20-50ms) delayed signal processing
- Galaxy WebSocket disconnections caused trade executor crashes
- TUI input polling starved async event loop

---

## Decision

We enforce **strict separation of concerns**:

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    TRADING CORE                          │
│  ┌────────────┐      ┌────────────┐                      │
│  │  Director  │──────│  Tactical  │  (P0: Critical Path) │
│  │            │      │  Strategy  │                      │
│  └────────────┘      └──────┬─────┘                      │
│                             │                            │
│                             │ Events Only                │
│                             ▼                            │
│  ┌──────────────────────────────────────────┐            │
│  │        SignalBus (Pub/Sub)               │            │
│  │  • Fire-and-forget event emission         │            │
│  │  • No UI synchronization                 │            │
│  └──────────────────────────────────────────┘            │
└─────────────────────┬────────────────────────────────────┘
                      │ Async Queue
                      │
        ┌─────────────┼─────────────┐
        ▼                           ▼
┌───────────────┐           ┌──────────────┐
│   Rich TUI    │           │    Galaxy    │
│  (Consumer)   │           │  (Consumer)  │
│               │           │              │
│ • Subscribes  │           │ • HTTP API   │
│   to events   │           │ • WebSocket  │
│ • Independent │           │ • Buffered   │
│   thread      │           │   updates    │
└───────────────┘           └──────────────┘
```

### Implementation Rules

#### 1. No Synchronous UI Calls from Core

**Before**:
```python
# ❌ BAD
def execute_trade(self, signal):
    result = self._executor.buy(signal.token, signal.size)
    self.dashboard.show_notification(f"Bought {signal.token}")  # <-- BLOCKS
```

**After**:
```python
# ✅ GOOD
def execute_trade(self, signal):
    result = self._executor.buy(signal.token, signal.size)
    self.signal_bus.emit("TRADE_EXECUTED", result)  # Fire-and-forget
```

#### 2. UI Consumes via Async Queue

```python
# In TUI or Galaxy
async def ui_event_loop(self):
    while True:
        event = await self.signal_bus.subscribe("TRADE_EXECUTED")
        self.render_trade_notification(event.data)
```

#### 3. Shared State via Read-Only Cache

```python
# Core writes to cache (fast)
class CapitalManager:
    def update_balance(self, new_balance: Decimal):
        self._balance = new_balance
        AppState.set("balance", float(new_balance))  # ~0.1ms

# UI reads from cache (async)
class GalaxyAPI:
    async def get_metrics(self):
        return {
            "balance": AppState.get("balance"),
            "positions": AppState.get("positions")
        }
```

---

## Consequences

### Positive

#### 1. Deterministic Execution Time
Trading core no longer waits for UI:
- **Before**: `on_price_update()` took 5-50ms (UI-dependent)
- **After**: `on_price_update()` consistently <2ms

#### 2. UI Can Crash Without Affecting Trading
```python
try:
    galaxy_server.start()
except Exception as e:
    logger.error("Galaxy crashed, but trading continues", exc_info=True)
    # Core keeps running!
```

#### 3. Independent Scaling
- Can run headless (no UI) on VPS
- Multiple UIs can connect to same trading core
- UI can run on different machine via gRPC (future)

### Negative

#### 1. Eventual Consistency
- UI displays **stale data** (100-500ms lag acceptable)
- User sees "Executing..." → brief delay → "Filled"

#### 2. Increased Complexity
- Need to manage event subscriptions
- SignalBus debugging harder than direct calls

#### 3. State Synchronization Bugs
If `AppState` writes are missed:
```python
# Bug: Forgot to emit event
def _execute_internal_swap(self):
    self._balance -= 100  # Updated balance
    # Oops! No AppState.set() or signal_bus.emit()
    # UI shows wrong balance
```

**Mitigation**: Unit tests verify all state changes emit events.

---

## Migration Path

### Phase 1: Rich TUI Decoupling (Complete ✅)
- [x] Move TUI to separate thread
- [x] TUI subscribes to `SignalBus`
- [x] Remove all `dashboard.update()` calls from `src/director.py`

### Phase 2: Galaxy HTTP API (Complete ✅)
- [x] Expose `/api/v1/metrics` endpoint
- [x] Galaxy polls every 500ms instead of real-time push

### Phase 3: WebSocket Streaming (Planned 📋)
- [ ] Implement WebSocket server in `apps/galaxy/`
- [ ] Push events from `SignalBus` to connected clients
- [ ] Add backpressure handling (drop frames if client is slow)

---

## Performance Validation

### Before Decoupling

```
[PROFILE] on_price_update: 42ms
  |- check_signals: 3ms
  |- dashboard.update_price: 35ms  <-- Rendering lag
  |- emit_event: 4ms
```

### After Decoupling

```
[PROFILE] on_price_update: 4ms
  |- check_signals: 3ms
  |- signal_bus.emit: 1ms  <-- Non-blocking
```

**Result**: 10x faster critical path.

---

## Alternatives Considered

| Approach | Reason Rejected |
|----------|-----------------|
| **Shared Lock** | Lock contention would block trading |
| **UI in subprocess** | IPC overhead, complex crash handling |
| **Database polling** | 10ms+ latency, SQLite write locks |
| **No UI** | Users need real-time visibility |

---

## Future Enhancements

### Micro-Service Architecture (M4 Milestone)

```
┌────────────┐       gRPC        ┌──────────────┐
│ Trading    │───────────────────│  Galaxy      │
│ Core       │                   │  Service     │
│ (Server)   │                   │  (Client)    │
└────────────┘                   └──────────────┘
```

- Trading core as standalone gRPC server
- UI as separate process/container
- Full network isolation

---

## References

- [VISUAL_ARCHITECTURE.md](../VISUAL_ARCHITECTURE.md) - System diagram
- ADR-0001: Hybrid Architecture
- `src/shared/state/app_state.py` - Shared state implementation
- `src/shared/system/signal_bus.py` - Event bus
