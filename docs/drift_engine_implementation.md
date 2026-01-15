# Drift Engine Implementation Plan (Risk-First Architecture)

## 🏛️ Strategic Vision
The Drift Engine page is designed with a "Risk-First" mindset, moving beyond simple spot trading to handle the complexities of a Central Limit Order Book (CLOB) and leveraged perpetuals. The interface prioritizes safety metrics over basic balances to ensure liquidation risk is managed effectively.

### Strategic Pillar: "Split-Brain" Immunity
To ensure the UI always reflects the on-chain reality, the `DriftOrderController` must subscribe to a specific **Drift Account Stream** rather than relying purely on polling. 
- **Polling vs. Streaming**: Prices continue via WSS, but the Account Page must use the Drift User Account Subscriber for instantaneous health updates.
- **Health Sync**: Advanced `get_active_capital` logic must account for **Asset Weights** (e.g., $100 of SOL only counts as $80 of collateral) to prevent false safety readings.

## 📋 UI & Information Architecture

### 1. The "Health Gauge" Section (Focal Point)
- **Metric**: Health Score = $1 - (\text{Maintenance Margin} / \text{Margin Collateral})$.
- **Visual Logic**:
    - **90-100%**: Green (Safe)
    - **50-89%**: Yellow (Warning - Initial Margin used)
    - **<20%**: Pulsing Red (Liquidation Risk)
- **Leverage Meter**: Horizontal bar showing current vs. max allowed leverage (Drift allows up to 20x-100x).

### 2. Position Management Table ("Combat Zone")
| Column | Data Source | Importance |
| :--- | :--- | :--- |
| **Market** | `perp_market_index` | e.g., SOL-PERP, BTC-PERP. |
| **Size** | `base_asset_amount` | Long (Green) or Short (Red). |
| **PnL (Unrealized)** | `unsettled_pnl` | PnL remains "unsettled" until claimed. |
| **Liq. Price** | `liquidation_price` | The "Death Date" for the position. |
| **Funding** | `funding_rate` | Daily rate paid or received. |

### 3. Navigation & Controller Sidebar
- **Sidebar Integration**: Access via `fa-wave-square` icon in the main OS sidebar.
- **Sub-Account Selector**: Support for switching between multiple Drift sub-accounts.
- **Settle PnL Button**: Manual trigger for `settle_pnl()` to consolidate gains into collateral.
- **Delegated Signer Status**: Visual indicator showing if the engine has auto-signing authority.

## ⚙️ Implementation Phase Details

### Frontend Scaffold
- **Template**: `engine-drift.html` using a 3-column "Risk-Center" layout.
- **Styles**: `drift-engine.css` (custom themes for health bars and PnL states).
- **Controller**: `js/components/drift-controller.js` for real-time margin ratio and liq price calculations.

### Backend Pipeline
- **Heartbeat Upgrade**: `HeartbeatCollector.py` to provide maintenance margin and margin collateral.
- **Engine Link**: `EngineManager` wired to the Drift-specific Python runner for lifecycle management.

---
*Created on 2026-01-14 with full strategic context (User Notes + Initial Design).*
