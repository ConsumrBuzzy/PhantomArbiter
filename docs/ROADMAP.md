# Project Roadmap

**Version**: 3.0 (Hybrid)
**Status**: Transitioning to Micro-Services

## 🏛️ Functional Pillars

### 1. Ingestion (Data Pipeline)
*Focus: market data reliability, WSS latency, and scraper robustness.*

*   **P0: Unification (Phase 19)**
    *   [ ] Repair `src/scraper` broken imports.
    *   [ ] Wire WSS Aggregator directly to `HopGraphEngine`.
    *   [ ] Decouple `DataBroker` from legacy blocking calls.
*   **P1: Bridges**
    *   [ ] Stress test `orca_daemon.js` (IPC latency < 5ms).
    *   [ ] Implement `MeteoraBridge` health checks.
*   **Future (Micro-Service)**
    *   [ ] Build `apps/datafeed` gRPC server.

### 2. Intelligence (Brain & Rust)
*Focus: signal detection, graph algorithms, and risk analysis.*

*   **P1: Rust Acceleration (Phase 18)**
    *   [ ] **TA Engine**: Port `TechnicalAnalysis` (RSI/EMA) to `src_rust/src/technical.rs`.
    *   [ ] **PDA Cache**: Implement O(1) PDA lookup in `src_rust/src/pda.rs`.
    *   [ ] **Fee Engine**: Port congestion-aware fee estimation to Rust.
*   **P2: Risk Intelligence**
    *   [ ] Implement `get_risk_metrics()` (Drawdown, Sharpe) in CapitalManager.
    *   [ ] "Whale Pulse": Monitor smart money inflow (Phase 5A).

### 3. Execution (Transaction Layer)
*Focus: transaction building, signing, and Jito/MEV bundles.*

*   **P0: Battle Testing (Phase 17)**
    *   [ ] **Ghost Execution**: Verify 4-leg Jito bundle integrity (`scripts/ghost_execute.py`).
    *   [ ] **Soak Test**: Run Paper Mode for 24h with >99% uptime.
    *   [ ] **Scavenger**: Validate `FailureTracker` spike detection.
*   **Future (Micro-Service)**
    *   [ ] Build `apps/execution` gRPC server.
    *   [ ] Implement independent Nonce Manager.

### 4. UI (Galaxy & Dashboard)
*Focus: observability and real-time visualization.*

*   **P1: Dashboard Overhaul (Phase 6)**
    *   [ ] Expose Rust FFI performance metrics to Galaxy.
    *   [ ] Visualize "RPC Race" stats (Helius vs Triton wins).
    *   [ ] Display "Signal Pipeline" rejection rates.
*   **P2: Galaxy Features**
    *   [ ] 3D visualization of "Hot Path" arbitrage cycles.

---

## 📅 Milestone Status Board

| Milestone | Status | Description |
|-----------|--------|-------------|
| **M1: The Monolith** | ✅ Done | Initial Python V2 engine (Legacy). |
| **M2: Hybrid Core** | 🟡 Active | Node.js Bridges + Python Core + Galaxy UI. |
| **M3: Rust Turbo** | 📋 Backlog | Critical path logic moved to Rust (Phase 18). |
| **M4: Service Mesh** | 📋 Backlog | Full gRPC separation of DataFeed/Execution. |
