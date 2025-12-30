# System Inventory & Component Audit

**Last Updated:** 2025-12-30

## 🏷️ Status Legend

* 🟢 **Active**: Critical path, currently running in production.
* 🟡 **Legacy / Maintenance**: usage discouraged, superseded by newer systems, but still imported.
* 🔴 **Deprecated / Dead**: Code that is no longer used and should be archived/deleted.
* 🟣 **Restorable**: Valuable logic that is currently disconnected but worth preserving.

## 🧠 Core Engine

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Director** | `src/engine/director.py` | 🟢 Active | Main Orchestrator, manages Strategy Bridge and Agents. |
| **Arbiter** | `src/arbiter/arbiter.py` | 🟢 Active | High-frequency arbitrage agent (Fast Lane). |
| **Scalper** | `src/engine/trading_core.py` | 🟢 Active | Execution engine for Scalping strategies (Mid Lane). |
| **DecisionEngine** | `src/engine/decision_engine.py` | 🟡 Legacy | Mostly delegated to `MerchantEnsemble`, but still provides base structure. |

## 💰 Financial & Execution

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **CapitalManager** | `src/shared/system/capital_manager.py` | 🟢 Active | **Source of Truth** for PnL, Positions, and Equity. |
| **PaperWallet** | `src/shared/execution/paper_wallet.py` | 🟢 Active | V45 Adapter. Wraps CapitalManager (Live). |
| **PortfolioManager**| `src/strategy/portfolio.py` | 🟡 Legacy | Superseded by CapitalManager (V40.0). refactor planned. |
| **CapitalManager (Dup)**| `src/core/capital_manager.py` | 💀 Deleted | removed as duplicate of `shared/system` (V40.0 matched). |
| **JupiterSwapper** | `src/shared/execution/swapper.py` | 🟢 Active | Handles Jito tips, Smart Routing, and Jupiter V6 API. |

## 📡 Infrastructure & Data

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **SignalBus** | `src/shared/system/signal_bus.py` | 🟢 Active | Cross-Strategy Nerve Link (`SCALP`, `ARB`, `TIP`). |
| **SmartRouter** | `src/shared/system/smart_router.py` | 🟢 Active | RPC Load Balancing & Rate Limit management. |
| **SharedPriceCache** | `src/core/shared_cache.py` | 🟢 Active | Atomic IPC lock for price sharing between Broker and Engines. |
| **PhantomCore** | `src_rust/` | 🟢 Active | Rust Extension for heavy calculation (RSI, EMAs) & WSS Race-to-First. |
| **FastClient** | `src/shared/system/fast_client.py` | 🟢 Active | Python-side Bridge for Rust WSS Aggregator. |
| **RaceSpeedometer** | `src/dashboard/race_tracker.py` | 🟢 Active | Real-time RPC Performance Dashboard (Rich TUI). |

## 🧪 Backtesting & Simulation (The "Extensive System")

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Backtester** | `src/shared/backtesting/backtester.py` | 🟢 Active | **V9.0 Unified**: Uses `CapitalManager` for realistic PnL/Fee simulation. |
| **DataFetcher** | `src/shared/backtesting/data_fetcher.py` | 🟣 Restorable | Historical data integration. |
| **Adapters** | `src/shared/backtesting/adapters.py` | 🟢 Active | Bridges for strategy logic to run in backtest mode. |
| **WSS Monitor** | `scripts/monitor_race.py` | 🟢 Active | Standalone visualizer for WSS latency stats. |
| **Latency Trace** | `scripts/trace_latency.py` | 🟢 Active | Signal-to-Execution lag measurement utility. |

## 📚 Documentation

| Component | Path | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Master TODO** | `docs/TODO.md` | 🟢 Active | Central project tracking and sprint planning. |
| **Optimization** | `docs/PHASE_OPTIMIZATION.md` | 🟢 Active | Details on "Institutional Realism" phase (Rust, Latency). |
| **Inventory** | `docs/INVENTORY.md` | 🟢 Active | This file. |

## 🧹 Housekeeping Actions

1. **Delete** `src/core/capital_manager.py` (Avoid confusion).
2. **Migrate** remaining `PortfolioManager` refs to `CapitalManager`.
3. **Docs**: Ensure usage of `src/backtesting` is documented in `README.md` if we plan to use it.
