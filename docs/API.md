# PhantomTrader API Reference

Auto-generated documentation for Core Components.

# Module: `src.engine.trading_core`

## TradingCore

P0 Orchestrator for the V10.2 SRP Architecture.

The TradingCore is responsible for the high-frequency event loop (Tick Loop).
It delegating specialized tasks to sub-components while maintaining
strict zero-delay execution for the core cycle.

Priority Level: P0 (Critical execution path, no blocking I/O)

Attributes:
    wallet (WalletManager): Manages Solana keypairs and balances.
    swapper (JupiterSwapper): Executes trades via Jupiter API.
    portfolio (PortfolioManager): Manages capital allocation and risk state.
    decision_engine (DecisionEngine): Pure logic component for trade analysis.
    data_manager (DataFeedManager): Batched data fetching and injection.
    watchers (dict): Active asset state containers.

### `__init__`
*No documentation available.*

### `run_live`
P0 Main Loop: Zero Delay Orchestration.

### `run_tick`
Execute one atomic tick.

# Module: `src.engine.decision_engine`

## DecisionEngine

P1 Logic Engine for V10.2 SRP.

The DecisionEngine is a pure logic component that encapsulates all trading rules.
It accepts current state (Watcher, Price) and returns explicit decisions.
It contains no internal state other than references to configuration/portfolio context.

Priority Level: P1 (Logic Layer)

Attributes:
    portfolio (PortfolioManager): Reference to portfolio state for risk checks.

### `__init__`
*No documentation available.*

### `analyze_tick`
Analyze a single watcher tick.
Returns: (Action, Reason, Size)
Action: 'BUY', 'SELL', 'HOLD'

# Module: `src.engine.data_feed_manager`

## DataFeedManager

Manages data Ingestion for the TradingCore.
Decouples 'How to get data' from the Core Loop.

### `__init__`
*No documentation available.*

### `update_prices`
Batch fetch prices for all watchers and inject them.
Returns: Map of {mint: price}

# Module: `src.strategy.watcher`

## Watcher

P1 State Container for V10.2 SRP.

The Watcher represents a single asset being traded. It operates as a passive
state container, holding critical data such as entry price, position status,
and PnL metrics. It delegates all complex logic to specialized modules.

Responsibility:
- Hold State (In-Memory)
- Delegate Persistence -> PositionManager
- Delegate Display -> StatusFormatter
- Consume Data <- DataFeedManager

Attributes:
    symbol (str): Asset symbol (e.g., 'SOL').
    mint (str): Asset mint address.
    data_feed (DataFeed): Price history and technical indicators container.
    pos_manager (PositionManager): Persistence handler.

### `__init__`
*No documentation available.*

### `enter_position`
*No documentation available.*

### `exit_position`
*No documentation available.*

### `get_detailed_status`
*No documentation available.*

### `get_price`
Retrieve last price (Passive).

### `get_price_count`
*No documentation available.*

### `get_rsi`
Get RSI from DataFeed.

### `inject_price`
Update price data.

### `save_state`
Persist current state.

# Module: `src.system.db_manager`

## DBManager

V10.5: Database Manager (SQLite)
Singleton class for ACID-compliant persistence.
Replaces JSON/CSV files for Trades and Positions.

### `cursor`
Context manager for database interaction.

### `delete_position`
Remove position state (on exit).

### `get_all_positions`
Get all active positions.

### `get_connection`
Get a configured SQLite connection.

### `get_position`
Retrieve position state.

### `log_trade`
Insert a completed trade record.

### `save_position`
Upsert position state.

# Module: `src.system.data_source_manager`

## DataSourceManager

P2 Data Reliability Manager (DSM).

The DataSourceManager ensures robust price data availability by implementing
a tiered fallback system. It prevents the 'Zombie Broker' state where
RPC rate limits causing cooldowns starve the application of data.

Tiers:
- Tier 1 (High Quality): Jupiter RPC / SmartRouter. Best precision, rate-limited.
- Tier 2 (High Availability): DexScreener API. Good availability, less precise.

Priority Level: P2 (Infrastructure)

Behavior:
Switching to Tier 2 triggers a strict cooldown (default 30s) before
attempting to restore Tier 1 service.

### `__init__`
*No documentation available.*

### `get_prices`
Fetch prices for a list of mints, handling tier switching automatically.
Returns: {mint: price}

# Module: `src.execution.position_manager`

## PositionManager

Manages persistence logic for a Watcher using DBManager.

### `__init__`
*No documentation available.*

### `clear_state`
Delete persisted state from DB.

### `load_state`
Load state from DB.

### `persist_state`
Save state to DB.

### `recover_legacy_state`
Recover state from token balance if no DB record.

