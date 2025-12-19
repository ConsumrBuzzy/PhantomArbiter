# PhantomTrader Quickstart Guide

Get PhantomTrader running in 5 minutes.

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.10+ | Runtime |
| Solana Wallet | - | Trading keypair |
| RPC Endpoint | - | Blockchain access |

**Recommended RPC Providers:** QuickNode, Helius, or Helios for speed and reliability.

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/ConsumrBuzzy/PhantomTrader.git
cd PhantomTrader
```

### 2. Create Virtual Environment (Recommended)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Key Dependencies:**
- `solana` / `solders` — Solana SDK
- `python-telegram-bot` — Remote control
- `scikit-learn` / `xgboost` — ML features
- `aiohttp` — Async HTTP
- `psycopg2-binary` — PostgreSQL (optional)

---

## Configuration

### 1. Environment Variables

Create `.env` file in project root:

```ini
# Required
SOLANA_PRIVATE_KEY=your_base58_private_key_here

# Optional
JUPITER_API_KEY=optional_api_key
COINGECKO_API_KEY=optional_for_better_rate_limits
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

> ⚠️ **Security:** Never commit `.env` to version control. It's `.gitignore`d by default.

### 2. Watchlist Configuration

Edit `data/watchlist.json` to define tracked tokens:

```json
{
  "assets": {
    "WIF": {
      "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
      "category": "ACTIVE",
      "trading_enabled": true,
      "coingecko_id": "dogwifcoin"
    },
    "BONK": {
      "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
      "category": "SCOUT",
      "trading_enabled": false
    }
  }
}
```

**Categories:**
| Category | Description | Trading |
|----------|-------------|---------|
| `ACTIVE` | High-frequency monitoring | ✅ Enabled |
| `VOLATILE` | High-volatility tokens | ✅ Enabled |
| `SCOUT` | Discovery candidates | ❌ Monitoring only |
| `WATCH` | Price tracking only | ❌ Monitoring only |

### 3. Trading Parameters

Key settings in `config/settings.py`:

```python
# Capital
POOL_CAPITAL = 15.0          # Total portfolio cap (USD)
BUY_SIZE = 4.0               # Max per-trade allocation
MAX_POSITIONS = 3            # Concurrent positions

# Risk
TAKE_PROFIT_PCT = 0.04       # +4% target
STOP_LOSS_PCT = -0.03        # -3% stop
RISK_PER_TRADE_PCT = 0.02    # 2% portfolio risk per trade

# Trailing Stop Loss
TSL_ENABLED = True
TSL_ACTIVATION_PCT = 0.020   # Activate at +2% profit
TSL_TRAIL_PCT = 0.015        # 1.5% trail distance
```

---

## Running the Bot

### Monitor Mode (Safe - No Real Trades)

```bash
python main.py --monitor
```

- Simulates all trading logic
- Uses paper wallet for capital tracking
- Safe for testing and learning

### Live Mode (Real Money)

```bash
python main.py --live --scalper
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--live` | Enable blockchain transactions |
| `--scalper` | Run primary RSI scalping engine |
| `--longtail` | Run scout/longtail engine only |
| `--data` | Run data broker mode |
| `--status` | Show portfolio status and exit |

### Data Broker (Separate Process)

For production setups, run the data broker in a separate terminal:

```bash
python data_broker.py
```

The broker handles:
- WebSocket price feeds
- HTTP batch fetching
- Token validation
- Wallet state caching

---

## PowerShell Launch Scripts

Pre-configured scripts for Windows:

```powershell
# Launch full bot
.\run_bot.ps1

# Launch with monitoring
.\run_monitor.ps1

# Launch live trading
.\run_live.ps1

# Launch scout tool
.\run_scout.ps1
```

---

## First Run Checklist

1. ✅ Environment configured (`.env` with private key)
2. ✅ Watchlist populated (`data/watchlist.json`)
3. ✅ Start in Monitor Mode first
4. ✅ Verify prices are updating in logs
5. ✅ Observe paper trades executing correctly
6. ✅ Only then enable Live Mode

---

## Verification Commands

### Check Wallet Connection

```bash
python test_connection.py
```

### Check Jupiter Connectivity

```bash
python test_jupiter.py
```

### View Portfolio Status

```bash
python main.py --status
```

---

## Next Steps

- [Configuration Guide](./CONFIGURATION.md) — Deep dive into all settings
- [Trading Strategies](./TRADING_STRATEGIES.md) — Strategy explanations
- [Risk Management](./RISK_MANAGEMENT.md) — Risk controls
- [Telegram Bot](./TELEGRAM_BOT.md) — Remote control setup
