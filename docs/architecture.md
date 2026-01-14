# System Architecture

**Version**: 0.1.0  
**Status**: Hybrid Architecture (Active)  
**Last Updated**: 2026-01-14

---

## 🏛️ High-Level Overview

PhantomArbiter is an **autonomous Solana DeFi arbitrage and trading engine** built on a **hybrid multi-language architecture**:

- **Python 3.13+**: Core orchestration, business logic, and strategy implementation
- **Rust (via PyO3)**: Performance-critical hot paths (<1ms latency requirements)
- **TypeScript/Node.js**: DEX protocol integrations (Orca, Raydium, Meteora)

### Design Philosophy

1. **Separation by Performance Tier**: Fast/Mid/Slow lanes with dedicated execution contexts
2. **Language-Optimal Delegation**: Each technology handles what it does best
3. **UI Decoupling**: Trading core never waits for UI rendering
4. **Event-Driven Architecture**: SignalBus pub/sub for cross-component communication

---

## 🎯 Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PHANTOMARBITER                                   │
│                    Institutional-Grade Solana Trading Bot                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        FAST TIER (Rust)                             │   │
│  │                        < 1ms latency                                │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │   │
│  │  │ WSS         │───>│ Race-to-   │───>│ SignalScorer            │ │   │
│  │  │ Aggregator  │    │ First      │    │ (Go/No-Go Decision)     │ │   │
│  │  └─────────────┘    └─────────────┘    └─────────────────────────┘ │   │
│  │  ┌─────────────┐    ┌─────────────┐                                │   │
│  │  │ Cycle       │    │ Multiverse  │    (GIL-Released Rust)         │   │
│  │  │ Finder      │    │ Pathfinding │                                │   │
│  │  └─────────────┘    └─────────────┘                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼ ValidatedSignal                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        MID TIER (Python Async)                      │   │
│  │                        10-50ms latency                              │   │
│  │  ┌─────────────┐              ┌──────────────────────────────────┐ │   │
│  │  │  Director   │──────────────>│    ExecutionBackend              │ │   │
│  │  │  (Orchest.) │              │  ┌────────────┬──────────────┐   │ │   │
│  │  └─────────────┘              │  │PaperBackend│ LiveBackend  │   │ │   │
│  │         │                     │  │(Simulate)  │ (Jito/Jup)   │   │ │   │
│  │         │                     │  └─────┬──────┴──────┬───────┘   │ │   │
│  │         ▼                     └────────┼─────────────┼───────────┘ │   │
│  │  ┌────────────────────┐                │             │             │   │
│  │  │ TacticalStrategy   │                │             │             │   │
│  │  │ PhantomArbiter     │                ▼             ▼             │   │
│  │  │ CapitalManager     │         ┌─────────────────────────┐        │   │
│  │  │ SignalBus          │         │   ShadowManager         │        │   │
│  │  └────────────────────┘         │   (Audit Layer)         │        │   │
│  │                                 └─────────────────────────┘        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       SLOW TIER (Background)                        │   │
│  │                       Minutes-Hours                                 │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│  │  │   Scout     │    │  WhaleWatch │    │  Landlord   │             │   │
│  │  │ (Discovery) │    │   (Alpha)   │    │ (Gas Mgmt)  │             │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    BRIDGE LAYER (TypeScript)                        │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│  │  │ Orca Daemon │    │  Raydium    │    │  Meteora    │             │   │
│  │  │ (Whirlpools)│    │  Daemon     │    │   Bridge    │             │   │
│  │  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │   │
│  │         │ stdio             │ stdio            │ stdio              │   │
│  │         └───────────────────┼──────────────────┘                    │   │
│  │                             ▼                                       │   │
│  │                       Python Bridges                                │   │
│  │               (src/shared/execution/*_bridge.py)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Component Layers

### 1. Fast Tier (Rust - `phantom_core`)

**Purpose**: Sub-millisecond operations that Python cannot achieve due to GIL.

| Module | File | Responsibility |
|--------|------|----------------|
| **WSS Aggregator** | `src_rust/src/wss_aggregator.rs` | Multi-RPC WebSocket deduplication |
| **SignalScorer** | `src_rust/src/scorer.rs` | Go/No-Go signal validation |
| **CycleFinder** | `src_rust/src/cycle_finder.rs` | Bellman-Ford arbitrage detection |
| **Multiverse** | `src_rust/src/multiverse.rs` | 2-5 hop path enumeration |
| **Graph** | `src_rust/src/graph.rs` | Price graph data structure |
| **AMM Math** | `src_rust/src/amm_math.rs` | Constant product/CLMM calculations |
| **Router** | `src_rust/src/router.rs` | Optimal routing logic |
| **InstructionBuilder** | `src_rust/src/instruction_builder.rs` | Solana transaction construction |

**Build**: Via Maturin (PyO3 bindings), installed as Python module `phantom_core`.

---

### 2. Mid Tier (Python Core)

**Purpose**: Business logic, async coordination, and execution management.

#### Orchestration (`src/`)

| Component | File | Responsibility |
|-----------|------|----------------|
| **Director** | `src/director.py` | System lifecycle, process orchestration |
| **SignalBus** | `src/shared/system/signal_bus.py` | Event-driven pub/sub messaging |
| **AppState** | `src/shared/state/app_state.py` | Shared memory for UI updates |

#### Trading Engines

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **PhantomArbiter** | `src/legacy/arbiter/arbiter.py` | Arbitrage engine (legacy location) |
| **TacticalStrategy** | `src/legacy/strategies/tactical.py` | Scalping/trend strategies |
| **DecisionEngine** | `src/strategies/components/decision_engine.py` | RSI/signal logic |
| **TradeExecutor** | `src/strategies/components/trade_executor.py` | Order execution lifecycle |

#### Execution Backend

| Component | File | Responsibility |
|-----------|------|----------------|
| **ExecutionBackend** | `src/shared/execution/execution_backend.py` | Unified Paper/Live interface |
| **PaperBackend** | `execution_backend.py` | Simulation with realistic slippage |
| **LiveBackend** | `execution_backend.py` | Real blockchain execution |
| **ShadowManager** | `src/strategies/components/shadow_manager.py` | Paper vs. Live audit comparison |

#### Infrastructure

| Component | File | Responsibility |
|-----------|------|----------------|
| **CapitalManager** | `src/shared/system/capital_manager.py` | PnL tracking, position management |
| **RpcConnectionManager** | `src/shared/infrastructure/rpc_manager.py` | Multi-RPC failover |
| **WebSocketListener** | `src/shared/infrastructure/websocket_listener.py` | Real-time price feeds |
| **DataBroker** | `src/core/data_broker.py` | Central data aggregation |

---

### 3. Slow Tier (Background Agents)

**Purpose**: Long-running analysis and maintenance tasks.

| Agent | Location | Responsibility |
|-------|----------|----------------|
| **ScoutAgent** | `src/core/scout/agents/scout_agent.py` | Smart money flow tracking |
| **WhaleWatcher** | `src/core/scout/agents/whale_watcher_agent.py` | Alpha wallet shadowing |
| **SniperAgent** | `src/core/scout/agents/sniper_agent.py` | Pump.fun graduation detector |
| **Landlord** | `src/strategies/components/landlord_core.py` | Rent exemption, dust cleanup |

---

### 4. Bridge Layer (TypeScript Daemons)

**Purpose**: Native SDK integration for DEX protocols.

| Bridge | File | Protocol | Communication |
|--------|------|----------|---------------|
| **Orca** | `bridges/orca_daemon.ts` | Whirlpools | stdin/stdout (JSON) |
| **Raydium** | `bridges/raydium_daemon.ts` | CLMM/AMM | stdin/stdout (JSON) |
| **Meteora** | `bridges/meteora_dlmm.ts` | DLMM | stdin/stdout (JSON) |
| **Executor** | `bridges/execution_engine.ts` | Transaction dispatch | stdin/stdout (JSON) |

Python wrappers:
- `src/shared/execution/orca_bridge.py`
- `src/shared/execution/raydium_bridge.py`
- `src/shared/execution/meteora_bridge.py`

---

## 🔄 Data Flow (Signal to Execution)

### The "Hot Path" (Arbitrage)

```
1. [WSS Aggregator (Rust)] ←─ Multiple RPCs (Helius, Triton)
                ↓ Deduplicated price
2. [SignalScorer (Rust)] ──→ Validated signal (Go/No-Go)
                ↓
3. [SignalBus (Python)] ──→ Emit "MARKET_UPDATE" event
                ↓
4. [PhantomArbiter] ──→ CycleFinder checks negative cycles
                ↓ IF profitable
5. [TradeExecutor] ──→ Route to ExecutionBackend
                ↓
6. [LiveBackend] ──→ JITO bundle submission
         │
         └──→ [ShadowManager] Compare Paper vs Live fills
```

**Latency Budget**:
- WSS → Signal: <1ms (Rust)
- Signal → Decision: 3-5ms (Python)
- Decision → Execution: 10-20ms (Network RPC)
- **Total**: 15-25ms end-to-end

---

## 🖥️ User Interfaces

### 1. Rich TUI (`src/dashboard/tui_app.py`)

Terminal-based dashboard using `textual` library:
- Real-time P&L display
- Active positions table
- Trade history log
- System status indicators

**Runs independently** (separate thread, consumes SignalBus events).

### 2. Galaxy Dashboard (`apps/galaxy/`)

Web-based 3D visualization using Three.js:
- Force-directed graph of token relationships
- Live arbitrage cycle visualization
- WebSocket streaming updates

**Runs as separate micro-service** (HTTP API + WS server).

---

## 🛡️ Safety Mechanisms

1. **Paper Trading Default**: `ENABLE_TRADING = False` in `config/settings.py`
2. **ShadowManager**: Audits Paper vs. Live execution drift
3. **IntentRegistry**: Mutex prevents simultaneous strategies on same token
4. **CapitalManager**: Single source of truth for balance/positions
5. **JITO Bundles**: MEV protection via block engine submission

---

## 📂 Directory Layout

```
PhantomArbiter/
├── src/
│   ├── director.py              # System orchestrator
│   ├── core/
│   │   ├── data_broker.py       # Data aggregation
│   │   └── scout/               # Discovery agents
│   ├── shared/
│   │   ├── execution/           # Trade backends + bridges
│   │   ├── infrastructure/      # RPC, WebSocket
│   │   └── system/              # Capital, SignalBus, logging
│   ├── legacy/                  # Deprecated/transitioning code
│   │   ├── arbiter/             # Original arbitrage engine
│   │   └── strategies/          # Original strategy implementations
│   └── strategies/              # Current strategy components
├── src_rust/                    # Rust extension
│   ├── Cargo.toml
│   └── src/                     # 21 Rust modules
├── bridges/                     # TypeScript DEX integrations
│   ├── orca_daemon.ts
│   ├── raydium_daemon.ts
│   └── meteora_dlmm.ts
├── apps/                        # Micro-services
│   ├── galaxy/                  # 3D dashboard
│   ├── datafeed/                # gRPC data service (incubating)
│   └── execution/               # gRPC execution service (incubating)
├── tests/                       # Test suite
└── docs/                        # Documentation
```

---

## 🚀 Roadmap

### Milestone 2: Hybrid Core (Current)
- ✅ Python + Rust + TypeScript integration
- ✅ Multi-DEX support (Orca, Raydium, Meteora)
- ✅ Galaxy dashboard
- 🚧 Rust acceleration expansion

### Milestone 3: Rust Turbo (Planned)
- [ ] Port TA engine (RSI/EMA) to Rust
- [ ] PDA cache optimization
- [ ] Fee estimation engine in Rust

### Milestone 4: Service Mesh (Future)
- [ ] gRPC separation of DataFeed
- [ ] gRPC separation of Execution
- [ ] Independent nonce manager

---

## 📚 Related Documentation

- [COMPONENT_INVENTORY.md](./COMPONENT_INVENTORY.md) - Detailed component list
- [VISUAL_ARCHITECTURE.md](./VISUAL_ARCHITECTURE.md) - Execution flow diagrams
- [DEVELOPMENT.md](./DEVELOPMENT.md) - Contributor guide
- [ADR-0001: Hybrid Architecture](./adr/0001-hybrid-architecture.md)
- [ADR-0002: Rust Acceleration](./adr/0002-rust-acceleration.md)
- [ADR-0003: UI Decoupling](./adr/0003-ui-decoupling.md)
