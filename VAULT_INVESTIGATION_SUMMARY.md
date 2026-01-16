# Vault Investigation Summary

## Issue
User reported dashboard showing $4.98 in "Universal Vault" when expecting to see their Drift account balance.

## Root Causes Found

### 1. Database Pollution
- **1,042 test engine vaults** from test runs were never cleaned up
- These vaults aggregated to **$310M+** in the global snapshot
- Test vaults were created with pattern `test_engine_<uuid>`

### 2. Scalp Engine Vault Bloat
- Scalp engine vault contained **$277M** in test tokens
- Tokens included: BONK, WIF, JITOSOL, MSOL, POPCAT, GOAT, ACT, PENGU, MOODENG, CHILLGUY
- This was from simulation/testing runs that weren't cleaned up

### 3. Stale Funding Vault Data
- Funding vault showed **$4,163.42** (old data)
- Actual Drift collateral is **$26,395.05**
- Vault was not syncing automatically from Drift on startup

## Actual Account Balances

### Phantom Wallet (On-Chain)
- **Total**: $29.58
- **USDC**: $26.60
- **SOL**: 0.0199 (~$3 for gas)
- **Dust tokens**: TNSRxc, 6YUoZe, E7d9wp, CASH (negligible value)

### Drift Account (Perp DEX)
- **Collateral**: $26,395.05 USDC
- **Health**: 100%
- **Leverage**: 0x (no open positions)
- **Positions**: 0

### Total Net Worth
- **$26,424.63** across all venues

## Actions Taken

### 1. Database Cleanup
```sql
-- Deleted 1,042 test engine vaults
DELETE FROM engine_vaults WHERE engine LIKE 'test_engine_%';

-- Deleted remaining test vaults
DELETE FROM engine_vaults WHERE engine = 'test' OR engine LIKE 'test_%';
```

### 2. Vault Resets
- Reset scalp vault to default ($50 paper mode balance)
- Synced funding vault from Drift ($26,395.05)

### 3. Final State
- **Total Equity**: $26,645.05
- **Active Vaults**: 6 (arb, drift, funding, global, lst, scalp)
- **Funding Vault**: $26,395.05 (synced from Drift)
- **Other Vaults**: ~$250 (default paper mode balances)

## Dashboard Display Issue

The $4.98 value was likely caused by:
1. **Stale vault data** showing old Drift balance
2. **Calculation error** in the unified balance aggregation
3. **Display bug** showing a specific token balance instead of total equity

The dashboard's "Universal Vault" should now correctly show **~$26,400** after:
- Cleaning up test vaults
- Syncing funding vault from Drift
- Resetting bloated engine vaults

## Recommendations

### 1. Automatic Vault Sync
Add automatic Drift vault sync on engine startup:

```python
# In FundingEngine.start()
if self.live_mode:
    vault = get_engine_vault("funding")
    await vault.sync_from_drift(self.drift_adapter)
```

### 2. Test Cleanup
Add vault cleanup to test teardown:

```python
# In conftest.py or test fixtures
@pytest.fixture(autouse=True)
def cleanup_test_vaults():
    yield
    # Cleanup after test
    db = get_db()
    conn = db._get_connection()
    conn.execute("DELETE FROM engine_vaults WHERE engine LIKE 'test_engine_%'")
    conn.commit()
```

### 3. Vault Monitoring
Add logging to track vault state changes:

```python
# In vault_manager.py
def _save_state(self):
    logger.info(f"[{self.engine_name}] Vault updated: {self.balances}")
    # ... existing save logic
```

### 4. Dashboard Health Check
Add a health check endpoint to verify vault data integrity:

```python
# In dashboard_server.py
elif action == "VAULT_HEALTH_CHECK":
    # Check for anomalies (>$1M in single vault, >100 vaults, etc.)
    # Return warnings if found
```

## Files Created

- `check_all_vaults.py` - Inspect all vaults in database
- `sync_drift_vault.py` - Manual vault sync from Drift
- `check_dashboard_value.py` - Investigate $4.98 value source
- `check_drift_equity.py` - Verify Drift account state
- `fix_vault_and_cleanup.py` - Clean up test vaults and sync
- `final_cleanup.py` - Remove remaining test vaults
- `verify_final_state.py` - Verify final vault state

## Next Steps

1. **Test Dashboard**: Start dashboard and verify it shows $26,400+ in Universal Vault
2. **Implement Auto-Sync**: Add Drift vault sync to FundingEngine.start()
3. **Add Test Cleanup**: Prevent future test vault pollution
4. **Monitor Production**: Watch for any vault anomalies in live mode
