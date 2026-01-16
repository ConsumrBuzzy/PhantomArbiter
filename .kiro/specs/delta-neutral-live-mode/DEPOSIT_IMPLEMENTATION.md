# Deposit Implementation Documentation

**Date**: 2026-01-15  
**Task**: Task 8 - Implement deposit functionality  
**Status**: ✅ Complete

---

## Overview

Implemented the `deposit()` method in `DriftAdapter` to enable live mode capital management. This allows users to deposit SOL collateral into their Drift Protocol sub-account via the Web UI.

---

## Implementation Details

### Location
- **File**: `src/engines/funding/drift_adapter.py`
- **Method**: `DriftAdapter.deposit(amount_sol: float) -> str`

### Features Implemented

1. **Amount Validation** (Requirement 3.1)
   - Validates amount is positive
   - Checks wallet balance (including 0.017 SOL gas reserve)
   - Raises `ValueError` with user-friendly messages on validation failure

2. **Drift SDK Integration** (Requirement 3.2)
   - Uses `driftpy.DriftClient` for deposit instruction building
   - Converts human-readable SOL amount to spot market precision
   - Handles SOL market index (1) and associated token accounts

3. **Transaction Simulation** (Requirement 3.3, 3.4)
   - Simulation is handled automatically by `DriftClient.deposit()`
   - Transaction is rejected if simulation fails
   - Error messages are propagated to user

4. **Confirmation Handling** (Requirement 3.5)
   - Confirmation is handled automatically by `DriftClient.deposit()`
   - Default timeout is 30 seconds (configured in driftpy)
   - Returns transaction signature on success

5. **Error Handling** (Requirement 3.10)
   - Validation errors: `ValueError` with user-friendly message
   - Connection errors: `RuntimeError` with context
   - All errors logged with full details using Loguru

### Command Routing

Updated `FundingEngine.execute_funding_command()` to route DEPOSIT commands:
- **Paper Mode**: Updates VirtualDriver balance (existing behavior)
- **Live Mode**: Calls `DriftAdapter.deposit()` and returns transaction signature

---

## Usage

### From Web UI

```json
{
  "action": "DEPOSIT",
  "data": {
    "amount": 0.1
  }
}
```

### Programmatic Usage

```python
from src.engines.funding.drift_adapter import DriftAdapter
from src.drivers.wallet_manager import WalletManager

# Initialize adapter
adapter = DriftAdapter(network="mainnet")
wallet = WalletManager()

# Connect
await adapter.connect(wallet, sub_account=0)

# Deposit 0.1 SOL
tx_sig = await adapter.deposit(0.1)
print(f"Transaction: {tx_sig}")

# Cleanup
await adapter.disconnect()
```

---

## Validation Rules

| Validation | Error Message | Exception Type |
|------------|---------------|----------------|
| Amount ≤ 0 | "Deposit amount must be positive" | `ValueError` |
| Amount > wallet balance | "Insufficient balance. Requested: X SOL, Available: Y SOL (reserved 0.017 for gas)" | `ValueError` |
| Not connected | "Not connected to Drift. Call connect() first." | `RuntimeError` |
| No private key | "No private key found in environment" | `RuntimeError` |

---

## Testing

### Manual Testing

Run the test script:
```bash
python test_deposit_live.py
```

This script:
1. Connects to Drift Protocol
2. Fetches current account state
3. Tests validation (negative, zero, excessive amounts)
4. Optionally executes a real 0.01 SOL deposit (requires user confirmation)
5. Verifies balance update

### Expected Behavior

**Validation Tests**:
- ✅ Rejects negative amounts
- ✅ Rejects zero amounts
- ✅ Rejects amounts exceeding wallet balance

**Real Deposit** (if confirmed):
- ✅ Returns transaction signature
- ✅ Transaction confirms within 30 seconds
- ✅ Balance increases by deposited amount

---

## Integration Points

### FundingEngine

The `execute_funding_command()` method routes DEPOSIT commands:

```python
if action == "DEPOSIT":
    amount = float(data.get("amount", 0))
    tx_sig = await self.drift_adapter.deposit(amount)
    return {
        "success": True, 
        "message": f"Deposited {amount} SOL",
        "tx_signature": tx_sig
    }
```

### WebSocket Response Format

```json
{
  "success": true,
  "message": "Deposited 0.1 SOL",
  "tx_signature": "5Kq7..."
}
```

Or on error:

```json
{
  "success": false,
  "message": "Insufficient balance. Requested: 10.0 SOL, Available: 0.5 SOL (reserved 0.017 for gas)"
}
```

---

## Dependencies

### Python Packages
- `driftpy >= 0.7.0` - Drift Protocol Python SDK
- `solana >= 0.32.0` - Solana Python SDK
- `solders >= 0.21.0` - Solana types library
- `base58` - Base58 encoding/decoding

### Environment Variables
- `SOLANA_PRIVATE_KEY` or `PHANTOM_PRIVATE_KEY` - Wallet private key (base58)
- `RPC_URL` - Solana RPC endpoint (optional, defaults to public mainnet)

---

## Known Limitations

1. **SOL Only**: Currently only supports SOL deposits (market index 1)
   - USDC deposits (market index 0) not yet implemented
   - Other spot markets not supported

2. **No Vault Sync**: Engine_Vault balance is not yet updated after deposit
   - Will be implemented in Task 10 (Engine_Vault synchronization)

3. **No Reduce-Only**: Always deposits new collateral (reduce_only=False)
   - Repaying borrows not yet supported

---

## Next Steps

### Task 8.1: Write Property Test (Not Started)
- **Property 14**: Transaction Simulation Requirement
- Validates that all transactions are simulated before submission
- Minimum 100 iterations

### Task 8.2: Write Unit Tests (Not Started)
- Test successful deposit
- Test validation rejection (negative amount)
- Test validation rejection (insufficient balance)
- Test simulation failure handling
- Test confirmation timeout handling

### Task 9: Implement Withdrawal (Not Started)
- Similar structure to deposit
- Additional health ratio validation
- Reject if health would drop below 80%

### Task 10: Engine_Vault Synchronization (Not Started)
- Update Engine_Vault balance after deposit/withdraw
- Implement vault sync verification
- Add retry logic for sync failures

---

## References

- [DriftPy Documentation](https://drift-labs.github.io/driftpy/)
- [DriftPy for Dummies - Depositing](https://drift-2.gitbook.io/driftpy-for-dummies/depositing-and-withdrawing)
- [Drift Protocol SDK](https://github.com/drift-labs/driftpy)
- [Requirements Document](./requirements.md) - Requirement 3
- [Tasks Document](./tasks.md) - Task 8

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-15  
**Author**: Kiro AI Assistant
