# PhantomArbiter Architecture

> **Last Updated**: 2026-01-01 | **Phase**: 19 (Great Unification)

## Overview

PhantomArbiter is an **Institutional-Grade Solana Trading System** built on a 3-layer architecture:

| Layer | Purpose | Core Component |
|-------|---------|----------------|
| **A. Market Monitor** | Data ingestion & price discovery | `DataBroker`, `SharedPriceCache`, Rust WSS |
| **B. Execution Layer** | Trade logic & blockchain interaction | `TacticalStrategy`, `ExecutionBackend` |
| **C. Visualization** | Real-time observability | Galaxy Map (Three.js), Rich TUI |

**System Status**: Active Development  
**Python Version**: 3.12+  
**Rust Extension**: `phantom_core` (PyO3/Maturin)

---

## 🏗️ Project Structure

```
PhantomArbiter/
├── main.py                       # Unified CLI Entrypoint
├── config/                       # Shared Configuration
├── build_station.py              # Universal Station Setup
├── data/                         # Persistence Layer (SQLite, JSON)
├── frontend/
│   └── dashboard.html            # 🌌 GALAXY MAP (Three.js Visualization)
│
├── src/
│   ├── strategies/               # ⚡ EXECUTION CORE (Trading Brain)
│   │   ├── tactical.py           # TacticalStrategy (P0 Orchestrator)
│   │   └── components/           # SRP-Extracted Modules
│   │       ├── decision_engine.py    # Trade Signal Analysis
│   │       ├── trade_executor.py     # Execution Lifecycle
│   │       ├── shadow_manager.py     # Paper/Live Audit
│   │       ├── slippage_calibrator.py
│   │       └── congestion_monitor.py
│   │
│   ├── arbiter/                  # 🚀 ARBITRAGE METHOD
│   │   ├── arbiter.py            # Fast-lane arb engine
│   │   ├── core/                 # Spread detection, atomic execution
│   │   └── strategies/           # Multi-hop, triangular arb
│   │
│   ├── core/                     # 📡 MARKET MONITOR
│   │   ├── data_broker.py        # Central data orchestrator
│   │   ├── shared_cache.py       # Atomic price cache (IPC)
│   │   └── scout/                # Token discovery agents
│   │
│   ├── shared/                   # 🔧 INFRASTRUCTURE
│   │   ├── execution/            # Paper/Live backends, DEX bridges
│   │   ├── system/               # SignalBus, CapitalManager, DB
│   │   ├── infrastructure/       # RPC, Jito, WebSocket
│   │   └── feeds/                # Price feed adapters
│   │
│   ├── dashboard/                # 📺 RICH TUI (Terminal)
│   │   └── tui_app.py
│   │
│   └── interface/                # 🌐 REST/WS API
│       └── api_service.py        # FastAPI (/api/v1/galaxy)
│
├── src_rust/                     # ⚡ RUST ACCELERATION
│   └── src/
│       ├── wss_aggregator.rs     # Multi-RPC deduplication
│       ├── scorer.rs             # Signal scoring (<1ms)
│       ├── multiverse.rs         # Multi-hop path scanner
│       └── graph.rs              # Pool matrix
│
├── bridges/                      # 🔗 TypeScript DEX Daemons
│   ├── raydium_daemon.ts
│   ├── orca_daemon.ts
│   └── meteora_dlmm.ts
│
└── tests/                        # Test Suite
```

---

## 🧠 System Design Principles

### 1. Three-Layer Separation

```
┌─────────────────────────────────────────────────┐
│           LAYER C: VISUALIZATION                │
│   Galaxy Map (WebSocket) ←→ Rich TUI (Polling)  │
└─────────────────────────────────────────────────┘
                      ↑ Events
┌─────────────────────────────────────────────────┐
│           LAYER B: EXECUTION                    │
│  TacticalStrategy → ExecutionBackend → Chain    │
│         ↓ Paper          ↓ Live                 │
│    ShadowManager (Audit Comparison)             │
└─────────────────────────────────────────────────┘
                      ↑ Signals
┌─────────────────────────────────────────────────┐
│           LAYER A: MARKET MONITOR               │
│  WSS Aggregator → DataBroker → SharedPriceCache │
│  (Rust <1ms)       (Python)     (Atomic)        │
└─────────────────────────────────────────────────┘
```

### 2. Execution Tiers (SRP)

| Tier | Latency | Responsibility |
|------|---------|----------------|
| 🔴 **P0** | <10ms | `TacticalStrategy.execute_signal()` - blind execution |
| 🟡 **P1** | <100ms | `DecisionEngine.analyze_tick()` - logic filtering |
| 🟢 **P2** | >100ms | Logging, DB writes, Telegram notifications |

### 3. Paper = Live Parity

The `ExecutionBackend` protocol ensures identical slippage calculation:

```python
class ExecutionBackend(Protocol):
    def execute_buy(self, ...) -> TradeResult: ...
    def execute_sell(self, ...) -> TradeResult: ...
    def calculate_slippage(self, ...) -> float: ...  # SHARED

# Implementations
PaperBackend  → Simulates fills, updates CapitalManager
LiveBackend   → Submits via Jito, returns real tx_id
```

`ShadowManager` compares both and logs drift to `shadow_audits.csv`.

---

## 🛠️ Station Setup

```powershell
python build_station.py
```

This handles Python 3.12 checks, venv creation, dependency installation, and Rust extension build.

---

## 📚 Related Documentation

| Document | Purpose |
|----------|---------|
| [COMPONENT_INVENTORY.md](docs/COMPONENT_INVENTORY.md) | Detailed component status |
| [VISUAL_ARCHITECTURE.md](docs/VISUAL_ARCHITECTURE.md) | Signal flow diagrams |
| [TODO.md](docs/TODO.md) | Sprint tracking |
| [AGENT.md](docs/AGENT.md) | AI session resume guide |
