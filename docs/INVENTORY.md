# System Inventory & Component Audit

**Last Updated:** 2026-01-01

## 🏷️ Status Legend

* 🟢 **Active**: Critical path, currently running in production.
* 🟡 **Legacy / Maintenance**: Usage discouraged, superseded by newer systems.
* 🔴 **Deprecated / Dead**: Archived or deleted.
* 🟣 **Restorable**: Valuable logic that is currently disconnected.

## 🧠 Core Engine

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Director** | `src/director.py` | 🟢 Active | Main Orchestrator, manages Strategy Bridge and Agents. |
| **Arbiter** | `src/arbiter/arbiter.py` | 🟢 Active | High-frequency arbitrage agent (Fast Lane). |
| **TacticalStrategy** | `src/strategies/tactical.py` | 🟢 Active | Execution engine (replaces old TradingCore). |
| **DecisionEngine** | `src/strategies/components/decision_engine.py` | 🟢 Active | Trade logic analysis. |

## 💰 Financial & Execution

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **CapitalManager** | `src/shared/system/capital_manager.py` | 🟢 Active | Source of Truth for PnL, Positions, Equity. |
| **PaperWallet** | `src/shared/execution/paper_wallet.py` | 🟢 Active | V45 Adapter wrapping CapitalManager. |
| **ExecutionBackend** | `src/shared/execution/execution_backend.py` | 🟢 Active | Paper/Live backend protocol. |
| **PortfolioManager** | `src/strategy/portfolio.py` | 🟡 Legacy | Superseded by CapitalManager (V40.0). |
| **JupiterSwapper** | `src/shared/execution/swapper.py` | 🟢 Active | Jito tips, Smart Routing, Jupiter V6 API. |

## 📡 Infrastructure & Data

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **SignalBus** | `src/shared/system/signal_bus.py` | 🟢 Active | Cross-Strategy Nerve Link. |
| **SmartRouter** | `src/shared/system/smart_router.py` | 🟢 Active | RPC Load Balancing & Rate Limit. |
| **SharedPriceCache** | `src/core/shared_cache.py` | 🟢 Active | Atomic IPC lock for price sharing. |
| **PhantomCore** | `src_rust/` | 🟢 Active | Rust Extension (RSI, EMAs, WSS). |
| **FastClient** | `src/shared/system/fast_client.py` | 🟢 Active | Python-side Bridge for Rust WSS. |
| **DataBroker** | `src/core/data_broker.py` | 🟢 Active | Central data orchestrator. |

## 🌌 Visualization

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Galaxy Map** | `frontend/dashboard.html` | 🟢 **CANONICAL** | Three.js 3D visualization. |
| **Rich TUI** | `src/dashboard/tui_app.py` | 🟢 Active | Terminal UI dashboard. |
| **viz/** | `_deprecated/viz/` | 🔴 Archived | Superseded by Galaxy Map. |
| **prism_hud/** | `_deprecated/prism_hud/` | 🔴 Archived | Superseded by Galaxy Map. |

## 🧪 Backtesting & Simulation

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Backtester** | `src/shared/backtesting/backtester.py` | 🟢 Active | Uses CapitalManager for PnL simulation. |
| **DataFetcher** | `src/shared/backtesting/data_fetcher.py` | 🟣 Restorable | Historical data integration. |

## 📚 Documentation

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Master TODO** | `docs/TODO.md` | 🟢 Active | Central sprint planning. |
| **Architecture** | `ARCHITECTURE.md` | 🟢 Active | 3-layer system design. |
| **Inventory** | `docs/INVENTORY.md` | 🟢 Active | This file. |

## 🧹 Housekeeping Status

| Action | Status |
| :--- | :--- |
| ~~Delete `src/core/capital_manager.py`~~ | ✅ Done (V40.0) |
| ~~Delete `src/engine/` source files~~ | ✅ Done (refactored to strategies/) |
| ~~Archive `viz/` and `prism_hud/`~~ | ✅ Done (2026-01-01) |
| Migrate `PortfolioManager` refs | 📋 Planned |
| Restore `src/scraper/` agents | 📋 Planned |
