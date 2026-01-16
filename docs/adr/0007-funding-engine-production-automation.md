# ADR-0007: Funding Engine Production Automation

**Status:** Proposed  
**Date:** 2026-01-16  
**Deciders:** Development Team  
**Technical Story:** Complete autonomous operation of Funding Engine in live mode

---

## Context

The Funding Engine (Delta Neutral Engine) currently operates at **~75% automation readiness**. It can autonomously detect delta drift and execute corrective trades in live mode, but lacks critical safety controls and error recovery mechanisms needed for unattended production operation.

### Current State (What Works)
- ✅ Auto-rebalancing logic with 1% drift tolerance
- ✅ 30-minute cooldown between trades
- ✅ Live mode execution via DriftAdapter
- ✅ Health monitoring with warnings (50%/20% thresholds)
- ✅ Vault synchronization after trades
- ✅ Manual command execution (DEPOSIT, WITHDRAW, OPEN/CLOSE positions)

### Missing Components (What's Needed)
- ❌ **Safety Gates**: Profitability checks, latency monitoring, fee estimation
- ❌ **MEV Protection**: Jito bundle submission with RPC fallback
- ❌ **Error Recovery**: Automatic reconnection and state re-sync
- ❌ **Comprehensive Logging**: Audit trail for profitability and safety decisions

### Business Impact
Without these components, the engine requires **supervised operation** (human monitoring). Completing these features enables **unattended operation**, reducing operational overhead and enabling 24/7 autonomous trading.

---

## Decision

We will implement the remaining automation components in **4 phases**, prioritized by risk mitigation:

### Phase 1: Safety Gates Integration (CRITICAL)
**Priority:** P0 - Blocks production deployment  
**Estimated Time:** 2-3 hours  
**Risk Mitigation:** Prevents unprofitable trades and toxic flow execution

### Phase 2: MEV Protection (HIGH)
**Priority:** P1 - Reduces slippage and MEV losses  
**Estimated Time:** 2-3 hours  
**Risk Mitigation:** Protects against front-running and sandwich attacks

### Phase 3: Error Recovery (HIGH)
**Priority:** P1 - Enables unattended operation  
**Estimated Time:** 1-2 hours  
**Risk Mitigation:** Automatic recovery from transient failures

### Phase 4: Comprehensive Logging (MEDIUM)
**Priority:** P2 - Audit and debugging  
**Estimated Time:** 1 hour  
**Risk Mitigation:** Enables post-mortem analysis and compliance

**Total Estimated Time:** 6-9 hours

---

## Phase 1: Safety Gates Integration

### Objective
Integrate existing `SafetyGate` class into FundingEngine to prevent unprofitable or dangerous trades.

### Implementation Plan

#### Task 1.1: Add SafetyGate to FundingEngine
**File:** `src/engines/funding/logic.py`

```python
class FundingEngine(BaseEngine):
    def __init__(self, live_mode: bool = False, config: Optional[RebalanceConfig] = None):
        super().__init__("funding", live_mode)
        self.config = config or RebalanceConfig()
        self.safety_gate = SafetyGate()  # NEW
        self.latency_monitor = LatencyMonitor()  # NEW
        # ... existing code
```

#### Task 1.2: Add Profitability Check Before Rebalance
**Location:** `check_and_rebalance()` method, before trade execution

```python
# Calculate expected revenue
funding_rate = await self._get_current_funding_rate("SOL-PERP")
conservative_rate = funding_rate * 0.5  # 50% haircut (Requirement 6.4)
expected_revenue_usd = correction_size * sol_price * conservative_rate * 3 * 365 / 365  # Daily

# Estimate costs
jito_tip_lamports = 10000  # 0.00001 SOL
estimated_costs = await self._estimate_trade_costs(
    correction_size, 
    sol_price, 
    jito_tip_lamports
)

# Check profitability
can_execute = await self.safety_gate.can_execute(
    wallet=wallet_manager,
    latency_monitor=self.latency_monitor,
    expected_profit_usd=expected_revenue_usd,
    trade_amount_usd=correction_size * sol_price,
    sol_price=sol_price,
    jito_tip_lamports=jito_tip_lamports
)

if not can_execute:
    Logger.warning(f"[REBALANCER] Trade blocked by safety gate")
    result["status"] = "blocked"
    result["message"] = "Trade blocked: unprofitable or unsafe"
    return result
```

#### Task 1.3: Implement Cost Estimation
**New Method:** `_estimate_trade_costs()`

```python
async def _estimate_trade_costs(
    self, 
    size: float, 
    sol_price: float, 
    jito_tip_lamports: int
) -> float:
    """
    Estimate total trade costs.
    
    Validates: Requirements 6.1
    
    Returns:
        Total cost in USD
    """
    # Jito tip cost
    jito_tip_sol = jito_tip_lamports / (10 ** 9)
    jito_cost_usd = jito_tip_sol * sol_price
    
    # Drift trading fee (0.1% taker)
    drift_fee_usd = size * sol_price * 0.001
    
    # Slippage estimate (0.02% for typical size)
    slippage_usd = size * sol_price * 0.0002
    
    # Base transaction fee (~0.000005 SOL)
    base_fee_usd = 0.000005 * sol_price
    
    total_cost = jito_cost_usd + drift_fee_usd + slippage_usd + base_fee_usd
    
    Logger.debug(f"[COST] Jito: ${jito_cost_usd:.4f}, Drift: ${drift_fee_usd:.4f}, "
                 f"Slippage: ${slippage_usd:.4f}, Base: ${base_fee_usd:.4f}, "
                 f"Total: ${total_cost:.4f}")
    
    return total_cost
```

#### Task 1.4: Add Latency Monitoring
**New Method:** `_check_network_latency()`

```python
async def _check_network_latency(self) -> bool:
    """
    Check if network latency is acceptable.
    
    Validates: Requirements 6.5
    
    Returns:
        True if latency is acceptable, False otherwise
    """
    latency_ms = await self.latency_monitor.get_current_latency()
    threshold_ms = 500  # 500ms threshold (Requirement 6.5)
    
    if latency_ms > threshold_ms:
        Logger.warning(f"[SAFETY] Network latency too high: {latency_ms}ms > {threshold_ms}ms")
        return False
    
    return True
```

#### Task 1.5: Unit Tests
**File:** `tests/unit/test_funding_engine_safety.py`

- Test profitability check with various funding rates
- Test cost estimation accuracy
- Test latency kill-switch
- Test safety gate integration

**Acceptance Criteria:**
- ✅ Unprofitable trades are blocked
- ✅ High latency blocks trades
- ✅ Insufficient balance blocks trades
- ✅ All safety checks logged with WARNING level

---

## Phase 2: MEV Protection via Jito

### Objective
Integrate Jito bundle submission to protect against MEV attacks (front-running, sandwich attacks).

### Implementation Plan

#### Task 2.1: Add Jito Client to DriftAdapter
**File:** `src/engines/funding/drift_adapter.py`

```python
from jito_searcher_client import get_searcher_client

class DriftAdapter:
    def __init__(self, network: str = "mainnet"):
        # ... existing code
        self.jito_client = None
        self.jito_enabled = True  # Can be disabled via config
    
    async def connect(self, wallet: WalletManager, sub_account: int = 0) -> bool:
        # ... existing connection code
        
        # Initialize Jito client
        if self.jito_enabled:
            try:
                self.jito_client = get_searcher_client(
                    "mainnet.block-engine.jito.wtf"
                )
                Logger.success("[DRIFT] ✅ Jito client initialized")
            except Exception as e:
                Logger.warning(f"[DRIFT] Jito initialization failed: {e}")
                Logger.info("[DRIFT] Will use standard RPC submission")
                self.jito_enabled = False
```

#### Task 2.2: Implement Jito Bundle Submission
**New Method:** `_submit_via_jito()`

```python
async def _submit_via_jito(
    self, 
    transaction: VersionedTransaction,
    max_retries: int = 3
) -> str:
    """
    Submit transaction via Jito bundle.
    
    Validates: Requirements 4.5, 4.6
    
    Args:
        transaction: Signed transaction
        max_retries: Maximum retry attempts
    
    Returns:
        Transaction signature
    
    Raises:
        Exception if all retries fail
    """
    for attempt in range(1, max_retries + 1):
        try:
            Logger.info(f"[JITO] Submitting bundle (attempt {attempt}/{max_retries})...")
            
            # Create bundle with single transaction
            bundle = [transaction]
            
            # Submit bundle
            bundle_id = await self.jito_client.send_bundle(bundle)
            
            Logger.info(f"[JITO] Bundle submitted: {bundle_id}")
            
            # Wait for confirmation (up to 30 seconds)
            signature = await self._wait_for_bundle_confirmation(bundle_id, timeout=30)
            
            Logger.success(f"[JITO] ✅ Bundle confirmed: {signature}")
            return signature
            
        except Exception as e:
            Logger.warning(f"[JITO] Attempt {attempt} failed: {e}")
            
            if attempt < max_retries:
                await asyncio.sleep(1)  # Brief delay before retry
            else:
                Logger.error(f"[JITO] All {max_retries} attempts failed")
                raise
```

#### Task 2.3: Add RPC Fallback
**Update:** `open_position()` method

```python
async def open_position(
    self,
    market: str,
    direction: str,
    size: float,
    max_leverage: float = 5.0
) -> str:
    """Open a position with Jito protection and RPC fallback."""
    
    # Build transaction
    transaction = await self._build_position_transaction(
        market, direction, size, max_leverage
    )
    
    # Try Jito first
    if self.jito_enabled and self.jito_client:
        try:
            return await self._submit_via_jito(transaction, max_retries=3)
        except Exception as e:
            Logger.warning(f"[DRIFT] Jito submission failed after retries: {e}")
            Logger.info("[DRIFT] Falling back to standard RPC submission")
    
    # Fallback to standard RPC
    return await self._submit_via_rpc(transaction)
```

#### Task 2.4: Unit Tests
**File:** `tests/unit/test_jito_integration.py`

- Test Jito bundle submission
- Test retry logic
- Test RPC fallback
- Test bundle confirmation timeout

**Acceptance Criteria:**
- ✅ Jito submission attempted first
- ✅ Falls back to RPC after 3 failed attempts
- ✅ Transaction confirmed within 30 seconds
- ✅ All attempts logged

---

## Phase 3: Error Recovery and Reconnection

### Objective
Enable automatic recovery from transient failures (RPC disconnections, network issues).

### Implementation Plan

#### Task 3.1: Add Reconnection Loop
**New Method:** `_reconnection_loop()`

```python
async def _reconnection_loop(self):
    """
    Automatic reconnection loop for DriftAdapter.
    
    Validates: Requirements 9.5, 9.6
    
    Runs in background, attempts reconnection every 10 seconds
    when disconnected.
    """
    while self.running:
        try:
            # Check if connected
            if not self.drift_adapter or not self.drift_adapter.is_connected:
                Logger.warning("[FUNDING] Drift disconnected, attempting reconnection...")
                
                # Attempt reconnection
                from src.drivers.wallet_manager import WalletManager
                wallet_manager = WalletManager()
                
                success = await self.drift_adapter.connect(wallet_manager, sub_account=0)
                
                if success:
                    Logger.success("[FUNDING] ✅ Reconnected to Drift Protocol")
                    
                    # Re-sync state after reconnection (Requirement 9.6)
                    await self._sync_vault_from_drift()
                    
                    # Broadcast recovery event
                    if self._callback:
                        await self._callback({
                            "type": "ENGINE_STATUS",
                            "status": "recovered",
                            "message": "Reconnected to Drift Protocol"
                        })
                else:
                    Logger.error("[FUNDING] Reconnection failed, will retry in 10s")
            
            # Check every 10 seconds
            await asyncio.sleep(10)
            
        except Exception as e:
            Logger.error(f"[FUNDING] Reconnection loop error: {e}")
            await asyncio.sleep(10)
```

#### Task 3.2: Add Transaction Status Polling
**New Method:** `_poll_transaction_status()`

```python
async def _poll_transaction_status(
    self, 
    signature: str, 
    timeout: int = 60
) -> Optional[str]:
    """
    Poll transaction status for unknown transactions.
    
    Validates: Requirements 9.3, 9.4
    
    Args:
        signature: Transaction signature
        timeout: Maximum polling time in seconds
    
    Returns:
        "confirmed", "failed", or None (unknown)
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            status = await self.drift_adapter.get_transaction_status(signature)
            
            if status in ["confirmed", "finalized"]:
                Logger.success(f"[TX] Transaction confirmed: {signature}")
                return "confirmed"
            elif status == "failed":
                Logger.error(f"[TX] Transaction failed: {signature}")
                return "failed"
            
            # Still pending, wait and retry
            await asyncio.sleep(5)
            
        except Exception as e:
            Logger.debug(f"[TX] Status check error: {e}")
            await asyncio.sleep(5)
    
    # Timeout reached, status unknown
    Logger.error(f"[TX] Transaction status unknown after {timeout}s: {signature}")
    return None
```

#### Task 3.3: Add Trading Disable During Recovery
**Update:** `check_and_rebalance()` method

```python
# Check if in recovery mode
if self._in_recovery_mode:
    result["status"] = "recovery"
    result["message"] = "Trading disabled during error recovery"
    return result
```

#### Task 3.4: Integration Tests
**File:** `tests/integration/test_error_recovery.py`

- Test automatic reconnection
- Test state re-sync after recovery
- Test transaction status polling
- Test trading disable during recovery

**Acceptance Criteria:**
- ✅ Reconnects automatically every 10 seconds
- ✅ Re-syncs state after reconnection
- ✅ Polls transaction status for 60 seconds
- ✅ Marks unknown transactions appropriately
- ✅ Disables trading during recovery

---

## Phase 4: Comprehensive Logging

### Objective
Add complete audit trail for profitability calculations, safety decisions, and trade execution.

### Implementation Plan

#### Task 4.1: Add Profitability Logging
**Location:** Before profitability check in `check_and_rebalance()`

```python
Logger.info(f"[PROFITABILITY] Expected revenue: ${expected_revenue_usd:.4f}")
Logger.info(f"[PROFITABILITY] Estimated costs: ${estimated_costs:.4f}")
Logger.info(f"[PROFITABILITY] Net profit: ${expected_revenue_usd - estimated_costs:.4f}")
Logger.info(f"[PROFITABILITY] Funding rate: {funding_rate:.6f} (conservative: {conservative_rate:.6f})")
```

#### Task 4.2: Add Safety Gate Logging
**Location:** When safety gate blocks trade

```python
Logger.warning(f"[SAFETY] Trade blocked by safety gate")
Logger.warning(f"[SAFETY] Reason: {safety_gate.get_last_rejection_reason()}")
Logger.warning(f"[SAFETY] Expected profit: ${expected_revenue_usd:.4f}")
Logger.warning(f"[SAFETY] Estimated costs: ${estimated_costs:.4f}")
```

#### Task 4.3: Add Trade Execution Logging
**Location:** After successful trade execution

```python
Logger.info(f"[TRADE] Market: {market}")
Logger.info(f"[TRADE] Side: {direction}")
Logger.info(f"[TRADE] Size: {size:.6f}")
Logger.info(f"[TRADE] Price: ${price:.2f}")
Logger.info(f"[TRADE] Signature: {tx_signature}")
Logger.info(f"[TRADE] Timestamp: {datetime.now().isoformat()}")
```

#### Task 4.4: Add Account State Logging
**Location:** After fetching account state

```python
Logger.info(f"[ACCOUNT] Health ratio: {health_ratio:.1f}%")
Logger.info(f"[ACCOUNT] Leverage: {leverage:.2f}x")
Logger.info(f"[ACCOUNT] Total collateral: ${collateral:.2f}")
Logger.info(f"[ACCOUNT] Free collateral: ${free_collateral:.2f}")
```

**Acceptance Criteria:**
- ✅ All profitability calculations logged
- ✅ All safety gate decisions logged
- ✅ All trade executions logged with full details
- ✅ All account state updates logged
- ✅ Logs include timestamps and context

---

## Consequences

### Positive
- ✅ **Unattended Operation**: Engine can run 24/7 without human supervision
- ✅ **Risk Mitigation**: Safety gates prevent unprofitable and dangerous trades
- ✅ **MEV Protection**: Jito integration reduces slippage and front-running
- ✅ **Reliability**: Automatic recovery from transient failures
- ✅ **Auditability**: Complete log trail for compliance and debugging
- ✅ **Production Ready**: Meets all requirements for live deployment

### Negative
- ⚠️ **Complexity**: Additional code to maintain and test
- ⚠️ **Dependencies**: Requires Jito client library
- ⚠️ **Testing Overhead**: More integration tests needed

### Neutral
- 📊 **Performance**: Minimal impact (safety checks add <50ms per trade)
- 📊 **Cost**: Jito tips add ~$0.01 per trade (acceptable for MEV protection)

---

## Implementation Timeline

### Week 1: Safety Gates (P0)
- **Days 1-2:** Implement safety gate integration
- **Day 3:** Unit tests and validation
- **Deliverable:** Profitability checks operational

### Week 2: MEV Protection (P1)
- **Days 1-2:** Implement Jito integration
- **Day 3:** Testing and RPC fallback validation
- **Deliverable:** MEV protection operational

### Week 3: Error Recovery (P1)
- **Days 1-2:** Implement reconnection and status polling
- **Day 3:** Integration tests
- **Deliverable:** Automatic recovery operational

### Week 4: Logging & Polish (P2)
- **Day 1:** Complete logging implementation
- **Days 2-3:** End-to-end testing and documentation
- **Deliverable:** Production-ready engine

**Total Timeline:** 4 weeks (part-time) or 1-2 weeks (full-time)

---

## Testing Strategy

### Unit Tests
- Safety gate integration
- Cost estimation accuracy
- Jito submission logic
- Reconnection logic
- Transaction status polling

### Integration Tests
- End-to-end rebalance with safety checks
- Jito submission with RPC fallback
- Automatic recovery from disconnection
- Full position lifecycle with logging

### Property-Based Tests
- Profitability calculation (Property 26, 27, 28)
- Cost estimation (Property 25)
- Latency kill-switch (Property 29)
- Balance guard (Property 30)

### Manual Testing
- Run engine in live mode for 24 hours
- Verify no unprofitable trades executed
- Verify automatic recovery from simulated failures
- Verify complete log trail

---

## Success Criteria

### Functional Requirements
- ✅ All safety gates operational
- ✅ Jito submission with RPC fallback
- ✅ Automatic reconnection working
- ✅ Complete audit logging

### Performance Requirements
- ✅ Safety checks complete in <50ms
- ✅ Jito submission within 30 seconds
- ✅ Reconnection within 10 seconds
- ✅ Transaction status determined within 60 seconds

### Reliability Requirements
- ✅ 99.9% uptime over 7 days
- ✅ Zero unprofitable trades
- ✅ Automatic recovery from all transient failures
- ✅ Complete log coverage for audit

---

## References

- [Requirements Document](../.kiro/specs/delta-neutral-live-mode/requirements.md)
- [Design Document](../.kiro/specs/delta-neutral-live-mode/design.md)
- [Task List](../.kiro/specs/delta-neutral-live-mode/tasks.md)
- [SafetyGate Implementation](../src/delta_neutral/safety_gates.py)
- [DriftAdapter Implementation](../src/engines/funding/drift_adapter.py)
- [FundingEngine Implementation](../src/engines/funding/logic.py)

---

## Appendix: Risk Assessment

### High Risk (Requires Immediate Attention)
1. **Unprofitable Trades**: Without safety gates, engine may execute losing trades
   - **Mitigation:** Phase 1 (Safety Gates) is P0
   
2. **MEV Attacks**: Standard RPC submission vulnerable to front-running
   - **Mitigation:** Phase 2 (Jito) is P1

### Medium Risk (Manageable with Monitoring)
3. **Network Failures**: Transient disconnections may cause missed opportunities
   - **Mitigation:** Phase 3 (Error Recovery) is P1
   
4. **Audit Trail Gaps**: Incomplete logging may hinder debugging
   - **Mitigation:** Phase 4 (Logging) is P2

### Low Risk (Acceptable)
5. **Jito Dependency**: Jito service outage requires RPC fallback
   - **Mitigation:** Automatic fallback implemented in Phase 2

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-16  
**Next Review:** After Phase 1 completion
