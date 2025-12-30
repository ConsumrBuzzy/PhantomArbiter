
# 🏛️ Phase 4: Institutional Realism - Master Plan

**Objective**: Eliminate the delta between Simulation and Reality.
**Owner**: AI Agent (Optimization Specialist)
**Status**: 🟡 In Progress

---

## 🎯 The "Realism Gap" Problem

Most bots fail because they optimize for a fantasy.

- **Fantasy**: Instant fills, zero slippage, 100% liqudity access.
- **Reality**: 200ms+ network lag, MEV sandwich attacks, failed transactions, variable gas markets.

**Phase 4 Goal**: Build a bot that *survives* Reality, rather than just profiting in Fantasy.

---

## 🛠️ Work Breakdown Structure (WBS)

### 1. ⚡ Network Latency (The "Fast-Path")

* [x] **Rust WebSocket Aggregator**: Parallel connections to Helius, QuickNode, Triton.
- [x] **Race-to-First Deduplication**: Process the *first* packet, drop the rest.
- [ ] **Signal Scoring (Rust)**: Move logic from Python to Rust.
  - *Input*: Raw Price Updates (Tickers).
  - *Logic*: `Spread > Fee + Slippage + MinProfit`.
  - *Output*: Validated Signals only.

### 2. 🛡️ Execution Fidelity (The "Truth-Path")

* [x] **Dynamic Slippage Model**: `Slippage = Base + (Vol * Impact)`.
- [x] **Volatility Penalty**: Forbid entry if standard deviation > threshold.
- [ ] **Shadow Mode**:
  - Run `Live` and `Paper` engines on the *exact same signals* in parallel.
  - Log `(Live_Entry - Paper_Entry)` deltas.
  - Auto-adjust `Paper` parameters until delta < 1%.

### 3. 🧠 Smart Valuation (The "Alpha-Path")

* [ ] **Whale Watcher Integration**:
  - Track "Smart Money" wallet accumulation.
  - Boost Signal Confidence if Top 10 Holders are buying.
- [ ] **MEV Protection**:
  - Use JITO bundles for ALL swaps (Live).
  - Simulate JITO "Tips" in Paper mode (Cost of Business).

---

## 🧪 Verification & Acceptance Criteria

### A. The "Pulse" Test

* **Command**: `main.py pulse`
- **Criteria**:
    1. Logs show proper "Race" stats (e.g., "Helius won 40%, Triton 60%").
    2. Paper Trades show realistic costs (Gas + Slippage + Jito Tip).
    3. No crashes over 24 hours of uptime.

### B. The "Backtest" Test

* **Command**: `scripts/run_backtest.py`
- **Criteria**:
    1. PnL graph must NOT look like a straight line up.
    2. Drawdowns must align with known market dumps (e.g., SOL crashes).
    3. "Win Rate" should drop significantly compared to naive backtests (from 80% -> 55%). *This is good; it means we are filtering noise.*

---

## 📅 Execution Roadmap (Next Steps)

1. **Step 1**: Implement `SignalScorer` in Rust (`src_rust/src/scorer.rs`).
2. **Step 2**: Expose Scorer to Python via PyO3.
3. **Step 3**: Update `Director.py` to use `FastClient` with Rust Scoring.
4. **Step 4**: Build `ShadowMode` analyzer script.

---

**"If it works in Backtest but fails in Live, the Backtest was a lie."**
