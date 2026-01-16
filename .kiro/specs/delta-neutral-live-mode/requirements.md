# Requirements Document: Delta Neutral Engine Live Mode Integration

## Introduction

The Delta Neutral Engine (Funding Engine) is a sophisticated trading system that maintains market-neutral positions on Drift Protocol by holding spot SOL and shorting SOL-PERP futures. The system earns funding rates while minimizing directional risk. This specification defines requirements for enabling full live trading capabilities through the Web UI, following a phased rollout approach that prioritizes safety and incremental validation.

## Glossary

- **System**: The Delta Neutral Engine (also called Funding Engine)
- **Drift_Protocol**: Solana-based perpetual futures DEX with sub-account support
- **Sub_Account**: Isolated trading account within Drift Protocol (numbered 0, 1, 2...)
- **Health_Ratio**: Metric indicating liquidation risk (100% = safe, 0% = liquidated)
- **Funding_Rate**: Periodic payment between long and short position holders
- **Delta_Drift**: Deviation from perfect hedge (spot SOL vs perp short)
- **Virtual_Driver**: Paper trading simulation engine
- **Drift_Adapter**: Python wrapper for Drift Protocol SDK (driftpy)
- **Engine_Vault**: Isolated capital allocation for a specific trading engine
- **Web_UI**: Browser-based dashboard for engine control
- **WebSocket_Server**: Real-time communication layer between UI and backend

---

## Requirements

### Requirement 1: Paper Mode Simulation Enhancement

**User Story:** As a developer, I want accurate paper trading simulation, so that I can validate business logic before risking real capital.

#### Acceptance Criteria

1. WHEN the System operates in paper mode, THE Virtual_Driver SHALL simulate Drift Protocol behavior including funding rate accrual
2. WHEN a paper mode position is opened, THE Virtual_Driver SHALL track settled and unsettled PnL separately
3. WHEN funding rates are applied in paper mode, THE Virtual_Driver SHALL update position PnL every 8 hours
4. WHEN the Health_Ratio is calculated in paper mode, THE Virtual_Driver SHALL use realistic maintenance margin requirements (5% for SOL-PERP)
5. WHEN a paper mode trade is executed, THE Virtual_Driver SHALL apply realistic slippage (0.1-0.3% based on size)
6. WHEN paper mode positions exceed 10x leverage, THE Virtual_Driver SHALL reject new position increases
7. WHEN the System broadcasts updates in paper mode, THE WebSocket_Server SHALL include all metrics required by Web_UI (health, leverage, positions, PnL)

---

### Requirement 2: Live Mode Read-Only Monitoring

**User Story:** As a trader, I want to monitor my live Drift account health in real-time, so that I can assess liquidation risk without executing trades.

#### Acceptance Criteria

1. WHEN the System starts in live mode with read-only permissions, THE Drift_Adapter SHALL connect to Drift Protocol mainnet
2. WHEN connected to Drift Protocol, THE Drift_Adapter SHALL fetch current sub-account state (collateral, positions, margin)
3. WHEN sub-account data is fetched, THE System SHALL calculate Health_Ratio using maintenance margin and total collateral
4. WHEN Health_Ratio drops below 50%, THE System SHALL emit a warning event to Web_UI
5. WHEN Health_Ratio drops below 20%, THE System SHALL emit a critical alert with liquidation price
6. WHEN positions exist on the sub-account, THE Drift_Adapter SHALL fetch mark prices from Drift oracles
7. WHEN mark prices are updated, THE System SHALL recalculate unrealized PnL for all positions
8. WHEN the System polls account state, THE polling interval SHALL be configurable (default: 10 seconds)
9. WHEN account state changes, THE System SHALL broadcast updates via WebSocket_Server within 500ms

---

### Requirement 3: Live Mode Capital Management

**User Story:** As a trader, I want to deposit and withdraw collateral from my Drift sub-account, so that I can manage capital allocation safely.

#### Acceptance Criteria

1. WHEN a deposit command is received via Web_UI, THE System SHALL validate the amount is positive and less than available wallet balance
2. WHEN a deposit is validated, THE Drift_Adapter SHALL build a Drift deposit instruction for the specified sub-account
3. WHEN a deposit instruction is built, THE System SHALL simulate the transaction before submission
4. IF simulation fails, THEN THE System SHALL reject the deposit and return an error message to Web_UI
5. WHEN a deposit transaction is submitted, THE System SHALL wait for confirmation (max 30 seconds)
6. WHEN a deposit is confirmed, THE System SHALL update Engine_Vault balance and broadcast success to Web_UI
7. WHEN a withdraw command is received, THE System SHALL validate the amount does not violate minimum collateral requirements
8. WHEN a withdraw would cause Health_Ratio to drop below 80%, THE System SHALL reject the withdrawal
9. WHEN a withdraw is executed, THE Drift_Adapter SHALL transfer collateral from sub-account to main wallet
10. WHEN any capital management operation fails, THE System SHALL log the error with full transaction details

---

### Requirement 4: Live Mode Position Lifecycle

**User Story:** As a trader, I want to open and close delta-neutral positions on Drift Protocol, so that I can earn funding rates while managing risk.

#### Acceptance Criteria

1. WHEN an open position command is received, THE System SHALL validate the market exists on Drift Protocol
2. WHEN opening a position, THE System SHALL check current leverage does not exceed configured maximum (default: 5x)
3. WHEN opening a short position, THE Drift_Adapter SHALL build a market order instruction with size and direction
4. WHEN a position order is built, THE System SHALL include a price limit based on current mark price plus slippage tolerance
5. WHEN a position order is submitted, THE System SHALL use Jito bundles for MEV protection if available
6. IF Jito submission fails after 3 retries, THEN THE System SHALL fall back to standard RPC submission
7. WHEN a position is opened successfully, THE System SHALL update Engine_Vault position tracking
8. WHEN a close position command is received, THE System SHALL calculate the exact size needed to flatten the position
9. WHEN closing a position, THE Drift_Adapter SHALL build an offsetting order (buy to close short, sell to close long)
10. WHEN a position is closed, THE System SHALL settle PnL if unsettled PnL exceeds $1.00
11. WHEN settling PnL, THE Drift_Adapter SHALL call the settle_pnl instruction on Drift Protocol
12. WHEN any position operation completes, THE System SHALL broadcast updated position list to Web_UI within 1 second

---

### Requirement 5: Delta Drift Auto-Rebalancing

**User Story:** As a trader, I want the system to automatically correct delta drift, so that my position remains market-neutral without manual intervention.

#### Acceptance Criteria

1. WHEN the System calculates net delta (spot SOL + perp position), THE delta drift percentage SHALL be (net_delta / hedgeable_spot) * 100
2. WHEN delta drift exceeds configured tolerance (default: 1.0%), THE System SHALL generate a rebalance signal
3. WHEN a rebalance signal is generated, THE System SHALL check cooldown period has elapsed (default: 30 minutes)
4. IF cooldown is active, THEN THE System SHALL skip rebalance and log remaining cooldown time
5. WHEN cooldown has elapsed, THE System SHALL calculate correction trade size as absolute value of net delta
6. WHEN correction size is below minimum trade size (default: 0.005 SOL), THE System SHALL skip rebalance
7. WHEN net delta is positive (net long), THE System SHALL expand short position by correction size
8. WHEN net delta is negative (net short), THE System SHALL reduce short position by correction size
9. WHEN a rebalance trade is executed, THE System SHALL update last rebalance timestamp
10. WHEN a rebalance trade fails, THE System SHALL NOT update cooldown timestamp to allow immediate retry

---

### Requirement 6: Safety Gates and Risk Controls

**User Story:** As a risk manager, I want automated safety checks before every trade, so that unprofitable or dangerous trades are prevented.

#### Acceptance Criteria

1. WHEN any trade is proposed, THE System SHALL estimate total costs (gas, Jito tip, slippage, fees)
2. WHEN costs are estimated, THE System SHALL calculate expected revenue from funding rates
3. IF expected revenue is less than estimated costs, THEN THE System SHALL reject the trade as unprofitable
4. WHEN checking profitability, THE System SHALL use conservative funding rate estimates (50% of current rate)
5. WHEN network latency exceeds configured threshold (default: 500ms), THE System SHALL reject trades
6. WHEN SOL balance is below reserved amount (default: 0.017 SOL), THE System SHALL reject trades requiring gas
7. WHEN leverage would exceed maximum allowed (default: 5x), THE System SHALL reject position increases
8. WHEN Health_Ratio would drop below 60% after a trade, THE System SHALL reject the trade
9. WHEN a safety gate blocks a trade, THE System SHALL log the reason and broadcast to Web_UI
10. WHEN in live mode, THE System SHALL require explicit user confirmation for trades exceeding $100 USD

---

### Requirement 7: Engine Vault Synchronization

**User Story:** As a system architect, I want engine vaults to accurately reflect on-chain sub-account state, so that capital allocation is tracked correctly.

#### Acceptance Criteria

1. WHEN the System starts in live mode, THE Engine_Vault SHALL be initialized with the current sub-account balance
2. WHEN sub-account collateral changes, THE Engine_Vault balance SHALL be updated within 10 seconds
3. WHEN positions are opened or closed, THE Engine_Vault SHALL track position sizes and entry prices
4. WHEN funding payments are received, THE Engine_Vault SHALL update realized PnL
5. WHEN the Web_UI requests vault status, THE System SHALL return current balance, allocated capital, and available capital
6. WHEN multiple engines use different sub-accounts, THE System SHALL maintain separate Engine_Vault instances
7. WHEN a vault sync fails, THE System SHALL retry up to 3 times with exponential backoff
8. IF vault sync fails after retries, THEN THE System SHALL emit an error event and disable trading

---

### Requirement 8: WebSocket Command Protocol

**User Story:** As a frontend developer, I want a consistent WebSocket API for engine control, so that the UI can reliably manage the engine.

#### Acceptance Criteria

1. WHEN the Web_UI sends a START_ENGINE command, THE System SHALL validate mode parameter is "paper" or "live"
2. WHEN starting in live mode, THE System SHALL initialize Drift_Adapter and verify wallet connection
3. WHEN the Web_UI sends a STOP_ENGINE command, THE System SHALL gracefully stop monitoring loops
4. WHEN the Web_UI sends a DRIFT_DEPOSIT command, THE System SHALL execute Requirement 3 (Capital Management)
5. WHEN the Web_UI sends a DRIFT_WITHDRAW command, THE System SHALL execute Requirement 3 (Capital Management)
6. WHEN the Web_UI sends a DRIFT_OPEN_POSITION command, THE System SHALL execute Requirement 4 (Position Lifecycle)
7. WHEN the Web_UI sends a DRIFT_CLOSE_POSITION command, THE System SHALL execute Requirement 4 (Position Lifecycle)
8. WHEN any command is received, THE System SHALL respond within 5 seconds with success or error status
9. WHEN a command fails, THE System SHALL return a structured error with code and human-readable message
10. WHEN the System broadcasts updates, THE message type SHALL be one of: FUNDING_UPDATE, COMMAND_RESULT, ENGINE_STATUS

---

### Requirement 9: Error Handling and Recovery

**User Story:** As a system operator, I want robust error handling, so that transient failures don't crash the engine or leave positions orphaned.

#### Acceptance Criteria

1. WHEN an RPC call fails, THE System SHALL retry up to 3 times with exponential backoff (1s, 2s, 4s)
2. WHEN a transaction simulation fails, THE System SHALL log the error and reject the trade without retrying
3. WHEN a transaction is submitted but confirmation times out, THE System SHALL query transaction status for 60 seconds
4. IF transaction status cannot be determined, THEN THE System SHALL mark the operation as "unknown" and alert the user
5. WHEN Drift_Adapter loses connection, THE System SHALL attempt reconnection every 10 seconds
6. WHEN reconnection succeeds, THE System SHALL re-sync account state before resuming operations
7. WHEN a critical error occurs (wallet missing, invalid sub-account), THE System SHALL stop the engine and broadcast error
8. WHEN an error is logged, THE log entry SHALL include timestamp, error type, context, and stack trace
9. WHEN the System recovers from an error, THE System SHALL broadcast a recovery event to Web_UI
10. WHEN in live mode, THE System SHALL never execute trades during error recovery

---

### Requirement 10: Logging and Observability

**User Story:** As a developer, I want comprehensive logging using Loguru, so that I can debug issues and monitor system health.

#### Acceptance Criteria

1. THE System SHALL use Loguru for all logging (no print() statements)
2. WHEN the System starts, THE log level SHALL be configurable via environment variable (default: INFO)
3. WHEN a trade is executed, THE System SHALL log: timestamp, market, side, size, price, tx_signature
4. WHEN account state is updated, THE System SHALL log: health_ratio, leverage, total_collateral, free_collateral
5. WHEN an error occurs, THE System SHALL log with ERROR level and include exception details
6. WHEN a safety gate blocks a trade, THE System SHALL log with WARNING level
7. WHEN the System calculates profitability, THE System SHALL log: expected_revenue, estimated_costs, net_profit
8. WHEN logs are written to file, THE rotation policy SHALL be daily with 30-day retention
9. WHEN in production, THE System SHALL log to both file and stderr
10. WHEN debugging, THE System SHALL support DEBUG level logging with detailed state dumps

---

## Non-Functional Requirements

### Performance
- Account state polling: ≤ 10 seconds interval
- WebSocket broadcast latency: ≤ 500ms
- Transaction confirmation timeout: ≤ 30 seconds
- Health calculation: ≤ 100ms

### Security
- Private keys stored in environment variables only
- No private keys logged or transmitted via WebSocket
- All transactions simulated before submission
- Explicit user confirmation for trades > $100 USD

### Reliability
- System uptime: > 99% during trading hours
- RPC failover: Automatic with 3 retry attempts
- State persistence: Vault state saved every 60 seconds
- Graceful degradation: Read-only mode if trading fails

### Maintainability
- Type hints on all public functions (PEP 484)
- Loguru for all logging (no print())
- Rich for CLI output
- SOLID principles compliance
- Property-based tests for critical paths

---

## Acceptance Criteria Testing Strategy

### Property-Based Tests (PBT)
- Delta drift calculation: For any spot and perp amounts, drift % should be mathematically correct
- Health ratio calculation: For any collateral and margin, health should be in [0, 100]
- Profitability estimation: For any funding rate and costs, net profit calculation should be accurate
- Position sizing: For any leverage and collateral, position size should not exceed limits

### Unit Tests
- Specific examples for each command (deposit, withdraw, open, close)
- Edge cases: zero balances, maximum leverage, minimum trade sizes
- Error conditions: invalid markets, insufficient funds, network failures

### Integration Tests
- End-to-end flow: Start engine → Open position → Monitor health → Close position → Stop engine
- WebSocket protocol: Send commands, verify responses, check state updates
- Vault synchronization: Verify on-chain state matches Engine_Vault state

---

## Dependencies

- **driftpy**: Drift Protocol Python SDK (≥ 0.7.0)
- **solana**: Solana Python SDK (≥ 0.32.0)
- **solders**: Solana types library (≥ 0.21.0)
- **loguru**: Logging library (≥ 0.7.0)
- **websockets**: WebSocket server (≥ 12.0)
- **aiohttp**: Async HTTP client (≥ 3.9.0)

---

## Constraints

1. Must maintain backward compatibility with existing paper mode
2. Must not modify core Drift Protocol contracts
3. Must support Windows, Linux, and macOS
4. Must work with Python 3.12+
5. Must integrate with existing Web UI without breaking other engines

---

## Assumptions

1. User has a funded Solana wallet with private key in .env
2. User has created a Drift Protocol account (sub-account 0 exists)
3. RPC endpoint supports WebSocket subscriptions
4. Jito Block Engine is available for MEV protection
5. User understands perpetual futures trading risks

---

**Document Version**: 1.0  
**Created**: 2026-01-15  
**Status**: Draft - Awaiting Review
