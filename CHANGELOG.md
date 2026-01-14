# Changelog

All notable changes to PhantomArbiter will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Documentation overhaul and standardization (Jan 2026)

---

## [0.1.0] - 2025-12-30

### Added
- **Hybrid Architecture**: Python core + Rust acceleration + TypeScript bridges
- **Rust Extension (`phantom_core`)**: 
  - WSS Aggregator for multi-RPC deduplication (<1ms)
  - SignalScorer for Go/No-Go decision logic
  - CycleFinder using Bellman-Ford algorithm
  - Multiverse multi-hop path scanner
- **TypeScript Bridges**:
  - Orca Whirlpools daemon
  - Raydium CLMM/AMM daemon
  - Meteora DLMM bridge
  - Execution engine for transaction submission
- **Galaxy Dashboard**: Three.js 3D visualization UI
- **Scout Agents**: Smart money tracking and whale watching
- **ExecutionBackend**: Unified Paper/Live trade execution interface
- **ShadowManager**: Paper vs. Live execution auditing
- **Capital Manager**: Centralized PnL and position tracking

### Changed
- Migrated from monolithic "SRP" architecture to hybrid multi-language design
- Project renamed from "PhantomTrader" to "PhantomArbiter"
- Moved hot paths from Python to Rust for sub-millisecond performance

### Security
- Disabled live trading by default (`ENABLE_TRADING = False`)
- Implemented paper trading mode with realistic slippage simulation
- Added JITO bundle submission for MEV protection

---

## Historical Milestones

### M1: The Monolith (Pre-0.1.0)
- Pure Python V2 engine
- Monolithic architecture
- Jupiter-only execution

### M2: Hybrid Core (0.1.0)
- Node.js bridges introduced
- Rust acceleration layer
- Multi-DEX support (Orca, Raydium, Meteora)
