# 📝 PhantomArbiter Master TODO

**Purpose**: This document serves as the central "Switchboard" for tracking active development, future roadmaps, and architectural pivots.

> **Newcomers**: Start with [STARTHERE.md](../STARTHERE.md) | **Agents**: Read [AGENT.md](./AGENT.md)

---

## 🚀 Active Sprint: "Institutional Realism" (Phase 4)

**Goal**: Eliminate the "Backtest Trap" by enforcing realistic execution costs and reducing latency to sub-60ms.

| Priority | Task | Status | Owner | Linked Doc |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Refactor Backtester** (Use `CapitalManager`) | ✅ Done | Shared | [EXECUTION.md](./EXECUTION.md) |
| **P0** | **Dynamic Slippage** (Volatility Scaling) | ✅ Done | CapMan | [RISK_MANAGEMENT.md](./RISK_MANAGEMENT.md) |
| **P0** | **Fast-Path** (Rust WSS Aggregator) | ✅ Done | Rust | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **P1** | **Race-to-First** (Deduplication) | ✅ Done | Rust | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **P1** | **Signal Scorer** (Move Logic to Rust) | ✅ Done | Rust | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **P1** | **Shadow Mode** (Paper/Live Parity) | ✅ Done | Python | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **P1** | **Whale-Pulse** (Confidence Boost) | 🏗️ Rust Done | Rust | [PHASE_WHALE_PULSE.md](./PHASE_WHALE_PULSE.md) |
| **P2** | **Full Backtest Suite** (Verify PnL Impact) | ⏳ Pending | QA | [TRADING_STRATEGIES.md](./TRADING_STRATEGIES.md) |

---

## 🗺️ Phase Roadmap

| Phase | Description | Status | Tracking Doc |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Foundation** (Scraper, Basic Arb) | ✅ Complete | [DATA_PIPELINE.md](./DATA_PIPELINE.md) |
| **Phase 2** | **Paper Trading** (Wallets, Simulation) | ✅ Complete | [EXECUTION.md](./EXECUTION.md) |
| **Phase 3** | **Refactor & Cleanup** (Inventory, SRP) | ✅ Complete | [INVENTORY.md](./INVENTORY.md) |
| **Phase 4** | **Optimization & Realism** (Rust, Latency) | 🟡 In Progress | [PHASE_INSTITUTIONAL.md](./PHASE_INSTITUTIONAL.md) |
| **Phase 5** | **Intelligence** (ML Advisor, Whale Watcher) | ⚪ Planned | `PHASE_INTELLIGENCE.md` (Todo) |

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
