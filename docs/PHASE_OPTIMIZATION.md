
# ⚡ Phase 4: Optimization & Realism

**Objective**: Transition PhantomArbiter from a standard Python bot to a Hybrid Rust/Python High-Frequency OS.
**Key Metrics**:

- Signal-to-Execution Latency: `< 60ms`
- Slippage Accuracy: `> 95%` vs Mainnet
- CPU Idle Time: `> 80%` (Offloading to Rust)

---

## 🛠️ Architecture Changes

### 1. The "Fast-Path" (Completed)

* **Component**: `wss_aggregator.rs` + `fast_client.py`
- **Description**:
  - Moved WebSocket handling to Rust (`tokio-tungstenite`).
  - Implemented "Race-to-First" deduplication to pick the fastest RPC packet.
  - Python now just "sips" verified unique events via FFI.
- **Benefit**: Eliminates Python GIL blocking on network I/O; massive latency reduction.

### 2. Institutional Risk (Completed)

* **Component**: `CapitalManager` (Shared)
- **Description**:
  - **Dynamic Slippage**: `Base * Volatility_Multiplier`.
  - **Volatility Penalty**: Backtester now intentionally fills at worse prices during high-vol regimes.
- **Benefit**: Prevents "Paper Tiger" syndrome where backtests look good but live trading bleeds money.

### 3. Signal Scoring (Pending)

* **Concept**: Move the decision logic ("Is this separate?") from `Director.py` to `Rust`.
- **Plan**:
  - Rust receives Price Update -> Calculates Spread -> Checks Thresholds.
  - If `Profit > Min`: Send `Signal` to Python.
  - If `Profit < Min`: Drop silently.
- **Impact**: Python ignores 99% of market noise, focusing only on actionable trades.

---

## 📉 Latency Benchmarks

| Metric | Legacy (Pure Python) | Hybrid (Rust Fast-Path) | Goal |
| :--- | :--- | :--- | :--- |
| **Ingest** | 120ms | ~15ms | < 10ms |
| **Parse** | 40ms | < 1ms | < 1ms |
| **Logic** | 35ms | 35ms (Python) | < 5ms (Rust) |
| **Total** | **~195ms** | **~50ms** | **< 20ms** |

---

## 📝 Implementation Notes

- **Rust Extension**: Requires `maturin develop` to build.
- **Dashboard**: `monitor_race.py` visualizes the RPC wins.
