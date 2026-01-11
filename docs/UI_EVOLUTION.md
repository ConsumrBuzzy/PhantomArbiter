# UI Evolution & Direction

**Status**: Transitioning from V2 (Monolith) to V4 (Service Mesh).

---

## 🕰️ Past: V1/V2 The Monolith
*The "Terminal Era".*

In the early stages, PhantomArbiter was a single Python process running inside a terminal multiplexer (tmux/screen).

*   **Technology**: `rich` library (Console), `curses`.
*   **Architecture**: UI logic ran in the **same thread** as the trading loop.
*   **Issues**: Rendering table updates (e.g., `live_dashboard.py`) blocked the Arbitrage Engine for 50-100ms, causing missed slots.
*   **Legacy Code**: `src/legacy/arbiter/monitoring/live_dashboard.py`

---

## 🧭 Current: V3 Hybrid (Galaxy)
*The "Dashboard Server".*

We currently utilize a dedicated "Dashboard Server" thread/process that serves a web-based visualization.

*   **Technology**: Python `FastAPI` + `Three.js` (Galaxy Frontend).
*   **Architecture**: 
    *   `src/interface/dashboard_server.py` runs an HTTP server on Port 8001.
    *   The Core Engine pushes updates via internal queues (`multiprocessing.Queue`).
*   **Status**: Active / Production.
*   **Pain Points**: 
    *   Still shares Python GIL in some modes.
    *   "Galaxy" 3D visualization is resource-heavy on the host machine if running locally.

---

## 🔭 Future: V4 Decoupled Service Mesh
*The "Headless Core".*

The roadmap (P0 Architecture Clean-up) dictates a complete separation of concerns. The Trading Engine should run "Headless" on a VPS, while the UI runs on a user's local machine or Edge CDN.

*   **Technology**: 
    *   **Backend**: gRPC Streams (`apps/datafeed`).
    *   **Frontend**: Next.js / React (hosted on Vercel/Netlify).
    *   **Transport**: Shared Memory (MMAP) on localhost, gRPC over the wire.
*   **Architecture**:
    1.  **Core** writes state to `shm` files (Zero-Copy).
    2.  **Sidecar (DataFeed)** reads `shm` and streams via WebSocket/gRPC.
    3.  **UI** connects to Sidecar. 
    *   *Zero impact* on Trading Loop latency.
*   **Action Plan**:
    *   [ ] Decompose `SyncExecution` dependencies on `dashboard_server`.
    *   [ ] Build `apps/datafeed` Service.
