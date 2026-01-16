# Design Document: Delta Neutral Engine Live Mode Integration

## Overview

This design extends the existing Delta Neutral Engine (Funding Engine) to enable full live trading capabilities through the Web UI. The system already has a working paper mode implementation and partial live mode support. This spec focuses on completing the Web UI integration to display live market opportunities and enable position management.

**Current State:**
- ✅ Paper mode fully functional with VirtualDriver
- ✅ Live mode core logic implemented in `FundingEngine`
- ✅ DriftAdapter for protocol interaction exists
- ✅ Safety gates and risk management implemented
- ✅ WebSocket server infrastructure in place (`run_dashboard.py`)
- ✅ Base UI template exists (`engine-drift.html`)
- ⚠️ Missing: Live market data feed to UI
- ⚠️ Missing: Position management UI interactions
- ⚠️ Missing: "Take Position" / "Leave Position" buttons

**What Needs to be Built:**
1. Backend API endpoint for Drift funding rates (`/api/drift/markets`)
2. Frontend JavaScript to fetch and display market opportunities
3. WebSocket command handlers for position management (OPEN_POSITION, CLOSE_POSITION)
4. UI components for "Take" and "Leave" position actions

The system operates in two modes:
- **Paper Mode**: Simulated trading using VirtualDriver for validation
- **Live Mode**: Real trading on Drift Protocol mainnet with comprehensive safety controls

Key architectural decisions:
1. **Composition over Inheritance**: Protocol adapters, risk gates, and vault managers are composed rather than inherited
2. **Interface Segregation**: Separate interfaces for read-only monitoring vs. trading operations
3. **Dependency Injection**: All external dependencies (RPC, WebSocket, Drift SDK) are injected for testability
4. **Async-First**: All I/O operations use asyncio for non-blocking execution
5. **Existing Infrastructure**: Leverage existing WebSocket server and engine architecture

## Architecture

### Existing System Architecture

```mermaid
graph TB
    UI[Web UI<br/>engine-drift.html] -->|HTTP GET| API[/api/drift/markets]
    UI -->|WebSocket| WS[DashboardServer<br/>:8765]
    
    API -->|Fetch| DFF[DriftFundingFeed]
    DFF -->|Query| Drift[Drift Protocol]
    
    WS -->|Commands| FE[FundingEngine]
    FE -->|Paper| VD[VirtualDriver]
    FE -->|Live| DA[DriftAdapter]
    
    DA -->|driftpy| Drift
    DA -->|RPC| Solana[Solana RPC]
    
    FE -->|Check| SG[SafetyGate]
    FE -->|Sync| VM[VaultManager]
    
    FE -->|Broadcast| WS
    WS -->|JSON| UI
    
    style API fill:#4CAF50
    style DFF fill:#4CAF50
    style FE fill:#2196F3
    style UI fill:#FF9800
```

### Data Flow: Market Opportunities Display

```
1. [Browser] ──HTTP GET──> [/api/drift/markets]
                                    ↓
2. [API Handler] ──Query──> [DriftFundingFeed.get_funding_rates_sync()]
                                    ↓
3. [DriftFundingFeed] ──RPC──> [Drift Protocol Oracle]
                                    ↓
4. [API Handler] ──JSON──> [Browser]
                                    ↓
5. [JavaScript] ──Render──> [Funding Table + Opportunity Cards]
```

### Data Flow: Position Management

```
1. [User] ──Click "Take"──> [JavaScript]
                                    ↓
2. [JavaScript] ──WebSocket──> {action: "DRIFT_OPEN_POSITION", market, direction, size}
                                    ↓
3. [DashboardServer] ──Route──> [FundingEngine.execute_funding_command()]
                                    ↓
4. [FundingEngine] ──Check──> [SafetyGate.can_execute()]
                                    ↓
5. [FundingEngine] ──Execute──> [DriftAdapter.open_position()]
                                    ↓
6. [DriftAdapter] ──Transaction──> [Drift Protocol]
                                    ↓
7. [FundingEngine] ──Sync──> [VaultManager.sync_from_drift()]
                                    ↓
8. [FundingEngine] ──Broadcast──> [WebSocket] ──> [UI Update]
```

---

## Components and Interfaces

### 1. Backend Components (Existing)

#### FundingEngine (`src/engines/funding/logic.py`)
**Status**: ✅ Implemented

Core engine that manages delta-neutral positions. Inherits from `BaseEngine`.

**Key Methods:**
```python
class FundingEngine(BaseEngine):
    async def start() -> None
    async def stop() -> None
    async def tick() -> None  # Auto-rebalancing loop
    async def check_and_rebalance(simulate: bool) -> dict
    async def execute_funding_command(action: str, data: dict) -> dict
    async def _sync_vault_from_drift(max_retries: int = 3) -> None
    async def _check_health_warnings(health_ratio: float) -> None
```

**Supported Commands:**
- `DEPOSIT`: Add collateral to Drift sub-account
- `WITHDRAW`: Remove collateral from Drift sub-account
- `OPEN_POSITION`: Open new perp position (long/short)
- `CLOSE_POSITION`: Close existing perp position

**State Tracking:**
- `self.live_mode`: Boolean flag for paper vs. live
- `self.drift_adapter`: DriftAdapter instance (live mode only)
- `self.driver`: VirtualDriver instance (paper mode only)
- `self.last_rebalance`: Timestamp of last auto-rebalance

#### DriftAdapter (`src/engines/funding/drift_adapter.py`)
**Status**: ✅ Implemented (assumed based on usage)

Wrapper around driftpy SDK for protocol interaction.

**Key Methods:**
```python
class DriftAdapter:
    async def connect(wallet: WalletManager, sub_account: int) -> bool
    async def disconnect() -> None
    async def get_account_state() -> dict
    async def deposit(amount: float) -> str  # Returns tx signature
    async def withdraw(amount: float) -> str
    async def open_position(market: str, direction: str, size: float) -> str
    async def close_position(market: str, settle_pnl: bool) -> str
```

**Account State Schema:**
```python
{
    "collateral": float,  # Total collateral in USD
    "positions": [
        {
            "market": str,  # e.g., "SOL-PERP"
            "side": str,  # "long" or "short"
            "size": float,  # Position size in base asset
            "entry_price": float,
            "mark_price": float,
            "total_pnl": float,
            "settled_pnl": float,
            "unrealized_pnl": float
        }
    ],
    "health_ratio": float,  # 0-100
    "leverage": float,  # Current leverage multiplier
    "margin_requirement": float  # Maintenance margin in USD
}
```

#### SafetyGate (`src/delta_neutral/safety_gates.py`)
**Status**: ✅ Implemented

Unified safety validation before trade execution.

**Key Methods:**
```python
class SafetyGate:
    async def can_execute(
        wallet: any,
        latency_monitor: any,
        expected_profit_usd: float,
        trade_amount_usd: float,
        sol_price: float,
        jito_tip_lamports: int
    ) -> bool
```

**Safety Checks:**
1. **FeeGuard**: Ensures profit > 2x fees
2. **OracleLatencyShield**: Rejects if RPC latency > 300ms
3. **BalanceGuard**: Validates sufficient SOL for gas + USDC reserves

#### DriftFundingFeed (`src/shared/feeds/drift_funding.py`)
**Status**: ⚠️ Needs Enhancement

Fetches funding rates from Drift Protocol.

**Current Interface:**
```python
class DriftFundingFeed:
    def get_funding_rates_sync() -> dict[str, float]
    # Returns: {"SOL-PERP": 0.0001, "BTC-PERP": 0.00015, ...}
```

**Required Enhancement:**
```python
@dataclass
class FundingMarket:
    symbol: str
    rate_1h: float  # Hourly rate
    rate_8h: float  # 8-hour rate
    apr: float  # Annualized rate
    direction: str  # "shorts" or "longs" (who receives funding)
    open_interest: float  # Total OI in USD
    volume_24h: float  # 24h volume in USD

class DriftFundingFeed:
    def get_funding_markets() -> list[FundingMarket]
    def get_market_stats() -> dict
    # Returns: {"total_oi": float, "volume_24h": float, "avg_funding": float}
```

### 2. Frontend Components (Existing)

#### Dashboard HTML (`frontend/templates/engine-drift.html`)
**Status**: ✅ Template exists, needs JavaScript integration

**Key Sections:**
- Health Gauge: Visual health ratio display (0-100%)
- Market Opportunities: Funding rates table + best opportunities cards
- Combat Zone: Active positions table
- Quick Actions: Deposit/Withdraw/Settle PnL buttons
- Delta Neutrality: Net delta display

**Missing Elements:**
- "Take Position" buttons in opportunity cards
- "Leave Position" buttons in positions table
- Market data refresh logic
- WebSocket command handlers

#### Dashboard JavaScript (`frontend/js/app.js`)
**Status**: ✅ Core infrastructure exists, needs funding-specific handlers

**Existing Infrastructure:**
```javascript
class DashboardApp {
    constructor()
    connect()  // WebSocket connection
    sendCommand(action, payload)  // Send commands to backend
    handlePacket(packet)  // Route incoming messages
    updateEngineStates(engines)  // Update engine status
}
```

**Required Additions:**
```javascript
// Market data fetching
async fetchDriftMarkets()
renderFundingTable(markets)
renderOpportunityCards(opportunities)

// Position management
handleTakePosition(market, direction, size)
handleLeavePosition(market)
handleDriftUpdate(data)  // WebSocket handler for FUNDING_UPDATE
```

### 3. WebSocket Server (`run_dashboard.py`)
**Status**: ✅ Implemented with LocalDashboardServer

**Existing Command Handlers:**
- `START_ENGINE`: Start funding engine
- `STOP_ENGINE`: Stop funding engine
- `DRIFT_DEPOSIT`: Deposit collateral
- `DRIFT_WITHDRAW`: Withdraw collateral
- `DRIFT_OPEN_POSITION`: Open position
- `DRIFT_CLOSE_POSITION`: Close position

**Message Types:**
- `FUNDING_UPDATE`: Broadcast engine status (health, positions, leverage)
- `COMMAND_RESULT`: Response to user commands
- `ENGINE_STATUS`: Engine state updates

---

## Data Models

### Market Opportunity (Frontend)
```typescript
interface MarketOpportunity {
    symbol: string;        // "SOL-PERP"
    rate_1h: number;       // 0.0001 (0.01%)
    rate_8h: number;       // 0.0008 (0.08%)
    apr: number;           // 8.76 (8.76% APR)
    direction: string;     // "shorts" or "longs"
    open_interest: number; // 125000000 ($125M)
    volume_24h: number;    // 450000000 ($450M)
}
```

### Position (Frontend)
```typescript
interface Position {
    market: string;         // "SOL-PERP"
    side: string;           // "long" or "short"
    size: number;           // 10.5 SOL
    entry_price: number;    // 145.50
    mark_price: number;     // 147.20
    unrealized_pnl: number; // 17.85
    liq_price: number;      // 120.00
}
```

### Engine Status (WebSocket)
```typescript
interface FundingUpdate {
    type: "FUNDING_UPDATE";
    payload: {
        timestamp: string;
        spot_sol: number;
        perp_sol: number;
        net_delta: number;
        drift_pct: number;
        sol_price: number;
        health: number;           // 0-100
        total_collateral: number;
        equity: number;
        maintenance_margin: number;
        leverage: number;
        positions: Position[];
        free_collateral: number;
    };
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I've identified several areas where properties can be consolidated:

**Redundancy Analysis:**
1. Properties 2.4 and 2.5 (health warnings at 50% and 20%) can be combined into a single property about health threshold warnings
2. Properties 5.7 and 5.8 (rebalance direction for positive/negative delta) can be combined into one property about correct rebalance direction
3. Properties 7.1, 7.2, 7.3, 7.4 (vault synchronization) can be consolidated into comprehensive vault sync properties
4. Properties 8.4, 8.5, 8.6, 8.7 (command routing) are integration tests, not properties
5. Properties 10.3, 10.4, 10.7 (log completeness) can be combined into a single property about log field completeness

**Consolidated Property Set:**
After removing redundancies and combining related properties, we have approximately 45 unique testable properties covering:
- Paper mode simulation accuracy (7 properties)
- Live mode monitoring and health (6 properties)
- Capital management validation (8 properties)
- Position lifecycle (10 properties)
- Delta drift rebalancing (8 properties)
- Safety gates (9 properties)
- Vault synchronization (5 properties)
- Error handling and recovery (7 properties)
- Logging (5 properties)

### Core Correctness Properties

#### Property 1: Paper Mode Funding Accrual
*For any* paper mode position with size S and funding rate R, after one 8-hour cycle, the settled PnL should increase by S × R × mark_price
**Validates: Requirements 1.1, 1.2, 1.3**

#### Property 2: Health Ratio Calculation
*For any* collateral C and maintenance margin M, the health ratio should equal (C / M) × 100, clamped to [0, 100]
**Validates: Requirements 1.4, 2.3**

#### Property 3: Slippage Modeling
*For any* paper mode trade of size S, the applied slippage percentage should be within [0.1%, 0.3%] and increase with trade size
**Validates: Requirements 1.5**

#### Property 4: Leverage Limit Enforcement
*For any* position that would result in leverage > 10x in paper mode or > 5x in live mode, the system should reject the position increase
**Validates: Requirements 1.6, 4.2, 6.7**

#### Property 5: WebSocket Message Completeness
*For any* FUNDING_UPDATE broadcast, the message should contain all required fields: health, leverage, positions, collateral, margin, delta
**Validates: Requirements 1.7, 8.10**

#### Property 6: Health Warning Thresholds
*For any* health ratio H, if H < 50%, a WARNING should be emitted; if H < 20%, a CRITICAL alert should be emitted
**Validates: Requirements 2.4, 2.5**

#### Property 7: PnL Recalculation on Price Update
*For any* position with entry price E and new mark price M, unrealized PnL should be recalculated as (M - E) × size × (1 if long else -1)
**Validates: Requirements 2.7**

#### Property 8: Broadcast Latency
*For any* account state change, the WebSocket broadcast should occur within 500ms
**Validates: Requirements 2.9**

#### Property 9: Deposit Validation
*For any* deposit amount A and wallet balance B, the deposit should be accepted if and only if 0 < A ≤ B
**Validates: Requirements 3.1**

#### Property 10: Simulation Failure Rejection
*For any* transaction that fails simulation, the system should reject the operation and return an error without retrying
**Validates: Requirements 3.4, 9.2**

#### Property 11: Vault Balance Synchronization
*For any* successful deposit or withdrawal of amount A, the Engine_Vault balance should change by exactly ±A within 10 seconds
**Validates: Requirements 3.6, 7.2**

#### Property 12: Withdrawal Health Check
*For any* withdrawal that would cause health ratio to drop below 80%, the withdrawal should be rejected
**Validates: Requirements 3.8, 6.8**

#### Property 13: Market Validation
*For any* position command with market M, the command should be accepted if and only if M exists in the set of valid Drift markets
**Validates: Requirements 4.1**

#### Property 14: Price Limit Calculation
*For any* market order with mark price P and slippage tolerance S, the price limit should be P × (1 + S) for buys and P × (1 - S) for sells
**Validates: Requirements 4.4**

#### Property 15: Position Close Sizing
*For any* existing position with size S, a close position command should generate an offsetting order of size exactly S
**Validates: Requirements 4.8**

#### Property 16: Conditional PnL Settlement
*For any* position close operation, if unsettled PnL > $1.00, the settle_pnl instruction should be called
**Validates: Requirements 4.10**

#### Property 17: Position Broadcast Latency
*For any* position operation completion, the updated position list should be broadcast within 1 second
**Validates: Requirements 4.12**

#### Property 18: Delta Drift Calculation
*For any* spot amount S, perp amount P, and reserved amount R, delta drift percentage should equal ((S - R + P) / (S - R)) × 100
**Validates: Requirements 5.1**

#### Property 19: Rebalance Signal Generation
*For any* delta drift D and tolerance T, a rebalance signal should be generated if and only if |D| > T
**Validates: Requirements 5.2**

#### Property 20: Cooldown Enforcement
*For any* rebalance signal generated within cooldown period C, the rebalance should be skipped
**Validates: Requirements 5.3, 5.4**

#### Property 21: Correction Size Calculation
*For any* net delta D, the correction trade size should equal |D|
**Validates: Requirements 5.5**

#### Property 22: Minimum Trade Size Filter
*For any* correction size C and minimum size M, if C < M, the rebalance should be skipped
**Validates: Requirements 5.6**

#### Property 23: Rebalance Direction
*For any* net delta D, if D > 0 the system should expand short, if D < 0 the system should reduce short
**Validates: Requirements 5.7, 5.8**

#### Property 24: Rebalance Timestamp Update
*For any* successful rebalance, the last_rebalance timestamp should be updated; for failed rebalances, it should not be updated
**Validates: Requirements 5.9, 5.10**

#### Property 25: Cost Estimation
*For any* trade with Jito tip T, swap amount A, and SOL price P, total cost should include T×P + A×0.001 + A×0.0002 + base_fee
**Validates: Requirements 6.1**

#### Property 26: Revenue Calculation
*For any* position size S, funding rate R, and SOL price P, expected revenue should equal S × R × P
**Validates: Requirements 6.2**

#### Property 27: Profitability Check
*For any* trade with expected revenue E and estimated cost C, the trade should be rejected if E < C
**Validates: Requirements 6.3**

#### Property 28: Conservative Funding Estimate
*For any* funding rate R used in profitability calculations, the system should use 0.5 × R
**Validates: Requirements 6.4**

#### Property 29: Latency Kill-Switch
*For any* network latency L and threshold T, if L > T, all trades should be rejected
**Validates: Requirements 6.5**

#### Property 30: Balance Guard
*For any* SOL balance B and reserved amount R, if B < R, trades requiring gas should be rejected
**Validates: Requirements 6.6**

#### Property 31: Vault Initialization
*For any* engine start in live mode, the Engine_Vault balance should equal the Drift sub-account balance
**Validates: Requirements 7.1**

#### Property 32: Position Tracking
*For any* position opened or closed, the Engine_Vault should maintain accurate records of size and entry price
**Validates: Requirements 7.3**

#### Property 33: Funding PnL Update
*For any* funding payment received, the Engine_Vault realized PnL should increase by the funding amount
**Validates: Requirements 7.4**

#### Property 34: Vault Status Response
*For any* vault status request, the response should contain balance, allocated_capital, and available_capital fields
**Validates: Requirements 7.5**

#### Property 35: Vault Isolation
*For any* two engines E1 and E2 using different sub-accounts, they should have separate Engine_Vault instances
**Validates: Requirements 7.6**

#### Property 36: Vault Sync Retry
*For any* vault sync failure, the system should retry up to 3 times with exponential backoff (1s, 2s, 4s)
**Validates: Requirements 7.7, 9.1**

#### Property 37: Vault Sync Failure Handling
*For any* vault sync that fails after 3 retries, the system should emit an error event and disable trading
**Validates: Requirements 7.8**

#### Property 38: Mode Validation
*For any* START_ENGINE command with mode M, the command should be accepted if and only if M ∈ {"paper", "live"}
**Validates: Requirements 8.1**

#### Property 39: Command Response Latency
*For any* WebSocket command, the system should respond within 5 seconds
**Validates: Requirements 8.8**

#### Property 40: Error Response Structure
*For any* failed command, the error response should contain both an error code and a human-readable message
**Validates: Requirements 8.9**

#### Property 41: Transaction Confirmation Timeout
*For any* submitted transaction, if confirmation is not received within 30 seconds, the system should query status for up to 60 seconds total
**Validates: Requirements 9.3**

#### Property 42: Unknown Transaction Handling
*For any* transaction whose status cannot be determined after 60 seconds, the system should mark it as "unknown" and alert the user
**Validates: Requirements 9.4**

#### Property 43: Reconnection Attempts
*For any* Drift_Adapter disconnection, the system should attempt reconnection every 10 seconds
**Validates: Requirements 9.5**

#### Property 44: Post-Reconnection Sync
*For any* successful reconnection, the system should re-sync account state before resuming operations
**Validates: Requirements 9.6**

#### Property 45: Trade Blocking During Recovery
*For any* error recovery period, the system should reject all trade execution attempts
**Validates: Requirements 9.10**

#### Property 46: Trade Log Completeness
*For any* executed trade, the log entry should contain: timestamp, market, side, size, price, tx_signature
**Validates: Requirements 10.3**

#### Property 47: State Log Completeness
*For any* account state update, the log entry should contain: health_ratio, leverage, total_collateral, free_collateral
**Validates: Requirements 10.4**

#### Property 48: Error Log Level
*For any* error occurrence, the log entry should use ERROR level and include exception details
**Validates: Requirements 10.5**

#### Property 49: Safety Gate Log Level
*For any* trade blocked by a safety gate, the log entry should use WARNING level
**Validates: Requirements 10.6**

#### Property 50: Profitability Log Completeness
*For any* profitability calculation, the log entry should contain: expected_revenue, estimated_costs, net_profit
**Validates: Requirements 10.7**

---

## Error Handling

### Error Categories

1. **Validation Errors** (User-Recoverable)
   - Invalid market names
   - Insufficient balance
   - Leverage limits exceeded
   - Health ratio violations
   - **Response**: Return structured error to UI, do not retry

2. **Network Errors** (Transient)
   - RPC timeouts
   - WebSocket disconnections
   - Oracle data staleness
   - **Response**: Retry with exponential backoff (1s, 2s, 4s), max 3 attempts

3. **Protocol Errors** (Requires Investigation)
   - Transaction simulation failures
   - Drift account not initialized
   - Invalid instruction data
   - **Response**: Log error with full context, alert user, do not retry

4. **Critical Errors** (System Halt)
   - Wallet keypair missing
   - Vault desynchronization after retries
   - Partial transaction execution (one leg fails)
   - **Response**: Stop engine, broadcast critical alert, require manual intervention

### Error Recovery Flows

#### RPC Failure Recovery
```
1. RPC call fails
2. Log warning with attempt number
3. Wait backoff period (1s, 2s, 4s)
4. Retry up to 3 times
5. If all retries fail:
   - Log error with full context
   - Return error to caller
   - Do NOT execute trade
```

#### Vault Sync Failure Recovery
```
1. Vault sync fails
2. Log warning with attempt number
3. Wait backoff period (1s, 2s, 4s)
4. Retry up to 3 times
5. If all retries fail:
   - Emit VAULT_SYNC_ERROR event
   - Disable trading (set flag)
   - Alert user via WebSocket
   - Require manual vault reset
```

#### Transaction Confirmation Timeout
```
1. Transaction submitted
2. Wait for confirmation (max 30s)
3. If timeout:
   - Query transaction status
   - Poll every 5s for 60s total
4. If status determined:
   - Process result (success/failure)
5. If status unknown after 60s:
   - Mark as "unknown"
   - Alert user with transaction signature
   - Recommend manual verification on explorer
```

#### Partial Execution (Leg Failure)
```
1. Spot leg executes successfully
2. Perp leg fails
3. Detect partial execution
4. IMMEDIATE ROLLBACK:
   - Calculate offsetting trade
   - Execute emergency close
   - Log full details
   - Alert user
5. If rollback fails:
   - CRITICAL ALERT
   - Stop engine
   - Require manual intervention
```

---

## Testing Strategy

### Dual Testing Approach

The system requires both unit tests and property-based tests for comprehensive coverage:

**Unit Tests** (Specific Examples):
- Specific market scenarios (SOL-PERP at $150)
- Edge cases (zero balance, maximum leverage)
- Error conditions (invalid market, network timeout)
- Integration points (WebSocket commands, API endpoints)

**Property-Based Tests** (Universal Properties):
- Delta drift calculations across all input ranges
- Health ratio calculations for any collateral/margin combination
- Profitability checks for any funding rate and cost combination
- Validation logic for any input values

### Property-Based Testing Configuration

**Library**: Use `hypothesis` for Python property-based testing

**Configuration**:
```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100)  # Minimum 100 iterations per property
@given(
    spot_sol=st.floats(min_value=0.0, max_value=1000.0),
    perp_sol=st.floats(min_value=-1000.0, max_value=0.0),
    reserved_sol=st.floats(min_value=0.01, max_value=0.02)
)
def test_delta_drift_calculation(spot_sol, perp_sol, reserved_sol):
    """
    Feature: delta-neutral-live-mode
    Property 18: Delta drift percentage calculation
    
    For any spot amount S, perp amount P, and reserved amount R,
    delta drift percentage should equal ((S - R + P) / (S - R)) × 100
    """
    # Test implementation
    pass
```

**Test Organization**:
```
tests/
├── unit/
│   ├── test_funding_engine.py
│   ├── test_drift_adapter.py
│   ├── test_safety_gates.py
│   └── test_vault_manager.py
├── property/
│   ├── test_delta_calculations.py
│   ├── test_health_calculations.py
│   ├── test_profitability_checks.py
│   └── test_validation_logic.py
└── integration/
    ├── test_websocket_commands.py
    ├── test_market_data_api.py
    └── test_end_to_end_flow.py
```

### Test Data Generators

**For Property Tests**:
```python
# Generate valid market names
valid_markets = st.sampled_from(["SOL-PERP", "BTC-PERP", "ETH-PERP"])

# Generate realistic funding rates (-0.01% to +0.01%)
funding_rates = st.floats(min_value=-0.0001, max_value=0.0001)

# Generate position sizes (0.001 to 100 SOL)
position_sizes = st.floats(min_value=0.001, max_value=100.0)

# Generate health ratios (0 to 100)
health_ratios = st.floats(min_value=0.0, max_value=100.0)

# Generate SOL prices ($50 to $500)
sol_prices = st.floats(min_value=50.0, max_value=500.0)
```

### Critical Path Testing

**High-Priority Properties** (Test First):
1. Property 18: Delta drift calculation (core algorithm)
2. Property 2: Health ratio calculation (safety critical)
3. Property 27: Profitability check (prevents losses)
4. Property 29: Latency kill-switch (prevents bad execution)
5. Property 37: Vault sync failure handling (data integrity)

**Integration Tests** (End-to-End):
1. Start engine → Open position → Monitor health → Close position → Stop engine
2. Fetch market data → Display opportunities → Take position → Leave position
3. Deposit collateral → Open position → Auto-rebalance → Withdraw collateral
4. Simulate network failure → Verify reconnection → Verify state sync
5. Trigger safety gate → Verify trade blocked → Verify UI notification

---

## Implementation Plan

### Phase 1: Backend API Enhancement (2-3 hours)

**Task 1.1**: Enhance DriftFundingFeed
- Add `FundingMarket` dataclass with all required fields
- Implement `get_funding_markets()` method
- Implement `get_market_stats()` method
- Add caching to reduce RPC calls (5-minute TTL)

**Task 1.2**: Update API Endpoint
- Modify `/api/drift/markets` handler in `run_dashboard.py`
- Use enhanced DriftFundingFeed
- Return full market data with stats
- Add error handling for RPC failures

**Task 1.3**: Test API Endpoint
- Verify response schema matches frontend expectations
- Test with mock data
- Test with live Drift data
- Verify caching behavior

### Phase 2: Frontend Market Display (3-4 hours)

**Task 2.1**: Implement Market Data Fetching
- Add `fetchDriftMarkets()` method to DashboardApp
- Call on page load and every 30 seconds
- Handle loading states
- Handle error states

**Task 2.2**: Implement Funding Table Rendering
- Add `renderFundingTable(markets)` method
- Sort by APR (highest first)
- Color-code positive/negative rates
- Add "Take" button for each market

**Task 2.3**: Implement Opportunity Cards
- Add `renderOpportunityCards(opportunities)` method
- Show top 3 opportunities
- Display APR, direction, OI
- Add "Take Position" button

**Task 2.4**: Implement Market Stats Display
- Update total OI, 24h volume, avg funding
- Add number formatting (K, M, B suffixes)
- Update on each data refresh

### Phase 3: Position Management UI (2-3 hours)

**Task 3.1**: Implement "Take Position" Flow
- Add click handler for "Take" buttons
- Show position size input modal
- Validate input (min/max size)
- Send DRIFT_OPEN_POSITION command
- Show loading state
- Handle success/error responses

**Task 3.2**: Implement "Leave Position" Flow
- Add "Leave" button to positions table
- Show confirmation modal
- Send DRIFT_CLOSE_POSITION command
- Show loading state
- Handle success/error responses

**Task 3.3**: Implement Position Updates
- Add `handleDriftUpdate(data)` WebSocket handler
- Update positions table on FUNDING_UPDATE
- Update health gauge
- Update leverage meter
- Update delta display

**Task 3.4**: Add Position Action Buttons
- Add "Close" button to each position row
- Add "Settle PnL" button (if unsettled > $1)
- Disable buttons during operations
- Show loading spinners

### Phase 4: WebSocket Integration (1-2 hours)

**Task 4.1**: Add FUNDING_UPDATE Handler
- Parse incoming FUNDING_UPDATE messages
- Update all UI components
- Handle missing fields gracefully
- Log updates to console (debug mode)

**Task 4.2**: Add COMMAND_RESULT Handler
- Show success/error toasts
- Update UI state on success
- Show error details on failure
- Re-enable action buttons

**Task 4.3**: Add HEALTH_ALERT Handler
- Show warning banner for health < 50%
- Show critical alert for health < 20%
- Add dismiss button
- Auto-dismiss after 10 seconds

### Phase 5: Testing & Polish (2-3 hours)

**Task 5.1**: Unit Tests
- Test delta drift calculation
- Test health ratio calculation
- Test profitability checks
- Test validation logic

**Task 5.2**: Property Tests
- Implement top 5 critical properties
- Run with 100 iterations each
- Fix any discovered bugs

**Task 5.3**: Integration Tests
- Test full position lifecycle
- Test error handling
- Test WebSocket reconnection
- Test UI state updates

**Task 5.4**: UI Polish
- Add loading skeletons
- Add error states
- Add empty states
- Improve mobile responsiveness
- Add keyboard shortcuts

### Total Estimated Time: 10-15 hours

---

## Security Considerations

### Private Key Management
- Private keys stored in environment variables only
- Never logged or transmitted via WebSocket
- Never included in error messages
- Loaded only at engine startup

### Transaction Simulation
- All transactions simulated before submission
- Simulation failures reject the transaction
- No retry on simulation failure
- Full simulation results logged

### User Confirmation
- Trades > $100 USD require explicit confirmation
- Confirmation modal shows full trade details
- Timeout after 30 seconds (auto-cancel)
- Confirmation required even in paper mode (for consistency)

### Rate Limiting
- API endpoint: 10 requests per minute per IP
- WebSocket commands: 5 commands per second per connection
- Auto-rebalance: Maximum 1 per 30 minutes
- Position operations: Maximum 10 per minute

### Input Validation
- All numeric inputs validated for range
- Market names validated against whitelist
- Amounts validated against balance
- Leverage validated against limits

---

## Performance Requirements

### Latency Targets
- API response time: < 500ms (p95)
- WebSocket broadcast: < 100ms (p95)
- Health calculation: < 50ms
- Delta drift calculation: < 50ms
- Position update broadcast: < 1 second

### Throughput
- Support 100 concurrent WebSocket connections
- Handle 1000 API requests per minute
- Process 10 position updates per second
- Maintain < 1% CPU usage when idle

### Resource Limits
- Memory: < 500MB per engine instance
- Database: < 100MB for vault state
- Logs: < 1GB per day (with rotation)
- Network: < 10MB/hour data transfer

---

## Deployment Considerations

### Environment Variables
```bash
# Required
SOLANA_PRIVATE_KEY=<base58_encoded_keypair>
RPC_URL=<solana_rpc_endpoint>

# Optional
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
DRIFT_SUB_ACCOUNT=0  # Sub-account index
MAX_LEVERAGE=5.0  # Maximum leverage multiplier
DRIFT_TOLERANCE_PCT=1.0  # Delta drift tolerance
REBALANCE_COOLDOWN_SEC=1800  # 30 minutes
MIN_TRADE_SIZE_SOL=0.005  # Minimum trade size
RESERVED_SOL=0.017  # Reserved for gas
```

### Health Checks
- HTTP endpoint: `GET /health`
- Returns: `{"status": "healthy", "engines": {...}}`
- Check engine status
- Check WebSocket connection
- Check RPC connectivity
- Check Drift connection (live mode)

### Monitoring
- Log all trades to file
- Track success/failure rates
- Monitor health ratio trends
- Alert on critical errors
- Dashboard for system metrics

### Backup & Recovery
- Vault state backed up every hour
- Transaction history retained for 90 days
- Configuration backed up on change
- Manual vault reset procedure documented

---

## Future Enhancements

### Phase 2 Features (Post-MVP)
1. **Multi-Market Support**: Trade multiple perp markets simultaneously
2. **Advanced Rebalancing**: ML-based optimal rebalance timing
3. **Portfolio View**: Aggregate view across all positions
4. **Historical Analytics**: PnL charts, funding rate history
5. **Mobile App**: Native iOS/Android apps
6. **Telegram Bot**: Position alerts and commands via Telegram
7. **Risk Scoring**: Real-time risk assessment and recommendations
8. **Backtesting**: Historical simulation of strategies

### Technical Debt
1. **Rust Acceleration**: Move delta/health calculations to PyO3
2. **Database Migration**: Move from JSON files to PostgreSQL
3. **gRPC API**: Replace HTTP API with gRPC for better performance
4. **Kubernetes**: Deploy as microservices on K8s
5. **Observability**: Add OpenTelemetry tracing
6. **Circuit Breakers**: Add circuit breakers for external dependencies

---

## Appendix

### Glossary
- **Delta Neutral**: A position where spot and perp exposures offset each other
- **Funding Rate**: Periodic payment between long and short position holders
- **Health Ratio**: Metric indicating liquidation risk (100% = safe, 0% = liquidated)
- **Drift Protocol**: Solana-based perpetual futures DEX
- **Sub-Account**: Isolated trading account within Drift Protocol
- **Jito**: MEV protection service for Solana transactions
- **Engine Vault**: Isolated capital allocation for a specific trading engine

### References
- [Drift Protocol Documentation](https://docs.drift.trade/)
- [driftpy SDK](https://github.com/drift-labs/driftpy)
- [Solana Documentation](https://docs.solana.com/)
- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)

---

**Document Version**: 1.0  
**Created**: 2026-01-16  
**Status**: Complete - Ready for Implementation
