# Scripts Directory

Operational utilities and debugging tools for PhantomArbiter.

## Categories

### 🔍 Verification Scripts (`verify_*.py`)
Validate system components are working correctly.

| Script | Purpose |
|--------|---------|
| `verify_bus.py` | Check SignalBus connectivity |
| `verify_config_manager.py` | Validate configuration loading |
| `verify_daemon_scan.py` | Test background scanner |
| `verify_hydration.py` | Test Bellows rehydration |
| `verify_rpc_failover.py` | Test RPC endpoint failover |
| `verify_scavenger.py` | Test scavenger detection |

### 🔧 Check Scripts (`check_*.py`)
Query current system state.

| Script | Purpose |
|--------|---------|
| `check_balances.py` | Show wallet balances |
| `check_live_ready.py` | Pre-flight check for live trading |
| `check_system.py` | System health check |
| `check_wallet.py` | Wallet status |

### 🧪 Test Scripts (`test_*.py`)
Manual integration tests (not pytest).

| Script | Purpose |
|--------|---------|
| `test_ws_client.py` | WebSocket connectivity test |
| `test_orca.py` | Orca DEX integration test |
| `stress_test_adaptive.py` | Load testing |

### 💰 Operations (`recover_*.py`, `liquidate_*.py`)
Production operations requiring care.

| Script | Purpose |
|--------|---------|
| `recover_gas.py` | Recover SOL from dust accounts |
| `liquidate_all.py` | Emergency liquidation |
| `close_accounts.py` | Close empty token accounts |
| `smart_sweep.py` | Consolidated token sweep |

### 📊 Analysis (`analyze_*.py`, `debug_*.py`)
Data analysis and debugging.

| Script | Purpose |
|--------|---------|
| `analyze_history.py` | Historical trade analysis |
| `debug_feeds.py` | Debug price feed issues |
| `diagnose_prices.py` | Price discrepancy diagnosis |
| `trace_latency.py` | Latency profiling |
| `monitor_drift.py` | Price drift monitoring |

### 🚀 Runners
Entry points for specific systems.

| Script | Purpose |
|--------|---------|
| `run_backtest.py` | Run historical backtest |
| `run_profitability_monitor.py` | Real-time P&L tracking |
| `preflight_check.py` | Pre-launch validation |

## Usage

Most scripts can be run directly:

```bash
python scripts/check_balances.py
python scripts/verify_hydration.py
```

Some require the main environment:

```bash
python -m scripts.run_backtest
```
