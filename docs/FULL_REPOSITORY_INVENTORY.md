# Master Systems Directory: PhantomArbiter

This directory establishes the definitive technical source of truth for the PhantomArbiter multi-engine ecosystem. It maps the systemic intersections between high-performance Rust execution, Python strategy intelligence, and real-time observability.

## 🧠 The Engine Matrix (Core Strategy Layer)

The system operates on a multi-engine paradigm, standardizing execution via `src/engines/base_engine.py`.

| Engine | Logic Source | Primary Strategy | Target |
| :--- | :--- | :--- | :--- |
| **Arb** | `src/engines/arb/` | Triangular Arbitrage | Core SOL/USDC/JUP liquidity pools. |
| **Scalp** | `src/engines/scalp/` | Meme Coin Sniping | Sentiment-driven momentum on new pods. |
| **Galaxy (SAGE)** | `apps/galaxy/` | Resource Arbitrage | Star Atlas R4 and SDU spreads on z.ink L1. |
| **Funding** | `src/engines/funding/` | Funding Rate Arb | Drift Protocol vs. Spot price variance. |
| **LST Depeg** | `src/engines/lst_depeg/` | Liquid Staking Arb | mSOL/JitoSOL depeg recovery cycles. |

## 🐋 Asymmetric Intelligence (Whale Watching)

"Whale Watching" is implemented as a leading indicator system that identifies price-elastic events before they hit the ticker.

- **Whale Watcher Agent**: `src/core/scout/agents/whale_watcher_agent.py`
    - Monitors "Alpha Wallets" for shadow-tracking and copy-trading signals.
- **Rust Whiff Detection**: `src_rust/src/log_parser.rs`
    - High-fidelity log parsing for large-scale CCTP/Wormhole mints (Inflows).
    - Real-time liquidation detection (Marginfi/Solend/Kamino).
- **Sentiment Engine**: `src/engines/scalp/sentiment.py`
    - Aggregates on-chain volume and whale-pulse signals into a 0-100 score.

## 🌉 The Coinbase Bridge (Liquidity & Discovery)

- **Driver**: `src/drivers/coinbase_driver.py`
- **Auth**: Modern CDP (Coinbase Cloud) JWT-based authentication.
- **Functionality**:
    - **Price Discovery**: Cross-exchange price parity audits via CCXT `fetch_ticker`.
    - **Liquidity Bridge**: Automated Solana-network USDC withdrawals from CEX to Phantom.
    - **Safety Gates**: Hard-coded Network Guards (Solana only) and Dust Floors.

## 📊 Dashboard & Observability (The Visual Ecosystem)

The dashboard is an extensive, multi-page web application featuring windowed components and 3D spatial visualizations.

### 🖼️ Architecture & Navigation
- **Kernel Server**: `src/interface/dashboard_server.py` (Bidirectional WS Kernel).
- **Heartbeat Engine**: `src/interface/heartbeat_collector.py` (1Hz System Snapshot).
- **Core Router**: `frontend/js/core/router.js` (Hash-based Hub-and-Spoke navigation).
- **Layout Engine**: `frontend/js/components/layout-manager.js` (Window visibility & persistence).
- **View Manager**: `frontend/js/core/view-manager.js` (Dynamic DOM orchestration).

### 🖥️ Main Dashboard (V23 "Frontier")
The primary interface for trading operations.
- **Base Styles**: `frontend/css/main.css`, `frontend/css/variables.css` (Neon/Dark Cyberpunk).
- **Component Styles**: `frontend/css/components/` (Individual .css files per module).
- **Console Heartbeat**: Found in `frontend/js/core/websocket.js` (Legacy debug logs) and `app.js` (Price flash and status transitions).

### 🌌 Galaxy Dashboard (V2 "Nebula")
Located in `apps/galaxy/frontend/`, focuses on 3D spatial market mapping.
- **HUD Styles**: `apps/galaxy/frontend/hud.css` (Holographic/Sci-fi aesthetics).
- **3D Engine**: `GalaxyScene.js` (Three.js with `UnrealBloomPass` and `EffectComposer`).
- **Managers**: `SceneManager.js`, `FleetManager.js`, `StarSystemManager.js` (Abstracted Three.js orchestration).

### ⌨️ TUI Archeology (Terminal UI Attempts)
PhantomArbiter features a rich history of CLI dashboards for headless monitoring:
1. **Textual App**: `src/dashboard/tui_app.py` (The official Python TUI with grid layout).
2. **Rich Pulse Dashboard**: `src/arbiter/ui/pulsed_dashboard.py` (Rich.live layout with fragmented data slots).
3. **ANSI Core**: `src/shared/ui/base_console_ui.py` (Low-level ANSI escape codes and BOX-drawing character primitives).
4. **Rich Panels**: `src/shared/ui/rich_panel.py` (DNEMDashboard class for unified engine reporting).

### � Console Heartbeat & Logging Styles
- **Terminal (Python)**: `src/shared/system/logging.py` uses `RichHandler` with `SOURCE_ICONS` (e.g., 🐋 for Orca, 🧠 for ML). Features markup-enabled logging.
- **Browser (JS)**: The `Terminal.js` component simulates terminal output with CSS variables (`--neon-blue`, `--neon-red`, etc.). Status bar `engineMode` uses reactive styling (linked, offline, error).

## 🔍 Market Discovery Methods (Registry)
...

PhantomArbiter maintains 5+ high-fidelity market discovery sensors:

1.  **Jupiter Hub**: `src/shared/feeds/jupiter_feed.py` (Aggregator Price Discovery).
2.  **Raydium/Orca/Meteora**: `src/shared/feeds/raydium_feed.py` (Direct Program Log Parsing).
3.  **Tensor Janitor**: `src/shared/infrastructure/tensor_client.py` (NFT Rent-Reclaim Arb).
4.  **Star Atlas Galaxy**: `src/shared/infrastructure/star_atlas_client.py` (z.ink L1 GraphQL).
5.  **Drift Protocol**: `src/shared/feeds/drift_funding.py` (Perp Funding Rates).

---
**Technical Note**: All modules adhere to the **Hybrid Bridge** architecture: Data Ingress (Rust) -> Strategy Logic (Python) -> Atomic Execution (Rust).
