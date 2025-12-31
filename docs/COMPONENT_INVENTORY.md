# PhantomArbiter Component Inventory

## 🧠 System Core (Orchestration)
The central nervous system managing data flow and lifecycle.

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **Director** | `src/engine/director.py` | ✅ Active | Top-level supervisor. Manages Fast/Mid/Slow lanes and task lifecycle. |
| **GlobalRiskGovernor** | `src/engine/risk_governor.py` | ✅ **NEW** | **Safety**: Enforces capital partitioning (70/30) and kill switches. |
| **SignalBus** | `src/shared/system/signal_bus.py` | ✅ Active | Unified Event Bus (Pub/Sub) connecting detailed components. |
| **IntentRegistry** | `src/shared/system/signal_bus.py` | ✅ **NEW** | **Mutex**: Prevents strategy collisions by locking tokens. |
| **App State** | `src/shared/state/app_state.py` | ✅ Active | Shared memory for TUI updates and global status. |

## ⚙️ Trading Engine (Mid-Lane / Intelligence)
The primary decision-making brain for scalping and trend trading.

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **TradingCore** | `src/engine/trading_core.py` | ✅ Active | Main logic hub. Wires up components and manages the trade loop. |
| **DecisionEngine** | `src/engine/decision_engine.py` | ✅ Active | Strategy Logic: Analyzes signals, checks RSI/Trends, issues Buy/Sell commands. |
| **TradeExecutor** | `src/engine/trade_executor.py` | ✅ Active | Execution Lifecycle: Handles Risk, Order Creation, and Audit Hooks. |
| **ShadowManager** | `src/engine/shadow_manager.py` | ✅ Active | **Audit Layer**: Compares Live vs. Paper execution to track "Drift". |
| **CongestionMonitor** | `src/engine/congestion_monitor.py` | ✅ Active | **Dynamic Speed**: Scales Jito tips based on network lag. |
| **SlippageCalibrator** | `src/engine/slippage_calibrator.py` | ✅ Active | **Self-Correction**: Adjusts tolerance based on recent drift. |
| **PositionSizer** | `src/engine/position_sizer.py` | ✅ Active | Risk Management: Calculates trade size based on Kelly/ATR. |
| **ML Filter** | `src/ml/xgboost_filter.py` | 🟡 Linked | Loaded dynamically if `.pkl` model exists. |

## ⚡ Arbitrage Engine (Fast-Lane)
High-frequency module for detecting and executing rigid arbitrage opportunities.

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **PhantomArbiter** | `src/arbiter/arbiter.py` | ✅ Active | Dedicated Arb engine entry point. |
| **SpreadDetector** | `src/arbiter/core/spread_detector.py` | ✅ Active | Scans for price discrepancies across pools. |
| **AtomicExecutor** | `src/arbiter/core/atomic_executor.py` | ✅ Active | Handles atomic transaction building (buy+sell in one tx). |
| **ArbDetector** | `src/shared/execution/arb_detector.py` | ✅ Active | Shared logic for detecting arb opps. |

## 🕵️ Intelligence Agents (Slow-Lane)
Async agents performing heavy analysis and discovery.

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **ScoutAgent** | `src/scraper/agents/scout_agent.py` | ✅ Active | Token Discovery: Hunts new pools and filters for rug checks. |
| **WhaleWatcher** | `src/scraper/agents/whale_watcher_agent.py` | ✅ Active | **Confidence Injection**: Monitors large wallets for social proof. |
| **Landlord** | `src/engine/landlord_core.py` | ✅ Active | Inventory Manager: Cleans up dust and enforces rent exemptions. |
| **SniperAgent** | `src/scraper/agents/sniper_agent.py` | ✅ Active | **Graduation Sniper**: Targets pump.fun -> Raydium migrations. |

## 🏗️ Execution & Infrastructure (The Body)
The "limbs" that interact with the blockchain.

| Component | File Path | Status | Description |
|-----------|-----------|--------|-------------|
| **RpcConnectionManager** | `src/shared/infrastructure/rpc_manager.py` | ✅ Active | **Failover**: Auto-switches RPCs on failure; Latency routing. |
| **WebSocketListener** | `src/shared/infrastructure/websocket_listener.py` | ✅ Active | Data Ingestion: Consumes Raydium/Orca logs. |
| **ExecutionBackend** | `src/shared/execution/execution_backend.py` | ✅ Active | Unified interface for Live/Paper backends. |
| **RaydiumBridge** | `src/shared/execution/raydium_bridge.py` | ✅ Active | Adapter for Raydium swaps (v4/AMM). |
| **OrcaBridge** | `src/shared/execution/orca_bridge.py` | ✅ Active | Adapter for Orca Whirlpools. |
| **MeteoraBridge** | `src/shared/execution/meteora_bridge.py` | ✅ Active | Adapter for Meteora DLMM (Dynamic Liquidity). |
| **JitoAdapter** | `src/speed/jito_adapter.py` | ✅ Active | **MEV Protection**: Sends bundled transactions via Jito. |

## 🔮 Potential & External Components
Components referenced but currently external, simulated, or missing.

| Component | Status | Description |
|-----------|--------|-------------|
| **phantom_core (Rust)** | ❌ Missing | Compiled Rust extension for Flash Log Decryption. Currently mocked/bypassed via Python. |
| **WssAggregator (Rust)** | ❌ Simulated | High-speed deduplication. Currently handled by `WebSocketListener` (Python). |
