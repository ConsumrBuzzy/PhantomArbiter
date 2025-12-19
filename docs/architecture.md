# PhantomTrader Architecture (V10.2 SRP)

## Overview

PhantomTrader V10.2 adopts a **Single Responsibility Principle (SRP)** architecture, decoupling high-speed execution from slow I/O operations. The system is organized into three priority tiers to ensure zero-delay trading.

## Priority Tiers

### 🔴 P0: Execution Core (The "Doer")
*   **Component**: `TradingCore` (`src/engine/trading_core.py`)
*   **Responsibility**: High-frequency event loop (Ticks). Manages the lifecycle of a trade from signal to transaction.
*   **Constraints**: NO blocking I/O. NO print statements. NO API calls (except execution).
*   **Cycle Time**: < 10ms

### 🟡 P1: Logic & Data (The "Thinker")
*   **Components**: 
    *   `DecisionEngine` (`src/engine/decision_engine.py`): Pure logic. Input State -> Output Signal.
    *   `DataFeedManager` (`src/engine/data_feed_manager.py`): Batch data fetching.
*   **Responsibility**: Providing the Core with actionable data and decisions.
*   **Behavior**: `DataFeedManager` injects price updates into Watchers. `DecisionEngine` reads Watcher state to return `BUY`/`SELL` signals.

### 🟢 P2: Infrastructure & Support (The "Helper")
*   **Components**:
    *   `PriorityQueue` (`src/system/priority_queue.py`): Async logging, alerts, and record keeping.
    *   `DiscoveryDaemon` (`src/engine/discovery_daemon.py`): Slow background tasks (Scouting, Grading).
    *   `DataBroker`: Independent process for reliable price feeds.
*   **Responsibility**: Offloading all non-critical work from the Core.

---

## Core Components

### 1. TradingCore (`src.engine.trading_core.TradingCore`)
The orchestrator. It holds references to all sub-systems but delegates actual work.
*   **Loop**: `run_tick()` -> `update_cash()` -> `update_prices()` -> `analyze_tick()` -> `execute_trade()`.

### 2. DecisionEngine (`src.engine.decision_engine.DecisionEngine`)
The brain. It contains no state of its own but implements all trading rules.
*   **Inputs**: `Watcher` (State), `Price`.
*   **Outputs**: `Action` (BUY/SELL/HOLD), `Reason`, `Size`.
*   **Logic**: RSI checks, TSL updates, Stop Loss, Take Profit, Risk checks.

### 3. DataSourceManager (DSM) (`src.system.data_source_manager.DataSourceManager`)
The data guardian. Ensures reliable price feeds by switching sources on failure.
*   **Tier 1**: Jupiter RPC (SmartRouter). Fast, precise, rate-limited.
*   **Tier 2**: DexScreener API. Slower, highly available fallback.
*   **Auto-Switch**: If Tier 1 fails 2x, switch to Tier 2 for 30s.

### 4. Watcher (`src.strategy.watcher.Watcher`)
The state container. Represents a single asset being traded.
*   **Role**: Passive data holder.
*   **State**: `entry_price`, `in_position`, `pnl_pct`, `trailing_stop_price`.
*   **Delegates**: Persistence -> `PositionManager`, Display -> `StatusFormatter`.

### 5. DBManager (V10.5) (`src.system.db_manager.DBManager`)
The persistence layer.
*   **Technology**: SQLite (`data/trading_journal.db`).
*   **Responsibility**: ACID-compliant storage for Trades and Positions.
*   **Tables**: `trades`, `positions`, `assets`.


---

## Data Flow

1.  **Price Injection**: `DataBroker` (or `DataFeedManager`) fetches prices -> Injects into `SharedPriceCache`.
2.  **State Update**: `TradingCore` calls `DataFeedManager` -> Updates `Watcher` from Cache.
3.  **Decision**: `TradingCore` calls `DecisionEngine.analyze_tick(watcher)`.
4.  **Signal**: `DecisionEngine` evaluates TSL/RSI -> Returns `SELL`.
5.  **Execution**: `TradingCore` calls `JupiterSwapper.execute_swap()`.
6.  **Logging**: `TradingCore` pushes log to `PriorityQueue` (Async).

## Directory Structure

```
src/
├── engine/           # P0/P1 Components (TradingCore, DecisionEngine)
├── execution/        # Blockchain Interaction (Wallet, Swapper)
├── strategy/         # Trading Rules & State (Watcher, Risk, Signals)
├── system/           # Infrastructure (Logging, RPC, Queue, DSM)
├── core/             # Shared Utilities (DataFeed, Cache, Validator)
└── tools/            # Standalone Scripts (AssetManager, Scout)
```
