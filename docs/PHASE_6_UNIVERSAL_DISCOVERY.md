# 🏛️ Phase 6: Universal Market Discovery & Lifecycle Arbitrage

## Goal

To bridge the gap between "Meme-coin creation" and "Market maturity" by tracking the full lifecycle of a token across three distinct liquidity regimes.

## The Strategy: "Lifecycle Tracking"

| Stage | Platform | Program ID | Role | Technical Step |
| :--- | :--- | :--- | :--- | :--- |
| **1. Birth** | **Pump.fun** | `6EF8...` | High Risk / High Multiplier | Monitor create and trade instructions on Pump.fun. |
| **2. Migration** | **Raydium Std** | `675k...` | **The Sweet Spot** | Detect `initialize2` logs where $69k cap is reached. |
| **3. Maturity** | **Raydium CLMM** | `CAMM...` | Stable / Arb focus | Standardized price feed for high-volume scaling. |

## 🛠️ Execution Plan

### Step 1: The Pump.fun Data Feed

Instead of polling an API, we will add a dedicated WSS filter to the `WssAggregator` for the Pump.fun Program ID.

- **Focus**: We only care about `Complete` events (where the bonding curve is finished). This gives us a ~2-second lead over the rest of the market before the token appears on Raydium.

### Step 2: The Migration Trigger

When the `RaydiumStandardBridge` detects a new pool created by the Pump.fun migration wallet, the Scalper instantly fires an entry.

- **Why**: Graduation to Raydium Standard creates a temporary "liquidity vacuum" that often results in a 20-50% price spike in the first 30 seconds.

### Step 3: Risk-Adjusted Sizing

Update `CapitalManager` to treat these stages differently:

- **Stage 1 (Pump)**: Max $10 trade (High risk).
- **Stage 2 (Standard)**: Max $30 trade (Medium risk/Graduation play).
- **Stage 3 (CLMM)**: Max $50 trade (Stable/Arb).

## Tasks

- [x] **Data**: Update `SharedTokenMetadata` schema with lifecycle fields (`market_stage`, `bonding_curve_progress`).
- [ ] **Infrastructure**: Add Pump.fun WSS filter to `src_rust/src/wss_aggregator.rs`.
- [ ] **Bridge**: Implement `RaydiumStandardBridge` to map OpenBook Market IDs.
- [ ] **Core**: Implement `initialize2` log detection for migrations.
- [ ] **Scout**: Update `ScoutAgent` to prioritize "Graduation Alerts".
- [ ] **Risk**: Update `CapitalManager` with stage-based slippage/sizing logic.
