# Testing Deposit Functionality - Quick Guide

## Overview

Task 8 (Deposit Functionality) has been implemented. This guide will help you test it.

---

## What Was Implemented

✅ **DriftAdapter.deposit()** - Deposits SOL to your Drift sub-account  
✅ **Validation** - Checks amount is positive and you have sufficient balance  
✅ **Transaction Simulation** - Automatically simulated before submission  
✅ **Confirmation** - Waits up to 30 seconds for transaction confirmation  
✅ **Error Handling** - User-friendly error messages  

---

## Prerequisites

1. **Funded Wallet**: You need SOL in your wallet
   - Minimum: 0.027 SOL (0.01 for deposit + 0.017 reserved for gas)
   - Your wallet: `99G8vXM4YjULWtmzshsVCJ7AJeb8Psr8dfWuHbwGxry3`

2. **Environment Variables**: Ensure `.env` has:
   ```
   SOLANA_PRIVATE_KEY=your_private_key_here
   RPC_URL=your_rpc_url_here
   ```

3. **Drift Account**: Your Drift account should be initialized
   - You already have this (confirmed in previous tests)

---

## Testing Options

### Option 1: Automated Test Script (Recommended)

Run the test script:
```bash
python test_deposit_live.py
```

**What it does**:
1. Connects to Drift Protocol
2. Shows your current balance and health
3. Tests validation (negative, zero, excessive amounts)
4. **Asks for confirmation** before executing a real 0.01 SOL deposit
5. Verifies balance update after deposit

**Expected Output**:
```
================================================================================
DEPOSIT FUNCTIONALITY TEST
================================================================================

[1] Connecting to Drift Protocol...
[DRIFT] ✅ Connected to mainnet

[2] Fetching current account state...
Current collateral: $31.60
Health ratio: 100.0%
Leverage: 0.00x

[3] Testing deposit validation...
✅ PASSED: Correctly rejected negative amount
✅ PASSED: Correctly rejected zero amount
✅ PASSED: Correctly rejected excessive amount

[4] Real deposit test
⚠️  This will execute a REAL transaction on mainnet!

Do you want to deposit 0.01 SOL? (yes/no): yes

[5] Executing deposit of 0.01 SOL...
[DRIFT] ✅ Deposit successful!
Transaction signature: 5Kq7...
View on Solscan: https://solscan.io/tx/5Kq7...

[6] Fetching updated account state...
New collateral: $33.00
Change: $1.40

================================================================================
TEST COMPLETE
================================================================================
```

### Option 2: Via Web UI (When Available)

Once the UI is connected:
1. Navigate to Funding Engine dashboard
2. Click "Deposit" button
3. Enter amount (e.g., 0.01 SOL)
4. Click "Confirm"
5. Wait for transaction confirmation
6. Verify balance update in UI

### Option 3: Programmatic Test

Create a simple Python script:
```python
import asyncio
from src.engines.funding.drift_adapter import DriftAdapter
from src.drivers.wallet_manager import WalletManager

async def test():
    adapter = DriftAdapter(network="mainnet")
    wallet = WalletManager()
    
    await adapter.connect(wallet, sub_account=0)
    
    # Deposit 0.01 SOL
    tx_sig = await adapter.deposit(0.01)
    print(f"Success! Transaction: {tx_sig}")
    
    await adapter.disconnect()

asyncio.run(test())
```

---

## Validation Tests

The implementation includes these validations:

| Test Case | Expected Behavior |
|-----------|-------------------|
| Negative amount | ❌ Rejected: "Deposit amount must be positive" |
| Zero amount | ❌ Rejected: "Deposit amount must be positive" |
| Amount > balance | ❌ Rejected: "Insufficient balance. Requested: X SOL, Available: Y SOL (reserved 0.017 for gas)" |
| Valid amount | ✅ Accepted: Returns transaction signature |

---

## Troubleshooting

### Error: "Not connected to Drift"
**Solution**: Ensure you call `connect()` before `deposit()`

### Error: "Insufficient balance"
**Solution**: 
- Check your wallet balance: `solana balance 99G8vXM4YjULWtmzshsVCJ7AJeb8Psr8dfWuHbwGxry3`
- Remember: 0.017 SOL is reserved for gas
- Try a smaller amount

### Error: "No private key found"
**Solution**: Check your `.env` file has `SOLANA_PRIVATE_KEY` or `PHANTOM_PRIVATE_KEY`

### Error: "User account not found"
**Solution**: Your Drift account may not be initialized. Visit https://app.drift.trade/ to initialize.

### Transaction Times Out
**Solution**: 
- Check RPC endpoint is responsive
- Try again (network congestion)
- Increase timeout (currently 30s)

---

## What to Verify

After a successful deposit:

1. **Transaction Signature**: Should be returned and valid
   - View on Solscan: `https://solscan.io/tx/{signature}`

2. **Balance Update**: Collateral should increase
   - Check via `adapter.get_account_state()`
   - Or check Drift UI: https://app.drift.trade/

3. **Health Ratio**: Should remain healthy (>80%)

4. **No Errors**: Check logs for any warnings or errors

---

## Safety Notes

⚠️ **This executes REAL transactions on mainnet**
- Start with small amounts (0.01 SOL)
- Verify transaction signatures on Solscan
- Keep 0.017 SOL reserved for gas

✅ **Safe to test**:
- Validation tests (no real transactions)
- Small deposits (0.01 - 0.1 SOL)

❌ **Not recommended**:
- Large deposits without testing first
- Depositing all your SOL (need gas reserve)

---

## Next Steps After Testing

Once deposit is working:

1. **Task 8.1**: Write property test (Property 14)
2. **Task 8.2**: Write unit tests
3. **Task 9**: Implement withdrawal functionality
4. **Task 10**: Implement Engine_Vault synchronization

---

## Questions?

If you encounter issues:
1. Check the logs (Loguru output)
2. Verify transaction on Solscan
3. Check Drift UI for account state
4. Review error messages (they're designed to be helpful!)

---

**Ready to test?** Run: `python test_deposit_live.py`
