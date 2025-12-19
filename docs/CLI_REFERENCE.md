# PhantomTrader CLI Reference

Command line interface documentation.

---

## Main Entry Point

```bash
python main.py [OPTIONS]
```

---

## Mode Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--live` | Enable real blockchain transactions | Off (Monitor) |
| `--monitor` | Paper trading only (no real trades) | Default |
| `--scalper` | Run primary RSI scalping engine | Off |
| `--longtail` | Run scout/longtail engine only | Off |
| `--data` | Run data broker mode | Off |
| `--status` | Show portfolio status and exit | Off |

---

## Usage Examples

### Monitor Mode (Safe)

```bash
# Paper trading - no real transactions
python main.py --monitor
python main.py --monitor --scalper
```

### Live Mode (Real Money)

```bash
# ⚠️ WARNING: Real trades enabled
python main.py --live --scalper
python main.py --live --longtail
```

### Data Broker Mode

```bash
# Run centralized data fetcher only
python main.py --data
# Or directly:
python data_broker.py
```

### Portfolio Status

```bash
# Quick status check and exit
python main.py --status
```

---

## Data Broker

```bash
python data_broker.py
```

The data broker runs as a separate process:
- Manages all WebSocket connections
- Handles HTTP price fetching
- Writes to SharedPriceCache
- Validates tokens in background

---

## Backtesting

```bash
python run_backtest.py [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--start` | Start date (YYYY-MM-DD) |
| `--end` | End date (YYYY-MM-DD) |
| `--strategy` | Strategy to backtest |
| `--symbol` | Token symbol to test |

Example:
```bash
python run_backtest.py --start 2024-01-01 --end 2024-03-01 --strategy SCALPER --symbol WIF
```

---

## Tool Commands

### Scout Tool

```bash
# Scan wallet for untracked tokens
python -m src.tools.scout --scan-wallet

# Discover new tokens
python -m src.tools.scout --discover
```

### Grader Tool

```bash
# Grade all tokens
python -m src.tools.grader

# Grade specific token
python -m src.tools.grader --symbol WIF
```

### Asset Manager

```bash
# List all assets
python -m src.tools.asset_manager --list

# Add new asset
python -m src.tools.asset_manager --add SYMBOL MINT_ADDRESS

# Remove asset
python -m src.tools.asset_manager --remove SYMBOL
```

### RugCheck

```bash
# Validate specific token
python -m src.tools.rugcheck MINT_ADDRESS
```

---

## PowerShell Scripts

Pre-configured scripts for Windows:

| Script | Command |
|--------|---------|
| `run_bot.ps1` | Full bot (broker + engine) |
| `run_live.ps1` | Live trading mode |
| `run_monitor.ps1` | Monitor (paper) mode |
| `run_scout.ps1` | Scout tool |
| `run_hunter.ps1` | Token discovery |
| `launch.ps1` | Multi-window launcher |

---

## Test Commands

```bash
# Test wallet connection
python test_connection.py

# Test Jupiter API
python test_jupiter.py
python test_jupiter_basic.py

# Test price fallback
python test_price_fallback.py

# Test position detection
python test_held_detection.py
```

---

## Database Migration

```bash
# Migrate to PostgreSQL
python scripts/migrate_to_postgres.py
```

---

## Environment Variables

Override settings via environment:

```bash
# Windows PowerShell
$env:ENABLE_TRADING = "true"
python main.py

# Linux/Mac
ENABLE_TRADING=true python main.py
```

Key environment variables:
- `SOLANA_PRIVATE_KEY` - Wallet keypair
- `JUPITER_API_KEY` - Jupiter API access
- `TELEGRAM_BOT_TOKEN` - Telegram integration
- `DYDX_ENABLED` - dYdX perpetuals mode
