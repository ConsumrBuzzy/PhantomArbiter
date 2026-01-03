# Component Map

This document tracks the status and responsibility of every major component in the PhantomArbiter ecosystem.

## 🟢 Active Components

| Component | Location | Type | Responsibility |
|-----------|----------|------|----------------|
| **Unified Director** | `src/director.py` | Core | System lifecycle, orchestration, and graceful shutdown. |
| **Data Broker** | `src/core/data_broker.py` | Core | Central data aggregation, caching, and distribution. |
| **Arbiter Engine** | `src/arbiter/` | Core | Spatial/Triangular arbitrage logic and graph traversal. |
| **Galaxy** | `apps/galaxy/` | Service | Real-time 3D visualization and dashboard hosting. |
| **Orca Bridge** | `bridges/orca_daemon.js` | Bridge | Interface to Orca Whirlpools SDK (Node.js). |
| **Raydium Bridge** | `bridges/raydium_daemon.js` | Bridge | Interface to Raydium CLMM/CPMM SDK (Node.js). |
| **Meteora Bridge** | `bridges/meteora_bridge.js` | Bridge | Interface to Meteora DLMM SDK (Node.js). |
| **Telegram Bot** | `src/shared/notification/` | Module | User notifications and simple command control. |

## 🟡 Incubating Components (Next Gen)

| Component | Location | Type | Status | Goal |
|-----------|----------|------|--------|------|
| **DataFeed Service** | `apps/datafeed/` | Micro-Service | 🚧 Prototype | Replace internal WSS logic with a dedicated gRPC ingress stream. |
| **Execution Service** | `apps/execution/` | Micro-Service | 🚧 Prototype | Replace internal transaction handling with a robust, nonce-managing signing service. |
| **Rust Graph** | `src_rust/` | Module | 🚧 Experimental | Replace Python NetworkX graph with Rust-based PetGraph for speed. |

## 🟣 Deprecated / Legacy

| Component | Location | Replacement | Note |
|-----------|----------|-------------|------|
| **Pulse** | `main.py pulse` | **Galaxy** | Legacy CLI dashboard. Still functional but not maintained. |
| **Old Scraper** | `src/scraper/legacy` | **Scout Agent** | Old single-file scrapers replaced by modular agents. |
