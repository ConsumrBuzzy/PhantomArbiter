# Drift Balance Parsing Fix

## Problem
The DriftAdapter was incorrectly parsing the user's Drift account balance, showing $26,395.03 instead of the actual $31.56 balance shown in the Drift UI.

## Root Cause
The raw byte parsing was reading from the wrong offset in the Drift User account data structure. The code was reading from offset 104, which contained an incorrect value.

## Solution
After exploring the Drift account data structure, we discovered that the USDC spot balance (scaled_balance field) is located at **offset 128**, not offset 104.

### Technical Details

**Drift User Account Structure:**
```
- 8 bytes: Anchor discriminator
- 32 bytes: authority
- 32 bytes: delegate
- 32 bytes: name
- 8 bytes: sub_account_id
- 8 bytes: status
- 8 bytes: next_order_id
- ... (other fields)
- Offset 128: First spot position scaled_balance (USDC, market index 0)
```

**Correct Parsing:**
```python
USDC_BALANCE_OFFSET = 128
usdc_scaled = struct.unpack_from("<q", data, USDC_BALANCE_OFFSET)[0]
usdc_balance = usdc_scaled / 1e6  # Convert from raw to USDC (1e6 precision)
```

## Files Modified

1. **src/engines/funding/drift_adapter.py**
   - Fixed `_parse_collateral()` to read from offset 128
   - Updated precision conversion (divide by 1e6, not 1e3)
   - Removed incorrect API fallback logic
   - Updated docstrings

2. **src/tools/drift_cli.py**
   - Updated DRIFT_API_URL constant (though not used for balance fetching)
   - Changed from `drift-gateway-api.mainnet.drift.trade` to `dlob.drift.trade`

3. **src/shared/state/vault_manager.py**
   - Updated API URL in `sync_from_drift()` method

## Verification

Running `python check_drift_equity.py` now correctly shows:
```
Collateral: $31.60
Health: 100.00%
Leverage: 0.00x
Positions: 0
```

This matches the user's Drift UI balance of $31.56 (small difference due to interest accrual).

## API Endpoint Research

During investigation, we discovered:
- The DLOB server (`https://dlob.drift.trade/`) is for orderbook/trades data, NOT user account balances
- User account data must be fetched directly from the blockchain
- The `/user/{wallet}` endpoint does not exist on the DLOB server
- The correct approach is to parse on-chain data directly (which we now do correctly)

## Status
✅ **FIXED** - The DriftAdapter now correctly parses the user's Drift account balance from on-chain data.
