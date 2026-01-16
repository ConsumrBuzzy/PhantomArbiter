# Design Document: Delta Neutral Engine Live Mode Integration

## Overview

This design document specifies the architecture and implementation approach for enabling full live trading capabilities in the Delta Neutral Engine (Funding Engine). The system maintains market-neutral positions on Drift Protocol by holding spot SOL and shorting SOL-PERP futures, earning funding rates while minimizing directional risk.

### Design Philosophy

The implementation follows a **phased rollout approach** that prioritizes safety and incremental validation:

1. **Phase 1**: Paper mode enhancement with realistic simulation
2. **Phase 2**: Live mode read-only monitoring (no trades)
3. **Phase 3**: Live mode capital management (deposits/withdrawals)
4. **Phase 4**: Live mode trading (open/close positions)

This phased approach allows validation at each step before progressing to higher-risk operations.

### Key Design Principles

- **Safety First**: All trades simulated before execution, explicit confirmations for large trades
- **Separation of Concerns**: Clear boundaries between paper/live adapters, UI/backend, monitoring/execution
- **Observability**: Comprehensive logging with Loguru, real-time WebSocket updates
- **Fault Tolerance**: Retry logic with exponential backoff, graceful degradation
- **Type Safety**: Full PEP 484 type hints on all public interfaces

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Drift Engine Dashboard (engine-drift.html)              │  │
│  │  - Health Gauge (SVG)                                     │  │
│  │  - Position Table                                         │  │
│  │  - Control Buttons (Deposit/Withdraw/Open/Close)         │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└────────────────────────┼────────────────────────────────────────┘
                         │ WebSocket (JSON)
                         │
┌────────────────────────▼────────────────────────────────────────┐
│              LocalDashboardServer (run_dashboard.py)            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  WebSocket Handler                                        │  │
│  │  - Command Router (START/STOP/DEPOSIT/WITHDRAW/etc)      │  │
│  │  - Broadcast Loop (SYSTEM_STATS every 1s)                │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└────────────────────────┼────────────────────────────────────────┘
                         │ Method Calls
                         │
┌────────────────────────▼────────────────────────────────────────┐
│           FundingEngine (src/engines/funding/logic.py)          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Mode: Paper | Live                                       │  │
│  │  - tick() - Single execution step                        │  │
│  │  - check_and_rebalance() - Delta drift logic             │  │
│  │  - execute_funding_command() - UI command handler        │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└────────────────────────┼────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼ (Paper Mode)                  ▼ (Live Mode)
┌──────────────────────┐        ┌──────────────────────┐
│   VirtualDriver      │        │   DriftAdapter       │
│  - Simulated trades  │        │  - Real driftpy SDK  │
│  - Mock balances     │        │  - Mainnet RPC       │
│  - Price feed        │        │  - Transaction build │
└──────────────────────┘        └──────────────────────┘
```

### Component Hierarchy

The system follows a layered architecture:

**Layer 1: Presentation (Frontend)**
- `frontend/templates/engine-drift.html` - Dashboard UI
- `frontend/js/components/drift-controller.js` - UI controller

**Layer 2: Communication (WebSocket)**
- `run_dashboard.py::LocalDashboardServer` - WebSocket server
- Command protocol: `{type: "COMMAND", action: "DRIFT_DEPOSIT", data: {...}}`
- Broadcast protocol: `{type: "SYSTEM_STATS", data: {drift_state: {...}}}`

**Layer 3: Business Logic (Engine)**
- `src/engines/funding/logic.py::FundingEngine` - Core engine
- Inherits from `BaseEngine` for lifecycle management
- Implements `tick()` for periodic execution
- Implements `execute_funding_command()` for UI commands

**Layer 4: Execution Adapters**
- **Paper Mode**: `VirtualDriver` - Simulates trades with mock state
- **Live Mode**: `DriftAdapter` - Wraps driftpy SDK for real execution

**Layer 5: Infrastructure**
- `src/drift_engine/core/builder.py::DriftOrderBuilder` - Drift instruction builder
- `src/drivers/wallet_manager.py::WalletManager` - Keypair management
- `src/shared/infrastructure/jito_adapter.py::JitoAdapter` - MEV protection

---

## Components and Interfaces

### 1. FundingEngine

**Responsibility**: Core business logic for delta-neutral trading

**Interface**:
```python
class FundingEngine(BaseEngine):
    def __init__(self, live_mode: bool = False, config: Optional[RebalanceConfig] = None)
    
    async def tick(self) -> None
        """Single execution step - checks delta and rebalances if needed"""
    
    async def check_and_rebalance(self, simulate: bool = True) -> dict
        """Check delta drift and execute corrective trade if needed"""
    
    async def execute_funding_command(self, action: str, data: dict) -> dict
        """Execute UI commands: DEPOSIT, WITHDRAW, OPEN_POSITION, CLOSE_POSITION"""
    
    def get_interval(self) -> float
        """Return polling interval in seconds"""
```

**State**:
- `live_mode: bool` - Paper vs Live mode flag
- `config: RebalanceConfig` - Configuration parameters
- `last_rebalance: Optional[datetime]` - Cooldown tracking
- `driver: Optional[VirtualDriver]` - Paper mode adapter
- `drift_adapter: Optional[DriftAdapter]` - Live mode adapter

**Dependencies**:
- `BaseEngine` - Lifecycle management
- `VirtualDriver` (paper mode) - Simulated execution
- `DriftAdapter` (live mode) - Real execution
- `DriftOrderBuilder` - Drift instruction construction

### 2. DriftAdapter

**Responsibility**: Wrapper for driftpy SDK with PhantomArbiter conventions

**Interface**:
```python
class DriftAdapter:
    def __init__(self, network: str = "mainnet")
    
    async def connect(self, wallet: WalletManager, sub_account: int = 0) -> bool
        """Initialize connection to Drift Protocol"""
    
    async def get_account_state(self) -> dict
        """Fetch current sub-account state (collateral, positions, margin)"""
    
    async def deposit(self, amount_sol: float) -> str
        """Deposit SOL collateral to sub-account, returns tx signature"""
    
    async def withdraw(self, amount_sol: float) -> str
        """Withdraw SOL collateral from sub-account, returns tx signature"""
    
    async def open_position(self, market: str, direction: str, size: float) -> str
        """Open perp position, returns tx signature"""
    
    async def close_position(self, market: str) -> str
        """Close perp position, returns tx signature"""
    
    async def calculate_health_ratio(self) -> float
        """Calculate health ratio: (total_collateral - maint_margin) / total_collateral * 100"""
```

**State**:
- `network: str` - "mainnet" or "devnet"
- `wallet: Optional[WalletManager]` - Wallet instance
- `sub_account: int` - Active sub-account number
- `drift_client: Optional[DriftClient]` - driftpy client instance
- `user_account: Optional[Pubkey]` - Derived user PDA

### 3. VirtualDriver (Enhanced)

**Responsibility**: Realistic paper trading simulation

**Interface**:
```python
class VirtualDriver:
    def __init__(self, initial_balances: dict[str, float])
    
    async def place_order(self, order: VirtualOrder) -> dict
        """Execute simulated trade with slippage"""
    
    def get_balances(self) -> dict[str, float]
        """Return current balances"""
    
    def set_balance(self, asset: str, amount: float) -> None
        """Set balance for asset"""
    
    def set_price_feed(self, prices: dict[str, float]) -> None
        """Update price feed"""
    
    def apply_funding_rate(self, market: str, rate_8h: float) -> None
        """Apply funding payment to position"""
    
    def calculate_health_ratio(self) -> float
        """Calculate simulated health ratio"""
```

**Enhancements for Phase 1**:
- Track settled vs unsettled PnL separately
- Apply funding rates every 8 hours (simulated)
- Realistic slippage (0.1-0.3% based on size)
- Leverage limits (reject > 10x)
- Maintenance margin calculation (5% for SOL-PERP)

### 4. WebSocket Command Protocol

**Command Format**:
```json
{
  "type": "COMMAND",
  "action": "DRIFT_DEPOSIT",
  "data": {
    "amount": 1.5
  }
}
```

**Supported Actions**:
- `START_ENGINE` - Start engine with mode parameter
- `STOP_ENGINE` - Stop engine gracefully
- `DRIFT_DEPOSIT` - Deposit collateral
- `DRIFT_WITHDRAW` - Withdraw collateral
- `DRIFT_OPEN_POSITION` - Open position
- `DRIFT_CLOSE_POSITION` - Close position

**Response Format**:
```json
{
  "type": "COMMAND_RESULT",
  "action": "DRIFT_DEPOSIT",
  "success": true,
  "message": "Deposited 1.5 SOL",
  "data": {
    "tx_signature": "5Kq..."
  }
}
```

**Broadcast Format** (SYSTEM_STATS):
```json
{
  "type": "SYSTEM_STATS",
  "data": {
    "drift_state": {
      "health": 85.3,
      "leverage": 2.1,
      "total_collateral": 150.0,
      "free_collateral": 120.0,
      "maintenance_margin": 30.0,
      "positions": [
        {
          "market": "SOL-PERP",
          "amount": -10.5,
          "entry_price": 145.0,
          "mark_price": 147.0,
          "pnl": -21.0,
          "liq_price": 180.0
        }
      ],
      "net_delta": 0.05,
      "drift_pct": 0.47
    }
  }
}
```

---

## Data Models

### RebalanceConfig

Configuration for auto-rebalancer behavior.

```python
@dataclass
class RebalanceConfig:
    drift_tolerance_pct: float = 1.0          # Delta tolerance (1% = 0.01)
    cooldown_seconds: int = 1800              # 30 minutes between rebalances
    max_slippage_bps: int = 50                # 0.5% max slippage
    min_trade_size: float = 0.005             # Minimum trade size (SOL)
    reserved_sol: float = 0.017               # Reserved for gas
    loop_interval_seconds: int = 60           # Polling interval
```

### DriftAccountState

State snapshot from Drift Protocol.

```python
@dataclass
class DriftAccountState:
    sub_account: int
    total_collateral: float                   # USD value
    free_collateral: float                    # USD value
    maintenance_margin: float                 # USD value
    initial_margin: float                     # USD value
    unrealized_pnl: float                     # USD value
    settled_pnl: float                        # USD value
    leverage: float                           # Effective leverage
    health_ratio: float                       # 0-100 scale
    positions: list[DriftPosition]
```

### DriftPosition

Individual perp position.

```python
@dataclass
class DriftPosition:
    market: str                               # e.g. "SOL-PERP"
    market_index: int                         # Drift market index
    amount: float                             # Signed: positive = long, negative = short
    entry_price: float                        # Average entry price
    mark_price: float                         # Current mark price
    unrealized_pnl: float                     # USD value
    liquidation_price: float                  # Liquidation price
```

### VirtualOrder

Order for paper trading.

```python
@dataclass
class VirtualOrder:
    symbol: str                               # e.g. "SOL-PERP"
    side: str                                 # "buy" or "sell"
    size: float                               # Quantity
    order_type: str                           # "market" or "limit"
    price: Optional[float] = None             # Limit price (if applicable)
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Delta Drift Calculation Accuracy

*For any* spot SOL amount and perp position size, the calculated delta drift percentage should equal `(spot_sol + perp_sol) / max(spot_sol - reserved_sol, 0.001) * 100` where perp_sol is negative for shorts.

**Validates: Requirements 1.1, 5.1**

**Rationale**: Delta drift is the core metric for determining when rebalancing is needed. Incorrect calculation leads to unnecessary trades or missed rebalancing opportunities.

### Property 2: Health Ratio Bounds

*For any* total collateral and maintenance margin values, the calculated health ratio should be in the range [0, 100], where 0 indicates liquidation and 100 indicates maximum safety.

**Validates: Requirements 1.4, 2.3**

**Rationale**: Health ratio is the primary risk metric. Values outside [0, 100] indicate calculation errors that could lead to incorrect risk assessment.

### Property 3: Funding Rate Application

*For any* position with non-zero size, applying a funding rate should update the position's PnL by `position_size * mark_price * funding_rate_8h`, and this operation should be idempotent within the same 8-hour period.

**Validates: Requirements 1.3**

**Rationale**: Funding payments are the revenue source for this strategy. Incorrect application leads to inaccurate PnL tracking and profitability assessment.

### Property 4: Leverage Limit Enforcement

*For any* proposed position size and current collateral, if the resulting leverage would exceed the configured maximum (default 5x for live, 10x for paper), the system should reject the trade.

**Validates: Requirements 1.6, 6.7**

**Rationale**: Excessive leverage increases liquidation risk. This property ensures the safety gate prevents dangerous positions.

### Property 5: Cooldown Period Enforcement

*For any* rebalance attempt, if the time since the last successful rebalance is less than the configured cooldown period (default 30 minutes), the system should skip the rebalance and log the remaining cooldown time.

**Validates: Requirements 5.3, 5.4**

**Rationale**: Cooldown prevents excessive trading costs from frequent small adjustments. Violating cooldown leads to unprofitable over-trading.

### Property 6: Minimum Trade Size Filter

*For any* calculated correction size, if the absolute value is below the minimum trade size (default 0.005 SOL), the system should skip the rebalance.

**Validates: Requirements 5.6**

**Rationale**: Dust trades have costs that exceed their benefit. This property ensures economic efficiency.

### Property 7: Withdrawal Safety Check

*For any* withdrawal amount, if executing the withdrawal would cause the health ratio to drop below 80%, the system should reject the withdrawal.

**Validates: Requirements 3.8**

**Rationale**: Withdrawals that leave insufficient collateral create liquidation risk. This property protects against user error.

### Property 8: Position Direction Correctness

*For any* net delta value, if net delta is positive (net long), the correction action should be EXPAND_SHORT, and if net delta is negative (net short), the correction action should be REDUCE_SHORT.

**Validates: Requirements 5.7, 5.8**

**Rationale**: Incorrect direction mapping causes the system to amplify drift instead of correcting it, leading to increased risk.

### Property 9: Slippage Application in Paper Mode

*For any* paper mode trade with size S and price P, the executed price should be within the range [P * (1 - slippage), P * (1 + slippage)] where slippage is 0.1-0.3% based on size.

**Validates: Requirements 1.5**

**Rationale**: Unrealistic paper trading leads to false confidence. Slippage simulation ensures paper results approximate live performance.

### Property 10: Account State Synchronization

*For any* live mode operation, after a successful deposit or withdrawal, the Engine_Vault balance should match the on-chain sub-account collateral within 10 seconds.

**Validates: Requirements 7.2**

**Rationale**: Desynchronized state leads to incorrect risk calculations and potential over-allocation of capital.

### Property 11: WebSocket Response Timeliness

*For any* command received via WebSocket, the system should send a response (success or error) within 5 seconds.

**Validates: Requirements 8.8**

**Rationale**: Slow responses create poor UX and make it difficult to diagnose issues. Timeouts indicate system health problems.

### Property 12: Error Recovery Idempotence

*For any* failed transaction, retrying the same operation with the same parameters should either succeed or fail with the same error, never producing duplicate state changes.

**Validates: Requirements 9.1, 9.3**

**Rationale**: Non-idempotent retries can cause double-execution (e.g., depositing twice), leading to capital misallocation.

### Property 13: Profitability Gate

*For any* proposed trade, if the estimated costs (gas + Jito tip + slippage + fees) exceed the expected revenue from funding rates (using conservative 50% of current rate), the system should reject the trade.

**Validates: Requirements 6.2, 6.3, 6.4**

**Rationale**: Unprofitable trades erode capital. This property ensures economic viability of all executed trades.

### Property 14: Transaction Simulation Requirement

*For all* live mode transactions, the system must successfully simulate the transaction before submission, and if simulation fails, the transaction must not be submitted.

**Validates: Requirements 9.2**

**Rationale**: Failed transactions waste gas and indicate logic errors. Simulation catches issues before they cost money.

### Property 15: Position Closure Completeness

*For any* close position command, the resulting position size should be zero (within 0.0001 SOL tolerance for rounding).

**Validates: Requirements 4.8, 4.9**

**Rationale**: Incomplete closures leave residual exposure and complicate accounting. Full closure ensures clean state.

---

## Error Handling

### Error Categories

**1. Transient Errors** (Retry with exponential backoff)
- RPC connection failures
- Network timeouts
- Temporary Drift Protocol unavailability
- Jito Block Engine congestion

**Strategy**: Retry up to 3 times with delays: 1s, 2s, 4s

**2. Validation Errors** (Reject immediately, no retry)
- Invalid market names
- Insufficient funds
- Leverage limit violations
- Health ratio violations
- Cooldown period active

**Strategy**: Return error to user, log with WARNING level

**3. Critical Errors** (Stop engine, alert user)
- Wallet keypair missing
- Invalid sub-account
- Drift account not initialized
- Persistent RPC failures (> 3 retries)

**Strategy**: Stop engine, broadcast error via WebSocket, log with ERROR level

**4. Unknown State Errors** (Manual intervention required)
- Transaction submitted but confirmation timeout
- Conflicting on-chain vs local state
- Unexpected account structure

**Strategy**: Mark operation as "unknown", alert user, require manual verification

### Error Handling Patterns

#### Pattern 1: RPC Call with Retry

```python
async def _rpc_call_with_retry(self, operation: Callable, max_retries: int = 3) -> Any:
    """Execute RPC call with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return await operation()
        except (ConnectionError, TimeoutError) as e:
            if attempt == max_retries - 1:
                raise
            delay = 2 ** attempt  # 1s, 2s, 4s
            Logger.warning(f"RPC call failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
            await asyncio.sleep(delay)
```

#### Pattern 2: Transaction with Simulation

```python
async def _execute_with_simulation(self, tx: VersionedTransaction) -> str:
    """Simulate transaction before submission."""
    # Simulate first
    sim_resp = await self.client.simulate_transaction(tx)
    if sim_resp.value.err:
        raise ValidationError(f"Simulation failed: {sim_resp.value.err}")
    
    # Execute
    resp = await self.client.send_transaction(tx, opts=TxOpts(skip_confirmation=False))
    
    # Wait for confirmation with timeout
    try:
        await asyncio.wait_for(
            self.client.confirm_transaction(resp.value, commitment=Confirmed),
            timeout=30.0
        )
        return str(resp.value)
    except asyncio.TimeoutError:
        # Query transaction status
        status = await self._query_transaction_status(resp.value)
        if status == "confirmed":
            return str(resp.value)
        elif status == "failed":
            raise TransactionError("Transaction failed on-chain")
        else:
            raise UnknownStateError(f"Transaction status unknown: {resp.value}")
```

#### Pattern 3: Graceful Degradation

```python
async def tick(self):
    """Single execution step with graceful degradation."""
    try:
        result = await self.check_and_rebalance(simulate=not self.live_mode)
        
        if self._callback:
            await self._callback({"type": "STATUS", "data": result})
            
    except ValidationError as e:
        # Expected errors - log and continue
        Logger.warning(f"Validation error: {e}")
        if self._callback:
            await self._callback({"type": "ERROR", "level": "warning", "message": str(e)})
            
    except CriticalError as e:
        # Critical errors - stop engine
        Logger.error(f"Critical error: {e}")
        self.stop()
        if self._callback:
            await self._callback({"type": "ERROR", "level": "critical", "message": str(e)})
            
    except Exception as e:
        # Unexpected errors - log and continue (but alert)
        Logger.error(f"Unexpected error in tick: {e}", exc_info=True)
        if self._callback:
            await self._callback({"type": "ERROR", "level": "error", "message": f"Unexpected: {e}"})
```

### Recovery Procedures

**Drift Connection Loss**:
1. Detect: RPC calls fail with connection errors
2. Action: Attempt reconnection every 10 seconds
3. On success: Re-sync account state before resuming operations
4. Broadcast: Connection status updates to UI

**Transaction Confirmation Timeout**:
1. Detect: `confirm_transaction()` times out after 30 seconds
2. Action: Query transaction status for 60 seconds
3. If confirmed: Proceed normally
4. If failed: Log error, update state
5. If unknown: Mark as "unknown", alert user, disable trading

**State Desynchronization**:
1. Detect: Engine_Vault balance != on-chain collateral
2. Action: Retry sync up to 3 times with exponential backoff
3. If sync fails: Stop engine, alert user
4. Broadcast: Sync status to UI

---

## Testing Strategy

### Dual Testing Approach

This system requires both **unit tests** and **property-based tests** for comprehensive coverage:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs

Both are complementary and necessary. Unit tests catch concrete bugs in specific scenarios, while property tests verify general correctness across the input space.

### Property-Based Testing Configuration

**Library**: `hypothesis` (Python)

**Configuration**:
- Minimum 100 iterations per property test
- Each test tagged with: `# Feature: delta-neutral-live-mode, Property N: [property text]`
- Generators constrained to realistic input ranges

**Example Property Test**:
```python
from hypothesis import given, strategies as st

# Feature: delta-neutral-live-mode, Property 1: Delta Drift Calculation Accuracy
@given(
    spot_sol=st.floats(min_value=0.0, max_value=1000.0),
    perp_sol=st.floats(min_value=-1000.0, max_value=0.0),  # Shorts are negative
    reserved_sol=st.floats(min_value=0.01, max_value=0.1)
)
def test_delta_drift_calculation(spot_sol, perp_sol, reserved_sol):
    """Property 1: Delta drift calculation accuracy."""
    hedgeable = max(spot_sol - reserved_sol, 0.001)
    net_delta = spot_sol + perp_sol
    expected_drift = (net_delta / hedgeable) * 100
    
    # Call system under test
    actual_drift = calculate_delta_drift(spot_sol, perp_sol, reserved_sol)
    
    assert abs(actual_drift - expected_drift) < 0.01  # Within 0.01%
```

### Unit Testing Strategy

**Test Organization**:
- `tests/engines/funding/test_logic.py` - FundingEngine tests
- `tests/engines/funding/test_drift_adapter.py` - DriftAdapter tests
- `tests/engines/funding/test_virtual_driver.py` - VirtualDriver tests
- `tests/engines/funding/test_properties.py` - Property-based tests

**Coverage Targets**:
- Core logic: 90%+ coverage
- Error handling: 80%+ coverage
- UI command handlers: 85%+ coverage

**Key Test Scenarios**:

1. **Paper Mode Simulation**
   - Open position → Apply funding → Check PnL
   - Deposit → Check balance update
   - Withdraw → Check balance update
   - Close position → Verify zero position

2. **Delta Drift Detection**
   - Within tolerance → No rebalance
   - Exceeds tolerance → Rebalance triggered
   - Cooldown active → Rebalance skipped
   - Below min size → Rebalance skipped

3. **Safety Gates**
   - Leverage limit → Trade rejected
   - Health ratio violation → Trade rejected
   - Insufficient funds → Trade rejected
   - Unprofitable trade → Trade rejected

4. **Error Handling**
   - RPC failure → Retry with backoff
   - Simulation failure → No submission
   - Confirmation timeout → Status query
   - Unknown state → Alert user

5. **WebSocket Protocol**
   - Valid command → Success response
   - Invalid command → Error response
   - Response within 5s → Pass
   - Broadcast format → Valid JSON

### Integration Testing

**End-to-End Flows**:

1. **Paper Mode Full Cycle**
   - Start engine (paper mode)
   - Open position
   - Monitor health (5 ticks)
   - Trigger rebalance
   - Close position
   - Stop engine

2. **Live Mode Read-Only**
   - Start engine (live mode, read-only)
   - Fetch account state
   - Calculate health ratio
   - Broadcast to UI
   - Stop engine

3. **Live Mode Capital Management**
   - Start engine (live mode)
   - Deposit 1 SOL
   - Verify vault sync
   - Withdraw 0.5 SOL
   - Verify vault sync
   - Stop engine

4. **Live Mode Trading** (Devnet only)
   - Start engine (live mode, devnet)
   - Open small position (0.01 SOL)
   - Wait for confirmation
   - Close position
   - Verify zero position
   - Stop engine

### Manual Testing Checklist

**Phase 1: Paper Mode**
- [ ] Start engine in paper mode
- [ ] Verify initial balances displayed in UI
- [ ] Open position via UI
- [ ] Verify position appears in table
- [ ] Trigger manual rebalance
- [ ] Verify rebalance executes
- [ ] Close position via UI
- [ ] Verify position removed from table

**Phase 2: Live Read-Only**
- [ ] Start engine in live mode (read-only)
- [ ] Verify real account data displayed
- [ ] Verify health gauge updates
- [ ] Verify position table shows real positions
- [ ] Verify metrics update every 10s

**Phase 3: Live Capital Management**
- [ ] Deposit 0.1 SOL via UI
- [ ] Verify transaction signature returned
- [ ] Verify balance updated in UI
- [ ] Withdraw 0.05 SOL via UI
- [ ] Verify transaction signature returned
- [ ] Verify balance updated in UI

**Phase 4: Live Trading**
- [ ] Open 0.01 SOL position via UI
- [ ] Verify transaction signature returned
- [ ] Verify position appears in table
- [ ] Wait 5 minutes
- [ ] Verify funding accrual
- [ ] Close position via UI
- [ ] Verify position removed
- [ ] Verify PnL settled

---

## Implementation Notes

### Phase 1: Paper Mode Enhancement

**Goal**: Realistic simulation that approximates live performance

**Changes**:
1. Enhance `VirtualDriver` with:
   - Settled vs unsettled PnL tracking
   - Funding rate application (every 8 hours simulated)
   - Realistic slippage (0.1-0.3% based on size)
   - Leverage limits (10x for paper)
   - Maintenance margin calculation

2. Update `FundingEngine.check_and_rebalance()`:
   - Use `VirtualDriver` methods for paper mode
   - Return enriched data for UI (health, leverage, positions)

3. Test with paper mode cycles:
   - Run 10 funding cycles
   - Verify PnL accumulation
   - Verify rebalancing triggers correctly

### Phase 2: Live Read-Only Monitoring

**Goal**: Fetch and display real Drift account data without trading

**Changes**:
1. Implement `DriftAdapter.connect()`:
   - Initialize driftpy client
   - Derive user PDA
   - Verify account exists

2. Implement `DriftAdapter.get_account_state()`:
   - Fetch account data via RPC
   - Parse positions from account bytes
   - Calculate health ratio
   - Return `DriftAccountState`

3. Update `FundingEngine.check_and_rebalance()`:
   - Use `DriftAdapter` for live mode
   - Return same enriched data format as paper mode

4. Test with real mainnet account:
   - Verify data matches Drift UI
   - Verify health calculation accuracy
   - Verify position parsing correctness

### Phase 3: Live Capital Management

**Goal**: Enable deposits and withdrawals with safety checks

**Changes**:
1. Implement `DriftAdapter.deposit()`:
   - Build deposit instruction
   - Simulate transaction
   - Submit and confirm
   - Return tx signature

2. Implement `DriftAdapter.withdraw()`:
   - Check health ratio impact
   - Build withdraw instruction
   - Simulate transaction
   - Submit and confirm
   - Return tx signature

3. Implement vault synchronization:
   - After deposit/withdraw, update `Engine_Vault`
   - Verify on-chain balance matches vault
   - Retry sync if mismatch

4. Test with small amounts:
   - Deposit 0.1 SOL
   - Verify confirmation
   - Withdraw 0.05 SOL
   - Verify confirmation
   - Check vault sync

### Phase 4: Live Trading

**Goal**: Enable position opening/closing with full safety gates

**Changes**:
1. Implement `DriftAdapter.open_position()`:
   - Build market order instruction
   - Add price limit (slippage tolerance)
   - Simulate transaction
   - Submit via Jito (with fallback to RPC)
   - Confirm and return tx signature

2. Implement `DriftAdapter.close_position()`:
   - Calculate offsetting size
   - Build closing order
   - Simulate transaction
   - Submit and confirm
   - Settle PnL if needed

3. Implement safety gates:
   - Leverage check
   - Health ratio check
   - Profitability check
   - Network latency check
   - Gas reserve check

4. Test with small positions:
   - Open 0.01 SOL short
   - Verify position on-chain
   - Wait for funding accrual
   - Close position
   - Verify zero position
   - Verify PnL settled

### Deployment Considerations

**Environment Variables**:
```bash
# Required
SOLANA_PRIVATE_KEY=<base58_keypair>
RPC_URL=<mainnet_rpc_endpoint>

# Optional
DRIFT_SUB_ACCOUNT=0
JITO_REGION=ny
MAX_LEVERAGE=5.0
DRIFT_TOLERANCE_PCT=1.0
COOLDOWN_SECONDS=1800
```

**Monitoring**:
- Log all trades to `logs/funding_engine.log`
- Rotate daily with 30-day retention
- Alert on critical errors via WebSocket
- Track metrics: trades/hour, PnL, health ratio

**Safety Checklist**:
- [ ] Private key stored in `.env` (not committed)
- [ ] Simulation enabled for all live transactions
- [ ] Leverage limits configured
- [ ] Health ratio thresholds set
- [ ] Profitability gates active
- [ ] Cooldown period enforced
- [ ] Gas reserves maintained

---

**Document Version**: 1.0  
**Created**: 2026-01-15  
**Status**: Draft - Awaiting Review
