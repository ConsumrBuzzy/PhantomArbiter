# ADR-0008: Dedicated Engine Vaults

**Status:** Proposed
**Date:** 2026-01-15
**Context:** The current "Unified Vault" system aggregates all funds into one global view. However, individual Engines (Drift, Scalp, Funding) need to track their *own* allocated capital ("Dedicated Vaults") to calculate ROI, isolate risk, and prevent cross-contamination of funds. The user has specifically requested that "Dedicated Engine Vaults" be wired correctly and displayed in the Inventory and on Engine Pages.

## Problem
1. **Global Mixing:** All funds currently show as one big pool. It's unclear how much is allocated to "Scalp" vs "Drift".
2. **PnL Ambiguity:** If the global balance goes up, we don't know which engine caused it.
3. **Risk Control:** Without isolation, a malfunctioning engine could theoretically drain funds intended for another strategy (though on-chain sub-accounts mitigate this somewhat).
4. **UI Disconnect:** The "Inventory" shows assets, but not "Strategy Allocations".

## Solutions Considered

### Option 1: Virtual Partitioning (Tagging)
- **Concept:** Keep one wallet, but "tag" amounts in the database/memory as belonging to Engine X.
- **Pros:** Simple on-chain (one wallet).
- **Cons:** Complex off-chain bookkeeping. Synchronization issues if external trades happen. Hard to enforce limits.

### Option 2: On-Chain Sub-Accounts (Recommended for Drift)
- **Concept:** Use Drift Protocol's Sub-Account feature (0, 1, 2...).
- **Mapping:**
  - `Main Account (0)`: Universal Vault / Aggregator
  - `Sub-Account (1)`: Delta Neutral Engine
  - `Sub-Account (2)`: Scalper Engine
- **Pros:** True on-chain isolation. PnL is automatically separated by the protocol.
- **Cons:** Managing valid sub-account IDs. managing transfers between sub-accounts (requires precise logic).

### Option 3: Hybrid (Virtual + On-Chain)
- **Concept:** Use On-Chain Sub-Accounts where possible (Drift), and Virtual Partitioning for simple hot-wallet strategies (Raydium Scalping).
- **Pros:** Flexible.
- **Cons:** Inconsistent implementation across engines.

## Decision: Hybrid Approach with "Managed Vault" Interface
We will implement a Hybrid approach where the `VaultManager` tracks "Allocations".

1. **Drift Engine**: Uses **Drift Sub-Account ID**.
   - The "Dedicated Vault" is strictly the state of that Sub-Account.
   - UI shows: `Collateral`, `PnL`, `Positions` for that Sub-Account.

2. **Scalp Engine (Hot Wallet)**: Uses **Virtual Allocation**.
   - The user "Deposits" SOL into the Scalp Engine (virtually).
   - The Engine tracks this `allocated_balance`.
   - The System ensures `live_wallet_balance >= sum(virtual_allocations)`.

3. **Inventory UI Update**:
   - Split Inventory into "Unallocated (Idle)" and "Deployed (Strategies)".
   - Show a breakdown of Deployed funds by Engine.

## Implementation Steps

### 1. Backend: `EngineVault` Class
Extend the current `Vault` concept to be engine-aware.
```python
class EngineVault:
    def __init__(self, engine_id: str):
        self.engine_id = engine_id
        self.type = "DRIFT_SUBACCOUNT" if is_drift else "VIRTUAL"
        self.lock_balance() # ...
```

### 2. Drift Integration
- Update `DriftAdapter` to support switching sub-accounts.
- `DeltaNeutralEngine` configuration must include `sub_account_id`.
- Default: `sub_account_id=0` (Main).

### 3. Frontend: Dedicated Vault Component
- Create `<engine-vault-card>` web component.
- Display:
  - `Allocated Capital`
  - `Available for Trades`
  - `Realized PnL`
  - `Unrealized PnL`
  - Actions: `Deposit`, `Withdraw` (Transfers to/from Main/Idle)

### 4. Inventory Widget Update
- Add "Strategy Allocation" pie chart or list.

## Consequences
- **Positive:** Clear separation of concerns. Accurate PnL attribution per engine. Risk isolation.
- **Negative:** Increased complexity in `VaultManager`. Requires users to perform "internal transfers" (Deposit/Withdraw) to fund engines.
