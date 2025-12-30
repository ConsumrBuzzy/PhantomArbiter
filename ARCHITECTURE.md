# PhantomArbiter Architecture

## Overview
PhantomArbiter operates on a **Single Engine Base** architecture. The system uses a unified, high-performance execution core (`src/engine`) which is driven by two distinct **Market Methods** depending on the operational context:
1.  **Arbiter**: Spatial/Triangular arbitrage for established pools.
2.  **Scraper**: High-speed discovery and sniping for new launches.

**System Status**: Active Development
**Python Version**: 3.12+

## 🏗️ Project Structure

```
PhantomArbiter/
├── main.py                    # Unified CLI Entrypoint ("Select Your Method")
├── config/                    # Shared Configuration
├── build_station.py           # Universal Station Setup Script
├── data/                      # Shared Persistence Layer
├── src/
│   ├── engine/                # ⚡ THE ENGINE BASE (Shared Core)
│   │   ├── trading_core.py    # Zero-alloc tick loop
│   │   ├── decision_engine.py # Logic processor
│   │   └── execution/         # Abstracted Executor
│   │
│   ├── arbiter/               # 🚀 METHOD 1: Arbitrage
│   │   ├── strategies/        # Logic: "Find price discrepancies"
│   │   └── core/              # Adapters to feed Engine with Arb signals
│   │
│   ├── scraper/               # 🔎 METHOD 2: Scraper
│   │   ├── discovery/         # Logic: "Find new tokens"
│   │   └── agents/            # Adapters to feed Engine with Snipe signals
│   │
│   └── shared/                # Common Infrastructure (Feeds, Logs)
└── tests/                     # Comprehensive Test Suite
```

## 🧠 System Design Principles

### 1. Single Engine, Multiple Methods
The **Engine Base** (`src/engine`) provides the "Muscle":
- **Tick Loop**: <10ms event processing.
- **Position Management**: Validating and holding state.
- **Execution**: Routing trades to the blockchain.

The **Methods** provide the "Brain":
- **Arbiter Method**: Scans for spread > fees. Injects `BUY` signal into Engine.
- **Scraper Method**: Scans for new pool creation. Injects `SNIPE` signal into Engine.

### 2. Execution Tiers (SRP)
The Core Engine ensures zero-delay execution by enforcing strict tiers.

#### 🔴 P0: Execution Core
- **Cycle Time**: <10ms
- **Responsibility**: Takes a Signal from *any* Method and executes it blindly and immediately.
- **Optimization**: No memory allocation in the hot loop.

#### 🟡 P1: Logic Adaptation (The Methods)
- **Cycle Time**: <100ms
- **Arbiter**: Calculates cross-DEX spreads.
- **Scraper**: Filters HoneyPot/RugPull risks.
- **Output**: Standardized `TradeSignal` passed to P0.

#### 🟢 P2: Infrastructure
- **Responsibility**: Logging, Database, Async API calls.

## 🛠️ Station Setup
Use the unified builder to set up any workstation:
```powershell
python build_station.py
```
This handles Python 3.12 checks, `venv` creation, and dependency installation.
