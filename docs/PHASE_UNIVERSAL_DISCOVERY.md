# Phase 6A: Universal Market Discovery

## Goal

Implement a hierarchical market discovery system to track tokens across their entire lifecycle (Pump.fun -> Raydium Standard -> Raydium CLMM) and capture the "Migration Gap" alpha.

## The Strategy: "Lifecycle Tracking"

Instead of blindly checking for a CLMM pool, we determine the token's **Market Stage**:

| Stage | Platform | Program ID | Alpha Opportunity |
| :--- | :--- | :--- | :--- |
| 1. Infancy | **Pump.fun** | `6EF8...` | Bonding Curve Sniping (High Risk/Reward) |
| 2. Adolescence | **Raydium Standard** | `675k...` | **The Migration Gap** (Golden Window for Volume) |
| 3. Maturity | **Raydium CLMM** | `CAMM...` | Efficient Arbitrage & Whale Following |

## Implementation Plan

### 1. Update Metadata Schema

- Modify `SharedTokenMetadata` (in Rust and Python) to include:
  - `market_stage` (Enum: `PUMP_FUN`, `RAYDIUM_STD`, `RAYDIUM_CLMM`)
  - `bonding_curve_progress` (float 0.0-1.0)
  - `migration_timestamp` (for timing graduation plays)

### 2. Create `UniversalDiscovery` Service

Replace or Augment `SauronDiscovery` with a logic that:

- Ingests a mint.
- Checks **Pump.fun Curve** state (is it active? completed?).
- Checks **Standard AMM** presence (did it just migrate?).
- Checks **CLMM** presence (is it mature?).

### 3. Build `RaydiumStandardBridge`

- A lightweight Python/Rust adapter to interact with Raydium Standard AMM (Account Layout V4).
- **Critical Function**: `find_standard_pool(mint)` using `getProgramAccounts` filters (optimized).

### 4. Build `PumpFunMonitor`

- Monitor the bonding curve state.
- Calculate "Distance to Graduation" (Percent bonded).

### 5. Integration

- Wire `UniversalDiscovery` into `ScoutAgent`.
- Update `TradeExecutor` to handle different "Execution Routes" based on stage (e.g. use Jito for Migration, standard slippage for Pump).

## Tasks

- [x] **Infrastructure**: Create `src/shared/execution/raydium_standard_bridge.py`.
- [x] **Infrastructure**: Create `src/scraper/discovery/pump_fun_monitor.py`.
- [/] **Core**: Update `SauronDiscovery` to use the hierarchical check (via `NEW_TOKEN` signal).
- [x] **Data**: Update `SharedTokenMetadata` schema.
- [ ] **Verification**: Finalize `scripts/verify_lifecycle.py` and fix runtime errors.
