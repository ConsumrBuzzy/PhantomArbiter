
# 🤖 AGENT.md - AI Developer Guide

**Welcome, Agent.**
This file provides the critical context you need to navigate, repair, and evolve the **PhantomArbiter** codebase efficiently.

---

## 🏗️ Project Architecture

PhantomArbiter is a **Hybrid Python/Rust** high-frequency trading bot on Solana.

* **Tiers of Operation**:
  * **FAST Tier (Rust)**: WSS Aggregation, Deduplication ("Race-to-First"), Signal Scoring (Pending). Handles milliseconds.
  * **MID Tier (Python Async)**: `Scalper`, `Arbiter`, `Director`. Handles logic, strategy, and execution.
  * **SLOW Tier (Python Background)**: `Scout`, `Landlord`, `DeepScout`. Handles analysis, rent management, and wallet sync.

* **Core Components**:
  * `src_rust/`: Rust extension (`phantom_core`). **Do not touch unless you are optimizing the hot path.**
  * `src/engine/director.py`: The Main Loop Supervisor. Orchestrates everything.
  * `src/engine/trade_executor.py`: Handles execution (Paper & Live). **Critical for money safety.**
  * `src/shared/system/capital_manager.py`: The "Bank". Manages balances, PnL, and position tracking.
  * `config/settings.py`: The "Brain". All constants and feature flags.

---

## ⚠️ Critical Rules (The "Prime Directives")

1. **Safety First**: `Settings.ENABLE_TRADING` must default to `False`. Never enable it without explicit user consent.
2. **No "Backtest Traps"**: Always verify simulation logic matches live execution.
    * *Example*: `TradeExecutor` uses `swapper` for Live, but `_execute_paper_buy` for Paper. Logic must be kept in sync.
3. **Use `TODO.md`**: It is the source of truth. If you finish a task, update it.
4. **Logging**: Use `priority_queue` for logs. The TUI (Pulse) consumes these. Standard `print` breaks the TUI.
5. **Paths**: Always use Absolute Paths.

---

## 🛠️ Common Tasks & Scripts

* **Boot the System (TUI)**: `python main.py pulse`
* **Run a Backtest**: `python scripts/run_backtest.py`
* **Debug Logs**: `python scripts/read_last_log.py`
* **Verify Trades**: `python scripts/parse_trades.py`
* **Check Performance**: `python scripts/trace_latency.py`

---

## 🚀 Active Context (As of Dec 30, 2025)

* **Current Phase**: "Institutional Realism" (Phase 4).
* **Recently Fixed**:
  * **Paper Wallet Match**: Fixed bug where Paper Sizing ignored intent. `TradeExecutor` now respects `size_usd`.
  * **Live Safety**: `ENABLE_TRADING` disabled in config.
  * **Crash**: Fixed `NameError` in `PaperWallet`.
* **Next Steps**:
    1. Move Signal Scoring logic to Rust (`src_rust`).
    2. Implement "Shadow Mode" (Paper vs Live compare).

---

**"Trust, but Verify."**
