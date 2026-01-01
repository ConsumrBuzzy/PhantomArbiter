# 📝 PhantomArbiter Master TODO

**Purpose**: This document serves as the central "Switchboard" for tracking active development, future roadmaps, and architectural pivots.

> **Newcomers**: Start with [STARTHERE.md](../STARTHERE.md) | **Agents**: Read [AGENT.md](./AGENT.md)

---

## 🚀 Active Sprint: "The Great Unification" (Phase 19)

**Goal**: Unify the fractured codebase, repair legacy scraper components, and wire the Rust WSS Aggregator to the Arbitrage Engine.

| Priority | Task | Status | Owner | Linked Doc |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Rehabilitation**: Fix broken imports in `src/scraper` | 🚧 In Progress | Core | [PHASE_REHABILITATION.md](../PHASE_REHABILITATION.md) |
| **P0** | **Cleanup**: Remove ghost code in `src/scalper` | 📋 Plan | Core | [PHASE_REHABILITATION.md](../PHASE_REHABILITATION.md) |
| **P0** | **Wiring**: Connect WSS to HopGraphEngine | 🚧 In Progress | Core | [PHASE_UNIFICATION.md](../PHASE_UNIFICATION.md) |
| **P1** | **Battle Test**: Resume soak testing (Phase 17) | ⏸️ Paused | Test | [PHASE_17_BATTLE_TEST.md](./PHASE_17_BATTLE_TEST.md) |

---

## ✅ Recently Completed

### Phase 16: Scavenger Intelligence (2025-12-31)

- [x] **FailureTracker**: Spike/Recoil detection in `log_harvester.py`
- [x] **BridgePod**: Circle CCTP & Wormhole monitoring
- [x] **Dashboard**: Hot Pools and Institutional Flow panels
- [x] **Integration Tests**: `tests/test_multi_hop.py`
- [x] **Benchmarks**: `scripts/bench_multiverse.py`

### Phase 8-15: Narrow Path Infrastructure

- [x] **graph.rs**: Pool Matrix Implementation
- [x] **cycle_finder.rs**: Bellman-Ford Cycle Detection
- [x] **multiverse.rs**: 2-5 Hop Scanner
- [x] **HopGraphEngine**: Python Integration
- [x] **ExecutionPod**: Paper/Live execution modes
- [x] **JupiterClient**: DEX quote routing
- [x] **MultiHopBuilder**: Jito bundle construction

---

## 🗺️ Phase Roadmap

| Phase | Description | Status | Tracking Doc |
| :--- | :--- | :--- | :--- |
| **Phase 4** | **Optimization & Realism** (Rust, Latency) | ✅ Complete | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **Phase 5** | **Intelligence** (ML Advisor) | ⏸️ Paused | `PHASE_INTELLIGENCE.md` |
| **Phase 5A** | **Whale Pulse** (Smart Money) | ⏸️ Paused | [PHASE_WHALE_PULSE.md](./PHASE_WHALE_PULSE.md) |
| **Phase 5C** | **Auto-Slippage** (Drift Calibration) | ✅ Complete | [PHASE_AUTO_SLIPPAGE.md](./PHASE_AUTO_SLIPPAGE.md) |
| **Phase 5D** | **Congestion Multiplier** (Gas Logic) | 📋 Plan | [PHASE_CONGESTION_MULTIPLIER.md](./PHASE_CONGESTION_MULTIPLIER.md) |
| **Phase 6** | **Dashboard Overhaul** (Observability) | 📋 Plan | [PHASE_DASHBOARD_OVERHAUL.md](./PHASE_DASHBOARD_OVERHAUL.md) |
| **Phase 7** | **PnL Audit & Risk Hardening** | ✅ Complete | `PHASE_7_AUDIT.md` |
| **Phase 8-15** | **Narrow Path** (Multi-Hop Token Hopping) | ✅ Complete | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **Phase 16** | **Scavenger Intelligence** (FailureTracker, BridgePod) | ✅ Complete | `PHASE_16_SCAVENGER.md` |
| **Phase 17** | **Battle Test** (Ghost Execution, Soak Testing) | 🟡 Active | [PHASE_17_BATTLE_TEST.md](./PHASE_17_BATTLE_TEST.md) |
| **Phase 18** | **🆕 Rust Acceleration** (TA Engine, PDA Cache, Fees) | 📋 Plan | [PHASE_RUST_ACCELERATION.md](./PHASE_RUST_ACCELERATION.md) |
| **Phase 19** | **Refactor & Unify** (DataBroker, Scraper repair) | 🟡 Active | [PHASE_UNIFICATION.md](../PHASE_UNIFICATION.md) |
| **Phase 20** | **Nomad Persistence** (Auto-Hydration) | ✅ Complete | [PHASE_20_21_NOMAD_PRIVACY.md](./PHASE_20_21_NOMAD_PRIVACY.md) |
| **Phase 21** | **Privacy Shield** (Ephemeral Wallets) | ✅ Complete | [PHASE_20_21_NOMAD_PRIVACY.md](./PHASE_20_21_NOMAD_PRIVACY.md) |
| **Phase 22** | **Token Memory** (Metadata Persistence) | ✅ Complete | [PHASE_22_23_PERSISTENCE.md](./PHASE_22_23_PERSISTENCE.md) |
| **Phase 23** | **Market Map** (Pool Persistence) | ✅ Complete | [PHASE_22_23_PERSISTENCE.md](./PHASE_22_23_PERSISTENCE.md) |

---

## 💡 Idea Backlog (The Icebox)

- [x] **"Shadow Mode"**: Run Live & Paper strategies side-by-side on the same signals.
- [ ] **"Replay Buffer"**: Save raw WSS logs to disk for market replay debugging.
- [ ] **"Landlord Agent"**: Manage SOL gas and RPC costs automatically.
- [ ] **"Sentiment Engine"**: Ingest Twitter/Discord sentiment for signal weighting.
- [ ] **"PythPod"**: Real-time oracle price feeds for institutional-grade pricing.

---

## 📂 Documentation Consistency Checklist

*When ending a session, ensure these are updated:*

1. [ ] **`INVENTORY.md`**: Did you create new files?
2. [ ] **`TODO.md`**: Did you finish a P0 item?
3. [ ] **[Phase_Doc]**: Did you add technical details to the active phase doc?
