# Phase 2 Checkpoint: Live Mode Read-Only Monitoring

**Status**: Ready for Validation  
**Date**: 2026-01-15

---

## Overview

Phase 2 implements live mode read-only monitoring, allowing the Funding Engine to connect to your actual Drift Protocol account and display real-time data in the UI.

**Completed Tasks**:
- ✅ Task 4: DriftAdapter connection logic with retry
- ✅ Task 4.1: Unit tests for DriftAdapter connection (8 tests)
- ✅ Task 5: Account state fetching and parsing
- ✅ Task 5.1: Property test for health ratio calculation (100 iterations)
- ✅ Task 6: Live monitoring integration into FundingEngine
- ✅ Task 6.1: Property test for WebSocket response timeliness (100 iterations)
- ✅ Task 6.2: Unit tests for live monitoring (8 tests)

**Test Results**: 25/25 tests passing

---

## Validation Steps

### Step 1: Verify Test Suite

Run all Phase 2 tests to ensure everything passes:

```bash
python -m pytest tests/engines/funding/ -v
```

**Expected**: All 25 tests pass

---

### Step 2: Test Live Connection

Run the live connection test script to verify your wallet can connect to Drift:

```bash
python test_live_mode_connection.py
```

**Expected Output**:
```
================================================================================
LIVE MODE CONNECTION TEST
================================================================================

✅ Wallet loaded from .env
Creating DriftAdapter...
Loading WalletManager...
Wallet address: <YOUR_WALLET_ADDRESS>

Connecting to Drift Protocol...
✅ Connected to Drift Protocol!

Fetching account state...
================================================================================
ACCOUNT STATE
================================================================================
Collateral: $XXX.XX
Health Ratio: XX.XX%
Leverage: X.XXx
Maintenance Margin: $XX.XX

POSITIONS:
  SOL-PERP: SHORT X.XXXX
    Entry: $XXX.XX
    Mark: $XXX.XX
    PnL: $XX.XX

================================================================================
✅ Live mode connection test PASSED
================================================================================
```

**Validation Checklist**:
- [ ] Connection succeeds without errors
- [ ] Wallet address matches your expected address
- [ ] Account state displays correctly
- [ ] Positions match what you see in Drift UI (https://app.drift.trade)
- [ ] Health ratio matches Drift UI (within 1%)
- [ ] Leverage calculation is accurate

---

### Step 3: Compare with Drift UI

Open the Drift UI and compare the values:

1. Go to https://app.drift.trade
2. Connect your wallet
3. Navigate to your account overview

**Compare**:
- [ ] Collateral matches (within $0.01)
- [ ] Health ratio matches (within 1%)
- [ ] Position sizes match exactly
- [ ] Entry prices match (within $0.01)
- [ ] Mark prices match (within $0.10)
- [ ] PnL matches (within $1.00)

**Note**: Small differences are expected due to:
- Funding rate accrual between fetches
- Mark price updates
- Network latency

---

### Step 4: Test Health Warnings

If your health ratio is above 50%, you can skip this step. Otherwise:

**Expected Behavior**:
- Health < 50%: Warning logged with "⚠️ WARNING: Health ratio XX.X% - Consider adding collateral"
- Health < 20%: Critical alert logged with "🚨 CRITICAL: Health ratio XX.X% - Risk of liquidation!"

**Validation**:
- [ ] Warnings appear at correct thresholds
- [ ] Warnings respect 60-second cooldown
- [ ] WebSocket broadcasts health alerts to UI

---

### Step 5: Test UI Integration (Optional)

If you have the dashboard running:

```bash
python run_dashboard.py
```

Then in the UI:
1. Start the Funding Engine in LIVE mode
2. Verify the engine status shows "RUNNING"
3. Verify positions table updates every 10 seconds
4. Verify health ratio displays correctly
5. Verify leverage displays correctly
6. Verify collateral displays correctly

**Validation**:
- [ ] UI updates every 10 seconds
- [ ] All metrics display correctly
- [ ] No errors in browser console
- [ ] No errors in server logs

---

## Troubleshooting

### Connection Fails

**Error**: "User account not found"

**Solution**: Your Drift account is not initialized. Visit https://app.drift.trade and initialize your account first.

---

**Error**: "RPC connection failed"

**Solution**: 
1. Check your RPC_URL in .env
2. Verify your RPC endpoint is working
3. Try a different RPC endpoint (e.g., Helius, QuickNode)

---

### Account State Parsing Errors

**Error**: "Failed to parse account data"

**Solution**: This indicates a mismatch in the account structure. Please report this issue with:
1. Your Drift account address
2. The full error message
3. The raw account data (if available)

---

### Health Ratio Mismatch

**Issue**: Health ratio differs significantly from Drift UI

**Possible Causes**:
1. Collateral calculation incomplete (Phase 2 limitation)
2. Oracle price differences
3. Unsettled PnL not included

**Note**: Full collateral calculation will be implemented in Phase 3.

---

## Known Limitations (Phase 2)

1. **Collateral Calculation**: Currently simplified. Full implementation in Phase 3.
2. **Oracle Prices**: Using entry prices as placeholders. Oracle integration in Phase 4.
3. **Unsettled PnL**: Not yet parsed from account data. Phase 3 enhancement.
4. **Read-Only**: No trading or capital management yet. Phase 3 & 4.

---

## Next Steps

Once all validation steps pass:

1. Mark Task 7 as complete in tasks.md
2. Proceed to Phase 3: Live Mode Capital Management
3. Implement deposit/withdraw functionality
4. Implement vault synchronization

---

## Sign-Off

**Validation Date**: _________________

**Validated By**: _________________

**Issues Found**: _________________

**Ready for Phase 3**: [ ] YES  [ ] NO

---

**Notes**:

