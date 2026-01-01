# PhantomArbiter API Reference

> **Last Updated**: 2026-01-01

Auto-generated documentation for Core Components.

---

# Module: `src.strategies.tactical`

## TacticalStrategy

P0 Orchestrator for the V10.2 SRP Architecture.

The TacticalStrategy is responsible for the high-frequency event loop (Tick Loop).
It delegates specialized tasks to sub-components while maintaining
strict zero-delay execution for the core cycle.

**Priority Level**: P0 (Critical execution path, no blocking I/O)

**Attributes**:
- `wallet` (WalletManager): Manages Solana keypairs and balances.
- `swapper` (JupiterSwapper): Executes trades via Jupiter API.
- `portfolio` (PortfolioManager): Manages capital allocation and risk state.
- `decision_engine` (DecisionEngine): Pure logic component for trade analysis.
- `data_manager` (DataFeedManager): Batched data fetching and injection.
- `watchers` (dict): Active asset state containers.
- `executor` (TradeExecutor): Handles trade execution lifecycle.
- `execution_backend` (ExecutionBackend): Paper or Live backend.

### Methods

| Method | Description |
|--------|-------------|
| `initialize()` | Async initialization (network/RPC calls). |
| `scan_signals()` | Scan watchers and return trade signals. |
| `execute_signal(signal)` | Execute a resolved signal. |
| `set_live_mode(live)` | Switch between LIVE and PAPER modes. |

---

# Module: `src.strategies.components.decision_engine`

## DecisionEngine

P1 Logic Engine for V10.2 SRP.

The DecisionEngine is a pure logic component that encapsulates all trading rules.
It accepts current state (Watcher, Price) and returns explicit decisions.

**Priority Level**: P1 (Logic Layer)

**Attributes**:
- `portfolio` (PortfolioManager): Reference to portfolio state for risk checks.

### Methods

| Method | Description |
|--------|-------------|
| `analyze_tick(watcher, price)` | Returns: (Action, Reason, Size). Action: 'BUY', 'SELL', 'HOLD' |
| `inject_agent_signal(data)` | Inject external signal (e.g., from Scout). |

---

# Module: `src.strategies.components.trade_executor`

## TradeExecutor

P0 Execution Lifecycle Manager.

Handles risk checks, order creation, and audit hooks.
Delegates actual blockchain interaction to ExecutionBackend.

### Methods

| Method | Description |
|--------|-------------|
| `execute_buy(...)` | Execute a buy order. |
| `execute_sell(...)` | Execute a sell order. |
| `update_ml_model(model)` | Hot-reload ML filter. |

---

# Module: `src.shared.execution.execution_backend`

## ExecutionBackend (Protocol)

Unified interface for Live/Paper execution.

```python
class ExecutionBackend(Protocol):
    def execute_buy(self, ...) -> TradeResult: ...
    def execute_sell(self, ...) -> TradeResult: ...
    def calculate_slippage(self, ...) -> float: ...  # SHARED
```

### Implementations

| Class | Description |
|-------|-------------|
| `PaperBackend` | Simulates fills, updates CapitalManager state. |
| `LiveBackend` | Submits via Jito, returns real tx_id. |

---

# Module: `src.shared.system.capital_manager`

## CapitalManager

V40.0: Central Source of Truth for PnL, Positions, and Equity.

**Singleton Access**: `get_capital_manager()`

### Methods

| Method | Description |
|--------|-------------|
| `get_balance()` | Get current balance. |
| `record_trade(...)` | Record a completed trade. |
| `get_positions()` | Get all open positions. |

---

# Module: `src.strategy.watcher`

## Watcher

P1 State Container for V10.2 SRP.

Represents a single asset being traded. Operates as a passive
state container holding entry price, position status, and PnL metrics.

### Methods

| Method | Description |
|--------|-------------|
| `get_price()` | Retrieve last price. |
| `get_rsi()` | Get RSI from DataFeed. |
| `inject_price(price)` | Update price data. |
| `enter_position(...)` | Record position entry. |
| `exit_position(...)` | Record position exit. |

---

# Module: `src.shared.system.db_manager`

## DBManager

V10.5: Database Manager (SQLite).
Singleton class for ACID-compliant persistence.

### Methods

| Method | Description |
|--------|-------------|
| `cursor()` | Context manager for database interaction. |
| `log_trade(...)` | Insert a completed trade record. |
| `save_position(...)` | Upsert position state. |
| `get_position(mint)` | Retrieve position state. |
| `get_all_positions()` | Get all active positions. |
