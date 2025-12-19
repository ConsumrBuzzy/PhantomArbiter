# PhantomArbiter Architecture

## Overview
PhantomArbiter is a **Solana DEX Arbitrage System** with a preserved Meme Coin Scraper module.

## 🏗️ Project Structure

```
PhantomArbiter/
├── main.py                    # Unified CLI entrypoint
├── config/                    # Shared configuration
├── scripts/                   # Utility scripts (14 files)
├── tests/                     # All tests (32 files)
└── src/
    ├── shared/                # Components used by BOTH projects
    │   ├── execution/         # WalletManager, JupiterSwapper
    │   ├── feeds/             # Jupiter, Raydium, Orca price feeds
    │   ├── system/            # Logging, utilities
    │   └── infrastructure/    # RPC balancer, Drift adapter
    │
    ├── arbiter/               # ACTIVE: Arbitrage project
    │   ├── arbiter.py         # Main orchestrator (PhantomArbiter class)
    │   ├── core/              # Executor, SpreadDetector, RiskManager
    │   ├── strategies/        # Spatial, Triangular, Funding arb
    │   └── monitoring/        # Dashboard, alerts
    │
    └── scraper/               # PRESERVED: Meme coin discovery
        ├── agents/            # ScoutAgent, SniperAgent, WhaleWatcher
        ├── discovery/         # LaunchpadMonitor, TokenRegistry
        └── scout/             # TokenScraper, Auditor
```

## 🎯 CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py arbiter` | Run spatial arbitrage (paper/live) |
| `python main.py scan` | Quick opportunity scan |
| `python main.py discover` | Find trending tokens |
| `python main.py watch` | Monitor launchpads |
| `python main.py scout` | Smart money analysis |
| `python main.py monitor` | Profitability dashboard |

## 🏛️ Logical Layers

### Layer 1: Data Ingestion (`src/shared/feeds/`)
- **JupiterFeed**: Jupiter aggregator prices
- **RaydiumFeed**: Raydium AMM prices
- **OrcaFeed**: Orca CLMM prices

### Layer 2: Opportunity Detection (`src/arbiter/core/`)
- **SpreadDetector**: Cross-DEX spread calculation
- **RiskManager**: Profitability validation

### Layer 3: Strategy Engines (`src/arbiter/strategies/`)
- **SpatialArb**: Buy DEX A → Sell DEX B
- **TriangularArb**: A → B → C → A cycles
- **FundingArb**: Spot + Perp delta-neutral

### Layer 4: Execution (`src/shared/execution/`)
- **WalletManager**: Keypair and balance management
- **JupiterSwapper**: Trade execution via Jupiter
- **AtomicExecutor**: Multi-leg atomic bundles

## 🚀 Key Principles
1. **Sibling Separation**: Arbiter and Scraper are independent modules sharing common infrastructure
2. **Atomic Execution**: Multi-leg trades succeed or fail together
3. **Paper-First**: Default to paper trading for safety
