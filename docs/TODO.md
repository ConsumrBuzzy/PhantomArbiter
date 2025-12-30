# 📝 PhantomArbiter Master TODO

**Purpose**: This document serves as the central "Switchboard" for tracking active development, future roadmaps, and architectural pivots.

> **Newcomers**: Start with [STARTHERE.md](../STARTHERE.md) | **Agents**: Read [AGENT.md](./AGENT.md)

---

## 🚀 Active Sprint: "Universal Discovery" (Phase 6)

**Goal**: Capture the "Graduation Gap" alpha via hierarchical lifecycle tracking.

| Priority | Task | Status | Owner | Linked Doc |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **PumpFunMonitor** (6EF8... Monitoring) | 📋 Plan | Rust/Py | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **P0** | **RaydiumStandardBridge** (675k... Initialization) | 📋 Plan | Python | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **P1** | **Hierarchical Scout Logic** (Graduation Alerts) | 📋 Plan | Scout | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **P1** | **Bonding Curve Math** (Metadata Schema) | ✅ Done | Rust | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **P2** | **Full PnL Auditor** (Shadow vs. Live) | ⚪ Planned | QA | `PHASE_7_AUDIT.md` |

---

## 🗺️ Phase Roadmap

| Phase | Description | Status | Tracking Doc |
| :--- | :--- | :--- | :--- |
| **Phase 4** | **Optimization & Realism** (Rust, Latency) | ✅ Complete | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **Phase 5** | **Intelligence** (ML Advisor, Whale Watcher) | ⚪ Planned | `PHASE_INTELLIGENCE.md` |
| **Phase 6** | **Universal Discovery** (Lifecycle Arbitrage) | 🟡 Active | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **Phase 7** | **PnL Audit & Risk Hardening** | ⚪ Upcoming | `PHASE_7_AUDIT.md` |

---

## 💡 Idea Backlog (The Icebox)

* [ ] **"Shadow Mode"**: Run Live & Paper strategies side-by-side on the same signals to compare execution quality explicitly.
* [ ] **"Replay Buffer"**: Save raw WSS logs to disk to "replay" a market day exactly as it happened for debugging.
* [ ] **"Landlord Agent"**: A devoted agent that manages rent/costs of the bot infrastructure itself (managing SOL gas, RPC accounts).
* [ ] **"Sentiment Engine"**: Ingest Twitter/Discord sentiment to weigh the `SignalScanner` confidence.

---

## 📂 Documentation Consistency Checklist

*When ending a session, ensure these are updated:*

1. [ ] **`INVENTORY.md`**: Did you create new files?
2. [ ] **`TODO.md`**: Did you finish a P0 item?
3. [ ] **[Phase_Doc]**: Did you add technical details to the active phase doc?
