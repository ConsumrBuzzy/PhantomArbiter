# PhantomTrader Configuration Guide

Complete reference for all configuration options.

---

## Configuration Files Overview

| File | Purpose |
|------|---------|
| `.env` | Secrets (private keys, API tokens) |
| `config/settings.py` | Trading parameters, risk limits |
| `config/thresholds.py` | Entry/exit thresholds |
| `config/rpc_pool.json` | RPC endpoint rotation |
| `data/watchlist.json` | Asset definitions |

---

## Environment Variables (`.env`)

```ini
# Required
SOLANA_PRIVATE_KEY=your_base58_private_key

# Optional - API Keys
JUPITER_API_KEY=               # Jupiter V6 API (higher rate limits)
COINGECKO_API_KEY=            # CoinGecko Pro API
TELEGRAM_BOT_TOKEN=           # Telegram bot control
TELEGRAM_CHAT_ID=             # Your Telegram user/group ID

# Optional - dYdX Integration (V40.0)
DYDX_ENABLED=false
DYDX_MNEMONIC=                # dYdX wallet seed phrase
DYDX_NETWORK=testnet          # "mainnet" or "testnet"

# Optional - Mode Override
EXECUTION_MODE=DEX            # "DEX" (Solana) or "DYDX" (Perpetuals)
```

---

## Capital & Position Settings

```python
# config/settings.py

# Shared Capital Pool
POOL_CAPITAL = 15.0          # Total portfolio cap (USD)
BUY_SIZE = 4.0               # Max per-trade allocation
MAX_POSITIONS = 3            # Max simultaneous positions
CASH_RESERVE = 3.0           # Minimum cash buffer

# V27.0: Risk-Based Position Sizing
RISK_PER_TRADE_PCT = 0.02    # Risk 2% of equity per trade

# ATR Position Sizing (V5.5)
ATR_MULTIPLIER = 2.0         # Stop-loss = ATR × 2.0
MIN_BUY_SIZE = 3.00          # Floor: Prevent micro-transactions
MAX_BUY_SIZE = 5.00          # Ceiling: Cap single position

# V20.0: Fractional Sizing
MAX_CAPITAL_PER_TRADE_PCT = 0.25  # Max 25% of cash per trade
```

---

## Trading Thresholds

```python
# config/settings.py

# Primary Targets (V7.0 Swing Trading)
TAKE_PROFIT_PCT = 0.04       # +4.0% target
STOP_LOSS_PCT = -0.03        # -3.0% stop-loss

# Legacy Thresholds (Fallback)
BREAKEVEN_FLOOR_PCT = 0.00325    # 0.325% nuclear exit
FAST_SCALP_PCT = 0.005           # 0.5% fast scalp
RECOVERY_TARGET_PCT = 0.00825    # 0.825% recovery exit

# Anti-Cascade Guard
HIBERNATION_SECONDS = 1800       # 30 min cooldown after stop-loss
EXTREME_OVERSOLD_RSI = 20        # RSI < 20 for re-entry after SL
```

### Trailing Stop Loss (V8.2)

```python
TSL_ENABLED = True
TSL_ACTIVATION_PCT = 0.020   # Activate at +2.0% profit
TSL_TRAIL_PCT = 0.015        # Trail by 1.5%
```

---

## Risk Controls (V28.0)

```python
# Circuit Breakers
MAX_DRAWDOWN_PER_STRATEGY_PCT = 0.15  # 15% → Auto-disable strategy
DAILY_DRAWDOWN_LIMIT_PCT = 0.05       # 5% daily → 24h pause

# Global Kill Switch
MAX_DAILY_DRAWDOWN = 0.10    # Stop if portfolio drops > 10%

# Distress Signal
DISTRESSED_THRESHOLD = -0.005  # -0.5% → Global lock
```

---

## Gas Management (V10.3)

```python
# SOL Balance Floors
GAS_FLOOR_SOL = 0.005        # Warn threshold (~$0.65)
GAS_CRITICAL_SOL = 0.002     # Auto-refuel trigger (~$0.26)
GAS_REPLENISH_USD = 1.00     # Buy min SOL to restore safety

CASH_FLOOR_USD = 2.00        # Emergency buffer only

# V24.0: Pre-trade check
MIN_SOL_RESERVE = 0.01       # Minimum SOL for gas (2 trades buffer)
```

---

## Token Safety Validation (V5.7)

```python
# Liquidity & Holder Checks
MIN_LIQUIDITY_USD = 100_000      # Minimum $100K liquidity
MAX_TOP10_HOLDER_PCT = 0.30      # Max 30% held by top 10 wallets

# Authority Checks
REQUIRE_MINT_REVOKED = True      # Block if mint authority active
REQUIRE_FREEZE_REVOKED = True    # Block if freeze authority active

# Honeypot Detection
ENABLE_HONEYPOT_CHECK = True
HONEYPOT_TEST_AMOUNT = 1_000_000 # 1 token (6 decimals)
HONEYPOT_SLIPPAGE_BPS = 1000     # 10% for simulation
```

---

## Execution Settings

```python
# Slippage
SLIPPAGE_BPS = 750           # 7.5% default
ADAPTIVE_SLIPPAGE_TIERS = [100, 300, 500, 1000]  # 1%→10% escalation

# Priority Fee
PRIORITY_FEE_MICRO_LAMPORTS = 50000  # ~0.00005 SOL per CU

# Mode Toggles
ENABLE_TRADING = False       # Master switch (False = Monitor)
SILENT_MODE = True           # True = production, False = debug
```

---

## Simulation Settings (V21.0+)

```python
# Paper Trading Realism
SIMULATION_SWAP_FEE_SOL = 0.0002     # Realistic DEX fee

# V46.0: Dynamic Slippage
SLIPPAGE_BASE_PCT = 0.003              # 0.3% base
SLIPPAGE_VOLATILITY_MULTIPLIER = 3.0   # 3x in volatile markets
SLIPPAGE_IMPACT_MULTIPLIER = 0.05      # Size impact factor

# Transaction Failure
TRANSACTION_FAILURE_RATE_PCT = 0.05    # 5% failure rate
LOW_LIQUIDITY_THRESHOLD_USD = 100000   # Low-liq threshold
LOW_LIQUIDITY_EXTRA_SLIPPAGE_MAX = 0.02  # +2% on low-liq

# V22.0: Execution Delay
EXECUTION_DELAY_MIN_MS = 200
EXECUTION_DELAY_MAX_MS = 500

# V23.0: Partial Fills
PARTIAL_FILL_RATE_PCT = 0.10  # 10% chance
MIN_FILL_PCT = 0.80           # 80% minimum fill

# V26.0: MEV Simulation
MEV_RISK_RATE_PCT = 0.15      # 15% sandwich risk
MEV_PENALTY_MAX_PCT = 0.03    # Up to 3% penalty

# V26.0: Network Congestion
HIGH_VOLATILITY_THRESHOLD_PCT = 0.10
CONGESTION_FAILURE_RATE_PCT = 0.15
CONGESTION_DELAY_MAX_MS = 1000
```

---

## RPC Pool Configuration

Edit `config/rpc_pool.json`:

```json
{
  "endpoints": [
    {
      "url": "https://api.mainnet-beta.solana.com",
      "weight": 1,
      "rate_limit": 10
    },
    {
      "url": "https://your-quicknode-endpoint.com",
      "weight": 10,
      "rate_limit": 100
    },
    {
      "url": "https://your-helius-endpoint.com",
      "weight": 5,
      "rate_limit": 50
    }
  ],
  "jito_endpoints": [
    "https://mainnet.block-engine.jito.wtf/api/v1/transactions"
  ]
}
```

**Fields:**
- `weight` — Higher = more frequently selected
- `rate_limit` — Requests per second limit

---

## Alert Policies (V40.0)

```python
ALERT_POLICIES = {
    # Market Volatility
    "DEX_VOLATILITY_HIGH_ATR_PCT": 0.04,     # 4% ATR = alert
    "DEX_TREND_BREAKOUT_ADX": 30.0,          # ADX > 30 = alert

    # dYdX Risk
    "DYDX_MARGIN_LOW_RATIO": 0.30,           # 30% margin alert

    # Engine Risk
    "ENGINE_DRAWDOWN_BREACH_PCT": 0.05,      # 5% drawdown alert

    # Spam Prevention
    "ALERT_COOLDOWN_SECONDS": 300,           # 5 min between alerts
}
```

---

## Engine Modes

```python
ENGINE_MODE = "SCALPER"   # SCALPER, KELTNER, LONGTAIL, VWAP
ENGINE_NAME = "PRIMARY"   # Identifier for logging
```

| Mode | Strategy | Best For |
|------|----------|----------|
| `SCALPER` | RSI oversold/overbought | Quick profits |
| `KELTNER` | Keltner Channel breakouts | Trending markets |
| `VWAP` | Volume-weighted entries | Fair value timing |
| `LONGTAIL` | Scout-focused discovery | New token discovery |
