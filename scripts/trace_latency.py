"""
Latency Trace - "The Reality Check"
====================================
Measures the critical "Signal-to-Execution" delta.
Answers: "How much does RPC lag + Processing cost me?"

Steps:
1.  PING: Fetch Price (Simulate RPC)
2.  THINK: Process Strategy (Simulate Logic)
3.  ACT: Execute Trade (Simulate CapitalManager)
"""

import time
import requests
import os
from src.shared.system.capital_manager import CapitalManager

# Setup lightweight CM
cm = CapitalManager()
ENGINE = "LATENCY_TESTER"
if ENGINE not in cm.state["engines"]:
    cm._add_engine(ENGINE)


def current_ms():
    return time.perf_counter() * 1000


def trace():
    print("\n⏱️  LATENCY TRACE START")
    print("=" * 40)

    # 1. READ (RPC Simulation)
    t0 = current_ms()
    print("1. [RPC] Fetching SOL Price...", end="", flush=True)
    # Simulate real network call to CoinGecko (or use Jito/RPC if available)
    try:
        requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
            timeout=2,
        )
    except:
        pass
    t1 = current_ms()
    read_lag = t1 - t0
    print(f" DONE ({read_lag:.1f}ms)")

    # 2. THINK (Strategy Simulation)
    print("2. [CPU] Computing Indicators...", end="", flush=True)
    # Simulate RSI/SMA math on 1000 points
    dummy = [x * 1.0 for x in range(1000)]
    sum(dummy)
    t2 = current_ms()
    think_lag = t2 - t1
    print(f" DONE ({think_lag:.1f}ms)")

    # 3. ACT (Execution Simulation)
    print("3. [EXE] CapitalManager Lock & Write...", end="", flush=True)
    # Simulate write overhead safely
    # We force the CM to use a test file to measure disk I/O
    original_file = cm.STATE_FILE
    cm.STATE_FILE = "latency_state.json"

    # Trigger a write
    try:
        cm._save_state()
    finally:
        # Cleanup
        if os.path.exists("latency_state.json"):
            os.remove("latency_state.json")
        cm.STATE_FILE = original_file

    t3 = current_ms()
    act_lag = t3 - t2
    print(f" DONE ({act_lag:.1f}ms)")

    # Report
    total_lag = t3 - t0
    print("-" * 40)
    print(f"📡 RPC Lag:       {read_lag:>6.1f} ms")
    print(f"🧠 Strategy Lag:  {think_lag:>6.1f} ms")
    print(f"⚙️ Execution Lag: {act_lag:>6.1f} ms")
    print("=" * 40)
    print(f"🛑 TOTAL SIGNAL-TO-EXECUTION: {total_lag:.1f} ms")

    if total_lag > 500:
        print("\n⚠️  CRITICAL WARNING: System is too slow for HFT (>500ms)")
        print("    Recommendation: Upgrade RPC or Rewrite Strategy in Rust")
    elif total_lag > 200:
        print("\n⚠️  WARNING: Latency is noticeable (>200ms)")
    else:
        print("\n✅ SYSTEM GREEN: Ready for Scalping (<200ms)")


if __name__ == "__main__":
    trace()
