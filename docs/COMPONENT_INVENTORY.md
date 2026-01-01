# PhantomArbiter Component Inventory

> **Last Updated**: 2026-01-01 | **Phase**: 19 (Great Unification)

## 🧠 System Core (Orchestration)

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **Director** | `src/director.py` | ✅ Active | Top-level supervisor. Manages Fast/Mid/Slow lanes. |
| **SignalBus** | `src/shared/system/signal_bus.py` | ✅ Active | Unified Event Bus (Pub/Sub) connecting components. |
| **IntentRegistry** | `src/shared/system/signal_bus.py` | ✅ Active | Mutex: Prevents strategy collisions by locking tokens. |
| **App State** | `src/shared/state/app_state.py` | ✅ Active | Shared memory for TUI updates and global status. |

## ⚙️ Trading Engine (Mid-Lane / Intelligence)

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **TacticalStrategy** | `src/strategies/tactical.py` | ✅ Active | Main orchestrator (formerly TradingCore). Tick loop. |
| **DecisionEngine** | `src/strategies/components/decision_engine.py` | ✅ Active | Strategy Logic: RSI/Trends, Buy/Sell commands. |
| **TradeExecutor** | `src/strategies/components/trade_executor.py` | ✅ Active | Execution Lifecycle: Risk, Order Creation, Audit. |
| **ShadowManager** | `src/strategies/components/shadow_manager.py` | ✅ Active | Audit Layer: Compares Live vs. Paper drift. |
| **CongestionMonitor** | `src/strategies/components/congestion_monitor.py` | ✅ Active | Dynamic Speed: Scales Jito tips based on lag. |
| **SlippageCalibrator** | `src/strategies/components/slippage_calibrator.py` | ✅ Active | Self-Correction: Adjusts tolerance based on drift. |
| **PositionSizer** | `src/strategies/components/position_sizer.py` | ✅ Active | Risk Management: Kelly/ATR position sizing. |
| **LandlordCore** | `src/strategies/components/landlord_core.py` | ✅ Active | Inventory Manager: Dust cleanup, rent exemption. |
| **ML Filter** | `src/ml/xgboost_filter.py` | 🟡 Optional | Loaded dynamically if `.pkl` model exists. |

## ⚡ Arbitrage Engine (Fast-Lane)

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **PhantomArbiter** | `src/arbiter/arbiter.py` | ✅ Active | Dedicated Arb engine entry point. |
| **SpreadDetector** | `src/arbiter/core/spread_detector.py` | ✅ Active | Scans for price discrepancies across pools. |
| **AtomicExecutor** | `src/arbiter/core/atomic_executor.py` | ✅ Active | Atomic transaction building (buy+sell in one tx). |
| **ArbDetector** | `src/shared/execution/arb_detector.py` | ✅ Active | Shared logic for detecting arb opportunities. |
| **HopGraphEngine** | `src/arbiter/core/hop_engine.py` | ✅ Active | Multi-hop path calculation via Rust. |

## 🕵️ Intelligence Agents (Slow-Lane)

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **ScoutAgent** | 🔴 **MISSING** | ❌ Broken | Token Discovery: needs restoration. |
| **WhaleWatcher** | 🔴 **MISSING** | ❌ Broken | Confidence Injection: needs restoration. |
| **SniperAgent** | 🔴 **MISSING** | ❌ Broken | Graduation Sniper: needs restoration. |

*Note: Agent files were orphaned in `src/scraper/`. Restoration planned for Phase 5.*

## 🏗️ Execution & Infrastructure

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **ExecutionBackend** | `src/shared/execution/execution_backend.py` | ✅ Active | Unified interface for Live/Paper backends. |
| **CapitalManager** | `src/shared/system/capital_manager.py` | ✅ Active | Source of Truth for PnL, Positions, Equity. |
| **RpcConnectionManager** | `src/shared/infrastructure/rpc_manager.py` | ✅ Active | Failover: Auto-switches RPCs on failure. |
| **WebSocketListener** | `src/shared/infrastructure/websocket_listener.py` | ✅ Active | Data Ingestion: Raydium/Orca logs. |
| **RaydiumBridge** | `src/shared/execution/raydium_bridge.py` | ✅ Active | Adapter for Raydium swaps (v4/AMM). |
| **OrcaBridge** | `src/shared/execution/orca_bridge.py` | ✅ Active | Adapter for Orca Whirlpools. |
| **MeteoraBridge** | `src/shared/execution/meteora_bridge.py` | ✅ Active | Adapter for Meteora DLMM. |
| **JitoAdapter** | `src/shared/infrastructure/jito_adapter.py` | ✅ Active | MEV Protection: Bundled transactions. |
| **JupiterSwapper** | `src/shared/execution/swapper.py` | ✅ Active | Jupiter V6 API integration. |

## 🦀 Rust Extension (phantom_core)

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **WssAggregator** | `src_rust/src/wss_aggregator.rs` | ✅ Active | Multi-RPC deduplication (<1ms). |
| **SignalScorer** | `src_rust/src/scorer.rs` | ✅ Active | Go/No-Go signal scoring. |
| **Multiverse** | `src_rust/src/multiverse.rs` | ✅ Active | 2-5 Hop path scanner. |
| **CycleFinder** | `src_rust/src/cycle_finder.rs` | ✅ Active | Bellman-Ford cycle detection. |

## 🌌 Visualization

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **Galaxy Map** | `frontend/dashboard.html` | ✅ **CANONICAL** | Three.js 3D visualization. |
| **Rich TUI** | `src/dashboard/tui_app.py` | ✅ Active | Terminal UI dashboard. |
| **viz/** | `_deprecated/viz/` | 🔴 Archived | Superseded Svelte+TS app. |
| **prism_hud/** | `_deprecated/prism_hud/` | 🔴 Archived | Superseded Svelte+Tailwind app. |
