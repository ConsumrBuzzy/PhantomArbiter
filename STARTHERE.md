
# 👻 Start Here - PhantomArbiter

**Welcome to PhantomArbiter**, an institutional-grade experimental trading framework for Solana.

---

## 🚀 Quick Start

1. **Activate Environment**:

    ```powershell
    .venv\Scripts\Activate.ps1
    ```

2. **Launch Dashboard (Pulse)**:

    ```bash
    python main.py pulse
    ```

    *This runs the "Monitor Mode" TUI with standard logic.*

3. **Run Tools**:
    * **Analyze Logs**: `python scripts/parse_trades.py` (See exactly what the bot bought/sold)
    * **Trace Latency**: `python scripts/trace_latency.py` (Measure network speed)

---

## 📂 Directory Structure

* `src/`: Python source code.
  * `engine/`: Core logic (`Director`, `TradeExecutor`).
  * `strategy/`: Trading strategies (`Scalper`, `Arbiter`).
  * `shared/`: Shared utilities (`CapitalManager`, `PaperWallet`).
* `src_rust/`: High-performance Rust extension (WSS Aggregation).
* `data/`: Local storage (price cache, token lists).
* `logs/`: Log files (Gitignored).
* `docs/`: Documentation.
  * **`TODO.md`**: Master roadmap and active tasks.
  * **`AGENT.md`**: Guide for AI collaborators.

---

## ⚠️ Safety Notice

* **Live Trading is DISABLED by default** in `config/settings.py` (`ENABLE_TRADING = False`).
* To trade real assets, you must explicit enable it and have a valid Private Key in `.env`.
* **Paper Trading** runs by default in Pulse mode. It simulates slippage, gas fees, and network latency for realism.

---

*For detailed architectural context, see [docs/AGENT.md](docs/AGENT.md).*
