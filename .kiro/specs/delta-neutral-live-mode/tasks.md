# Implementation Plan: Delta Neutral Engine Live Mode Integration

## Overview

This implementation plan breaks down the Delta Neutral Engine live mode integration into discrete, testable tasks following a phased rollout approach. Each phase builds on the previous one, allowing incremental validation before progressing to higher-risk operations.

The implementation follows these phases:
1. **Phase 1**: Paper mode enhancement (realistic simulation)
2. **Phase 2**: Live mode read-only monitoring
3. **Phase 3**: Live mode capital management
4. **Phase 4**: Live mode trading

---

## Tasks

### Phase 1: Paper Mode Enhancement

- [x] 1. Enhance VirtualDriver for realistic simulation
  - Implement settled vs unsettled PnL tracking
  - Add funding rate application method (8-hour cycles)
  - Implement realistic slippage calculation (0.1-0.3% based on size)
  - Add leverage limit enforcement (reject > 10x)
  - Implement maintenance margin calculation (5% for SOL-PERP)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 1.1 Write property test for slippage application
  - **Property 9: Slippage Application in Paper Mode**
  - **Validates: Requirements 1.5**

- [x] 1.2 Write property test for leverage limit enforcement
  - **Property 4: Leverage Limit Enforcement**
  - **Validates: Requirements 1.6**

- [x] 2. Update FundingEngine for enriched paper mode data
  - Modify `check_and_rebalance()` to return UI-ready metrics
  - Add health ratio calculation for paper mode
  - Add leverage calculation for paper mode
  - Add position list formatting for UI
  - Ensure WebSocket broadcast includes all required fields
  - _Requirements: 1.7_

- [x] 2.1 Write property test for health ratio bounds
  - **Property 2: Health Ratio Bounds**
  - **Validates: Requirements 1.4, 2.3**

- [x] 2.2 Write unit tests for paper mode command execution
  - Test DEPOSIT command updates balance
  - Test WITHDRAW command updates balance
  - Test OPEN_POSITION command creates position
  - Test CLOSE_POSITION command removes position
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 3. Checkpoint - Paper mode validation
  - Run paper mode simulation with 10 funding cycles
  - Verify PnL accumulation is realistic
  - Verify rebalancing triggers at correct drift thresholds
  - Verify UI displays all metrics correctly
  - Ensure all tests pass, ask the user if questions arise.

---

### Phase 2: Live Mode Read-Only Monitoring

- [x] 4. Implement DriftAdapter connection logic
  - Create `DriftAdapter` class in `src/engines/funding/drift_adapter.py`
  - Implement `connect()` method with driftpy client initialization
  - Implement user PDA derivation
  - Add account existence verification
  - Add connection retry logic with exponential backoff
  - _Requirements: 2.1_

- [x] 4.1 Write unit tests for DriftAdapter connection
  - Test successful connection
  - Test connection retry on failure
  - Test account not found error
  - _Requirements: 2.1_

- [x] 5. Implement account state fetching
  - Implement `get_account_state()` method in DriftAdapter
  - Parse Drift account data bytes
  - Extract collateral, positions, and margin data
  - Implement position parsing from account structure
  - Calculate health ratio from maintenance margin and collateral
  - _Requirements: 2.2, 2.3, 2.6, 2.7_

- [x] 5.1 Write property test for health ratio calculation
  - **Property 2: Health Ratio Bounds**
  - **Validates: Requirements 2.3**

- [x] 6. Integrate live monitoring into FundingEngine
  - Update `check_and_rebalance()` to use DriftAdapter in live mode
  - Implement polling loop with configurable interval (default 10s)
  - Add health ratio warning emission (< 50%)
  - Add health ratio critical alert (< 20%)
  - Ensure WebSocket broadcast within 500ms of state change
  - _Requirements: 2.4, 2.5, 2.8, 2.9_

- [x] 6.1 Write property test for WebSocket response timeliness
  - **Property 11: WebSocket Response Timeliness**
  - **Validates: Requirements 2.9, 8.8**

- [x] 6.2 Write unit tests for live monitoring
  - Test account state fetch and parse
  - Test health warnings at correct thresholds
  - Test WebSocket broadcast format
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

- [x] 7. Checkpoint - Live read-only validation
  - Connect to real mainnet account
  - Verify data matches Drift UI
  - Verify health calculation accuracy
  - Verify position parsing correctness
  - Verify UI updates every 10 seconds
  - Ensure all tests pass, ask the user if questions arise.

---

### Phase 3: Live Mode Capital Management

- [-] 8. Implement deposit functionality
  - Implement `deposit()` method in DriftAdapter
  - Add amount validation (positive, less than wallet balance)
  - Build Drift deposit instruction using DriftOrderBuilder
  - Implement transaction simulation before submission
  - Add transaction confirmation with 30s timeout
  - Return transaction signature on success
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 8.1 Write property test for transaction simulation requirement
  - **Property 14: Transaction Simulation Requirement**
  - **Validates: Requirements 3.4, 9.2**

- [ ] 8.2 Write unit tests for deposit
  - Test successful deposit
  - Test validation rejection (negative amount)
  - Test validation rejection (insufficient balance)
  - Test simulation failure handling
  - Test confirmation timeout handling
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 9. Implement withdrawal functionality
  - Implement `withdraw()` method in DriftAdapter
  - Add health ratio impact validation
  - Reject withdrawal if health would drop below 80%
  - Build Drift withdraw instruction
  - Implement transaction simulation and confirmation
  - Return transaction signature on success
  - _Requirements: 3.7, 3.8, 3.9_

- [ ] 9.1 Write property test for withdrawal safety check
  - **Property 7: Withdrawal Safety Check**
  - **Validates: Requirements 3.8**

- [ ] 9.2 Write unit tests for withdrawal
  - Test successful withdrawal
  - Test rejection when health < 80%
  - Test simulation failure handling
  - _Requirements: 3.7, 3.8, 3.9_

- [ ] 10. Implement Engine_Vault synchronization
  - Update Engine_Vault balance after deposit/withdraw
  - Implement vault sync verification (on-chain vs local)
  - Add retry logic for sync failures (3 retries, exponential backoff)
  - Emit error event if sync fails after retries
  - Disable trading if vault desynchronized
  - _Requirements: 7.1, 7.2, 7.7, 7.8_

- [ ] 10.1 Write property test for account state synchronization
  - **Property 10: Account State Synchronization**
  - **Validates: Requirements 7.2**

- [ ] 10.2 Write unit tests for vault synchronization
  - Test sync after deposit
  - Test sync after withdrawal
  - Test retry on sync failure
  - Test trading disabled on persistent sync failure
  - _Requirements: 7.1, 7.2, 7.7, 7.8_

- [ ] 11. Update execute_funding_command for live mode
  - Route DEPOSIT command to DriftAdapter.deposit()
  - Route WITHDRAW command to DriftAdapter.withdraw()
  - Add error handling and user-friendly error messages
  - Log all capital management operations with full details
  - _Requirements: 3.10, 8.4, 8.5, 8.9_

- [ ] 11.1 Write unit tests for command routing
  - Test DEPOSIT command execution
  - Test WITHDRAW command execution
  - Test error response format
  - _Requirements: 8.4, 8.5, 8.9_

- [ ] 12. Checkpoint - Capital management validation
  - Deposit 0.1 SOL via UI
  - Verify transaction signature returned
  - Verify balance updated in UI
  - Verify vault synchronized
  - Withdraw 0.05 SOL via UI
  - Verify transaction signature returned
  - Verify balance updated in UI
  - Ensure all tests pass, ask the user if questions arise.

---

### Phase 4: Live Mode Trading

- [ ] 13. Implement position opening
  - Implement `open_position()` method in DriftAdapter
  - Validate market exists on Drift Protocol
  - Check current leverage does not exceed maximum (5x)
  - Build market order instruction with DriftOrderBuilder
  - Add price limit based on mark price + slippage tolerance
  - Implement Jito bundle submission with fallback to RPC
  - Add retry logic for Jito failures (3 retries)
  - Update Engine_Vault position tracking on success
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [ ] 13.1 Write property test for leverage limit enforcement
  - **Property 4: Leverage Limit Enforcement**
  - **Validates: Requirements 4.2, 6.7**

- [ ] 13.2 Write unit tests for position opening
  - Test successful position open
  - Test leverage limit rejection
  - Test invalid market rejection
  - Test Jito submission with fallback
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [ ] 14. Implement position closing
  - Implement `close_position()` method in DriftAdapter
  - Calculate exact offsetting size to flatten position
  - Build offsetting order (buy to close short, sell to close long)
  - Implement PnL settlement if unsettled PnL > $1.00
  - Call settle_pnl instruction on Drift Protocol
  - Broadcast updated position list to UI within 1 second
  - _Requirements: 4.8, 4.9, 4.10, 4.11, 4.12_

- [ ] 14.1 Write property test for position closure completeness
  - **Property 15: Position Closure Completeness**
  - **Validates: Requirements 4.8, 4.9**

- [ ] 14.2 Write unit tests for position closing
  - Test successful position close
  - Test PnL settlement trigger
  - Test UI broadcast timing
  - _Requirements: 4.8, 4.9, 4.10, 4.11, 4.12_

- [ ] 15. Implement delta drift auto-rebalancing for live mode
  - Update `check_and_rebalance()` to execute real trades in live mode
  - Implement cooldown enforcement (30 minutes)
  - Implement minimum trade size filter (0.005 SOL)
  - Calculate correction trade size from net delta
  - Determine trade direction (EXPAND_SHORT vs REDUCE_SHORT)
  - Execute rebalance trade via DriftAdapter
  - Update last rebalance timestamp on success
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

- [ ] 15.1 Write property test for delta drift calculation
  - **Property 1: Delta Drift Calculation Accuracy**
  - **Validates: Requirements 5.1**

- [ ] 15.2 Write property test for cooldown enforcement
  - **Property 5: Cooldown Period Enforcement**
  - **Validates: Requirements 5.3, 5.4**

- [ ] 15.3 Write property test for minimum trade size filter
  - **Property 6: Minimum Trade Size Filter**
  - **Validates: Requirements 5.6**

- [ ] 15.4 Write property test for position direction correctness
  - **Property 8: Position Direction Correctness**
  - **Validates: Requirements 5.7, 5.8**

- [ ] 15.5 Write unit tests for auto-rebalancing
  - Test rebalance triggered at correct drift
  - Test cooldown prevents premature rebalance
  - Test minimum size filter
  - Test direction mapping (long → expand short, short → reduce short)
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

- [ ] 16. Implement safety gates
  - Create `SafetyGate` class in `src/engines/funding/safety_gates.py`
  - Implement cost estimation (gas + Jito tip + slippage + fees)
  - Implement revenue estimation (funding rates, conservative 50%)
  - Implement profitability check (revenue > costs)
  - Implement network latency check (< 500ms)
  - Implement gas reserve check (> 0.017 SOL)
  - Implement leverage check (< 5x)
  - Implement health ratio check (> 60% after trade)
  - Implement user confirmation for trades > $100 USD
  - Log rejection reason when gate blocks trade
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

- [ ] 16.1 Write property test for profitability gate
  - **Property 13: Profitability Gate**
  - **Validates: Requirements 6.2, 6.3, 6.4**

- [ ] 16.2 Write unit tests for safety gates
  - Test profitability rejection
  - Test latency rejection
  - Test gas reserve rejection
  - Test leverage rejection
  - Test health ratio rejection
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

- [ ] 17. Integrate safety gates into trading flow
  - Call SafetyGate before all live trades
  - Skip trade if gate blocks
  - Broadcast rejection reason to UI
  - Log rejection with WARNING level
  - _Requirements: 6.9_

- [ ] 18. Update execute_funding_command for trading commands
  - Route OPEN_POSITION command to DriftAdapter.open_position()
  - Route CLOSE_POSITION command to DriftAdapter.close_position()
  - Apply safety gates before execution
  - Return structured error on failure
  - _Requirements: 8.6, 8.7, 8.9_

- [ ] 18.1 Write unit tests for trading command routing
  - Test OPEN_POSITION command execution
  - Test CLOSE_POSITION command execution
  - Test safety gate integration
  - _Requirements: 8.6, 8.7, 8.9_

- [ ] 19. Checkpoint - Live trading validation
  - Open 0.01 SOL position via UI (devnet)
  - Verify transaction signature returned
  - Verify position appears in table
  - Wait 5 minutes for funding accrual
  - Close position via UI
  - Verify position removed
  - Verify PnL settled
  - Ensure all tests pass, ask the user if questions arise.

---

### Phase 5: Error Handling and Robustness

- [ ] 20. Implement RPC retry logic
  - Create `_rpc_call_with_retry()` helper method
  - Implement exponential backoff (1s, 2s, 4s)
  - Retry up to 3 times for transient errors
  - Log retry attempts with WARNING level
  - Raise exception after max retries
  - _Requirements: 9.1_

- [ ] 20.1 Write property test for error recovery idempotence
  - **Property 12: Error Recovery Idempotence**
  - **Validates: Requirements 9.1, 9.3**

- [ ] 20.2 Write unit tests for RPC retry logic
  - Test successful retry after transient failure
  - Test exception after max retries
  - Test exponential backoff timing
  - _Requirements: 9.1_

- [ ] 21. Implement transaction status query
  - Create `_query_transaction_status()` method
  - Query transaction status for 60 seconds after timeout
  - Return "confirmed", "failed", or "unknown"
  - Mark operation as "unknown" if status cannot be determined
  - Alert user for unknown status
  - _Requirements: 9.3, 9.4_

- [ ] 21.1 Write unit tests for transaction status query
  - Test confirmed transaction
  - Test failed transaction
  - Test unknown transaction
  - _Requirements: 9.3, 9.4_

- [ ] 22. Implement Drift connection recovery
  - Detect connection loss (RPC call failures)
  - Attempt reconnection every 10 seconds
  - Re-sync account state after successful reconnection
  - Broadcast connection status updates to UI
  - Disable trading during connection loss
  - _Requirements: 9.5, 9.6, 9.9_

- [ ] 22.1 Write unit tests for connection recovery
  - Test reconnection after connection loss
  - Test account state re-sync
  - Test trading disabled during outage
  - _Requirements: 9.5, 9.6, 9.9_

- [ ] 23. Implement critical error handling
  - Stop engine on critical errors (wallet missing, invalid sub-account)
  - Broadcast error event to UI with ERROR level
  - Log error with full stack trace
  - Prevent trade execution during error recovery
  - _Requirements: 9.7, 9.8, 9.10_

- [ ] 23.1 Write unit tests for critical error handling
  - Test engine stop on critical error
  - Test error broadcast to UI
  - Test trading disabled during error
  - _Requirements: 9.7, 9.8, 9.10_

- [ ] 24. Checkpoint - Error handling validation
  - Simulate RPC failure → Verify retry
  - Simulate transaction timeout → Verify status query
  - Simulate connection loss → Verify reconnection
  - Simulate critical error → Verify engine stop
  - Ensure all tests pass, ask the user if questions arise.

---

### Phase 6: Logging and Observability

- [ ] 25. Implement comprehensive logging
  - Configure Loguru with environment variable (default INFO)
  - Remove all print() statements (use Logger instead)
  - Log trade execution with all details (timestamp, market, side, size, price, tx_signature)
  - Log account state updates (health_ratio, leverage, collateral)
  - Log errors with ERROR level and exception details
  - Log safety gate rejections with WARNING level
  - Log profitability calculations (revenue, costs, net profit)
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [ ] 25.1 Write unit tests for logging
  - Test log level configuration
  - Test trade execution logging
  - Test error logging format
  - Verify no print() statements in codebase
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [ ] 26. Configure log rotation and retention
  - Set daily rotation policy
  - Set 30-day retention
  - Log to both file and stderr in production
  - Support DEBUG level for debugging
  - _Requirements: 10.8, 10.9, 10.10_

- [ ] 26.1 Write unit tests for log rotation
  - Test daily rotation trigger
  - Test retention policy
  - _Requirements: 10.8, 10.9_

- [ ] 27. Final checkpoint - Full system validation
  - Run full end-to-end test (paper mode)
  - Run full end-to-end test (live mode, devnet)
  - Verify all logs written correctly
  - Verify all metrics displayed in UI
  - Verify all safety gates functional
  - Verify all error handling paths
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at phase boundaries
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- All code must include PEP 484 type hints
- All logging must use Loguru (no print() statements)
- All live transactions must be simulated before submission

---

## Testing Configuration

**Property-Based Testing**:
- Library: `hypothesis`
- Minimum iterations: 100 per test
- Tag format: `# Feature: delta-neutral-live-mode, Property N: [property text]`

**Unit Testing**:
- Framework: `pytest`
- Coverage target: 85%+ for core logic
- Test organization: `tests/engines/funding/`

**Integration Testing**:
- End-to-end flows for each phase
- Manual testing checklist in design document
- Devnet testing before mainnet deployment

---

**Document Version**: 1.0  
**Created**: 2026-01-15  
**Status**: Draft - Awaiting Review
