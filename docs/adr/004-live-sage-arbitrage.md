# ADR-004: Transition to Live SAGE Arbitrage (Volume Mode)

**Status:** Proposed (Pending Simulation Success)
**Date:** 2026-02-15
**Context:** Connectivity confirmed via Ironforge. Protocol is SVM (z.ink). Capital is $14.

## Decision
Move to live execution only when the simulation proves a Net Profit + Airdrop Value > Gas Costs.

## Rules of Engagement (Volume Mode)
1.  **Objective**: Maximize "On-Chain Activity" (zXP) for Airdrop Weighting.
2.  **Capital**: $14 (0.168 SOL). Total loss acceptable; private key compromise is not.
3.  **Infrastructure**:
    -   **RPC**: Ironforge Dedicated Pool (SVM).
    -   **Failover**: Automated rotation between primary/secondary keys.
    -   **Security**: Keys stored in `.env`, never committed.
4.  **Limits**:
    -   **Stop Loss**: If balance < 0.15 SOL.
    -   **Rate Limit**: Resume on 429 errors after backoff; failover if persistent.
    -   **Throughput**: Target > 100 tx/hour.

## Consequences
-   **Positive**: High zXP yield, potential for leaderboard placement.
-   **Negative**: High frequency trading risks slippage and accumulated gas costs (though negligible on z.ink). Memory management becomes critical for 24h runs.

## Verification
-   **Success**: > 95% tx success rate over 2 hours.
-   **Validation**: Check `api.z.ink` for XP increases.
