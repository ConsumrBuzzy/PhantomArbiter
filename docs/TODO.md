# 📝 PhantomArbiter Master TODO

**Purpose**: This document serves as the central "Switchboard" for tracking active development, future roadmaps, and architectural pivots.

> **Newcomers**: Start with [STARTHERE.md](../STARTHERE.md) | **Agents**: Read [AGENT.md](./AGENT.md)

---

## 🚀 Active Sprint: "Narrow Path" (Phase 8)

**Goal**: Pivot to Long-Tail Multi-Hop Arbitrage via Rust-powered graph pathfinding.

| Priority | Task | Status | Owner | Linked Doc |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Slim-Down**: Disable WhaleWatcher & ScoutAgent | 🟡 Active | Director | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **P0** | **graph.rs**: Pool Matrix Implementation | 📋 Plan | Rust | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **P0** | **cycle_finder.rs**: Bellman-Ford Cycle Detection | 📋 Plan | Rust | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **P1** | **HopGraphEngine**: Python Integration | 📋 Plan | Arbiter | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **P1** | **AtomicExecutor**: 4-Leg Jito Bundle Support | 📋 Plan | Executor | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |
| **P2** | **Dashboard**: Path Efficiency Metrics | ⚪ Planned | UI | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |

---

## 🗺️ Phase Roadmap

| Phase | Description | Status | Tracking Doc |
| :--- | :--- | :--- | :--- |
| **Phase 4** | **Optimization & Realism** (Rust, Latency) | ✅ Complete | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **Phase 5** | **Intelligence** (ML Advisor, Whale Watcher) | ⏸️ Paused | `PHASE_INTELLIGENCE.md` |
| **Phase 6** | **Universal Discovery** (Lifecycle Arbitrage) | ⏸️ Paused | [PHASE_6_PLAN.md](./PHASE_6_UNIVERSAL_DISCOVERY.md) |
| **Phase 7** | **PnL Audit & Risk Hardening** | ⚪ Upcoming | `PHASE_7_AUDIT.md` |
| **Phase 8** | **🆕 Narrow Path** (Multi-Hop Token Hopping) | 🟡 Active | [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) |

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
