# ADR-106: Trustless Bounty "Skimmer" Module

## Status
Proposed

## Context
The PhantomArbiter creates thousands of temporary TokenAccounts during its high-frequency trading operations. Over time, these accounts may be left empty (balance 0) but still holding SOL for rent exemption (approx. 0.002 SOL/account). Manually closing these is tedious. A "Skimmer" module can automate this cleanup. To enable this as a service for other users (or safely for the user themselves), we need a trustless mechanism where the Arbiter can propose the cleanup transaction but cannot steal the principal.

## Decision
We will implement a "Skimmer" module that:
1.  **Scans** a target wallet for "zombie" token accounts (0 balance, non-zero rent).
2.  **Proposes** a single atomic transaction containing:
    *   `N` instructions to `closeAccount` (destination: User's Wallet).
    *   `1` instruction to `transfer` 10% of the reclaimed rent (User's Wallet -> Arbiter Treasury).
3.  Uses an SPL Memo to notify the user of the opportunity.

## Safety & Trust
The safety of this system relies on the **Atomic Execution** property of Solana transactions.
*   The `closeAccount` instruction *must* send the rent to the account owner (the user).
*   The `transfer` instruction (the fee) is part of the same transaction.
*   If the user signs the transaction, they are guaranteed to receive 90% of the rent, and pay 10%.
*   If the `transfer` fails (e.g., user drains funds before execution), the entire transaction fails, preserving the state (accounts are not closed).
*   The Arbiter *cannot* change the destination of the `closeAccount` instruction without invalidating the transaction signature (or the user would see it in the simulation).

## Technical Implementation
*   **Language**: Python (utilizing `solders` and `solana.rpc.async_api`).
*   **Module**: `src/engine/skimmer_module.py`.
*   **Components**:
    *   `find_zombie_value`: RPC scanner.
    *   `build_trustless_reclaim_tx`: Transaction builder.
    *   `create_skim_memo`: Memo generator.

## Consequences
*   **Positive**: unlocks "stuck" liquidity for users; creates a new revenue stream for the Arbiter.
*   **Negative**: Users must sign the transaction (requires user interaction).
*   **Risks**: User might perceive the 10% fee as high, though it is "found money".
