# Phase 17: Ghost Execution & Battle Testing

> **Status**: 🟡 Active | **Owner**: @Executor | **Start Date**: 2025-12-31

## Overview

With the "Narrow Path" infrastructure fully wired (Phase 16), we now move into **Battle Testing**. This phase focuses on validating that the entire pipeline—from signal detection to Jito bundle submission—works under realistic conditions.

The aim is to run "Ghost Executions" (dry runs) and stress test the system before enabling live trading.

---

## P0: Ghost Execution (Dry Run)

**Objective**: Verify that the `ExecutionPod` correctly formats 4-leg Jito bundles without submitting them.

| Task | Description | Status |
|------|-------------|--------|
| Bundle Format Test | Build a 4-leg bundle, serialize, and verify structure | 📋 Plan |
| Jupiter Quote Chain | Validate that `MultiHopQuoteBuilder` chains quotes correctly | 📋 Plan |
| Compute Budget Calc | Ensure CU allocation scales with hop count | 📋 Plan |
| Tip Calculation | Validate congestion-aware tip adjustment | 📋 Plan |
| Transaction Size | Confirm bundle fits within 1232-byte limit | 📋 Plan |

### Ghost Execution Script

```bash
# Run ghost execution test
python scripts/ghost_execute.py --hops 4 --dry-run
```

---

## P1: Scavenger Integration Testing

**Objective**: Validate that `FailureTracker` and `BridgePod` signals correctly trigger ExecutionPod warm-up.

| Task | Description | Status |
|------|-------------|--------|
| Failure Spike Simulation | Mock 5+ failures in 30s, verify SPIKE signal | 📋 Plan |
| Recoil Detection | Mock silence after spike, verify RECOIL signal | 📋 Plan |
| Bridge Inflow Simulation | Mock $500k CCTP mint, verify LIQUIDITY_INFLOW | 📋 Plan |
| Dashboard Verification | Confirm Hot Pools and Flow panels update | 📋 Plan |

---

## P2: Paper Mode 24-Hour Soak

**Objective**: Run the full system in Paper Mode for 24 hours and collect metrics.

| Metric | Target |
|--------|--------|
| Cycles Detected | > 100 |
| Signals Processed | > 500 |
| False Positives | < 10% |
| System Uptime | 99% |
| Memory Usage | Stable (no leaks) |

### Soak Test Command

```bash
# Start paper mode soak test
HOP_ENGINE_ENABLED=true python main.py --mode paper
```

---

## P3: Live Activation Checklist

Before enabling `ExecutionMode.LIVE`, complete:

- [ ] Ghost Execution passes all tests
- [ ] Paper Mode soak confirms no false positives
- [ ] Jito tip account rotation verified
- [ ] Private key securely loaded from environment
- [ ] Kill switch tested (emergency halt)
- [ ] Capital partitioning reviewed (max risk per trade)

---

## Architecture Reference

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  LogHarvester │────▶│ FailureTracker│────▶│   SignalBus   │
│  (WSS Logs)   │     │   BridgePod   │     │               │
└───────────────┘     └───────────────┘     └───────┬───────┘
                                                    │
                                                    ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│    HopPod     │────▶│  ExecutionPod │────▶│ JupiterClient │
│  (Multiverse) │     │  (Striker)    │     │ (DEX Routes)  │
└───────────────┘     └───────────────┘     └───────────────┘
                              │
                              ▼
                      ┌───────────────┐
                      │  Jito Bundle  │
                      │  (Atomic Tx)  │
                      └───────────────┘
```

---

## Success Criteria

| Criteria | Threshold |
|----------|-----------|
| Bundle Build Success Rate | 100% |
| Signal Latency (detect → queue) | < 50ms |
| Paper Trade Profitability | > 0 (net positive) |
| System Stability | No crashes in 24h |

---

## Related Documents

- [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) - Original Phase 8 plan
- [PHASE_16_SCAVENGER.md](./PHASE_16_SCAVENGER.md) - FailureTracker & BridgePod
- [TODO.md](./TODO.md) - Master task tracker
