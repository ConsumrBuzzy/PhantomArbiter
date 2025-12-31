import re
import glob
import os
import sys


def parse_logs():
    sys.stdout.reconfigure(encoding="utf-8")
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print("No logs dir.")
        return

    files = glob.glob(os.path.join(log_dir, "*.log"))
    if not files:
        print("No logs.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"Analyzing: {latest_file}")

    trades = []

    # Regex for EXECUTING log
    # 2025-12-30 15:39:00 [INFO] [SYSTEM] 🔧 EXECUTING MOCK BUY: TRUMP ($15.00)
    re_exec = re.compile(r"EXECUTING (?:MOCK|LIVE) (BUY|SELL): (\w+) \(\$([\d\.]+)\)")

    # Regex for SCALPER execution log
    # 2025-12-30 15:39:00 [INFO] [SYSTEM] 💰 [SCALPER] BUY TRUMP [JUPITER] (Liq: $0): 68.6811 @ $5.013385 (Slip: 2.02% / $6.96)
    re_scalper = re.compile(
        r"\[SCALPER\] (BUY|SELL) (\w+) .*?: ([\d\.]+) @ \$([\d\.]+) \(Slip: ([\d\.]+)% / \$([\d\.]+)\)"
    )

    pending_exec = {}  # symbol -> size_usd

    with open(latest_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Check Exec
            m_exec = re_exec.search(line)
            if m_exec:
                action, symbol, size = m_exec.groups()
                pending_exec[symbol] = float(size)
                # print(f"Intent: {action} {symbol} ${size}")

            # Check Scalper
            m_scalp = re_scalper.search(line)
            if m_scalp:
                action, symbol, units, price, slip_pct, slip_cost = m_scalp.groups()
                units = float(units)
                price = float(price)
                real_cost = units * price

                intent_size = pending_exec.get(symbol, 0.0)

                print(f"TRADE: {action} {symbol}")
                print(f"  > Intent: ${intent_size:.2f}")
                print(
                    f"  > Actual: ${real_cost:.2f} ({units:.4f} units @ ${price:.4f})"
                )
                print(f"  > Diff:   ${real_cost - intent_size:+.2f}")
                print("-" * 30)


if __name__ == "__main__":
    parse_logs()
