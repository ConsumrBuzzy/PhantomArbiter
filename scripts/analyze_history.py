import time
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.shared.system.db_manager import db_manager
from src.arbiter.core.triangular_scanner import TriangularScanner


class MockDetector:
    def __init__(self):
        self._price_cache = {}


def analyze_history(hours=1):
    print(f"🔍 Analyzing history for the last {hours} hour(s)...")

    conn = db_manager.get_connection()
    c = conn.cursor()

    cutoff = time.time() - (hours * 3600)

    # Fetch all spread data
    try:
        c.execute(
            """
            SELECT * FROM spread_history 
            WHERE timestamp > ? 
            ORDER BY timestamp ASC
        """,
            (cutoff,),
        )
        rows = c.fetchall()
    except Exception as e:
        print(f"❌ Error querying DB: {e}")
        print("Note: If 'spread_history' table missing, logging was just enabled.")
        return

    if not rows:
        print("⚠️ No history found (Logging was just enabled!)")
        return

    print(f"📊 Found {len(rows)} spread records. Reconstructing market state...")

    # Group by second
    snapshots = {}
    for row in rows:
        ts = int(row["timestamp"])
        if ts not in snapshots:
            snapshots[ts] = []
        snapshots[ts].append(row)

    scanner = TriangularScanner([])  # No feeds needed for replay

    found_ops = 0

    for ts, records in snapshots.items():
        # Reconstruct Cache
        detector = MockDetector()

        for r in records:
            pair = r["pair"]
            # Reconstruct Best Bid/Ask map
            # We don't have all feeds, but we have the best ones used for the spread
            # TriangularScanner takes max(prices) for Bid and min(prices) for Ask

            # If we provide these two, it will find them.
            prices = {}
            if r["sell_dex"] and r["sell_price"] > 0:
                prices[r["sell_dex"]] = r["sell_price"]
            if r["buy_dex"] and r["buy_price"] > 0:
                prices[r["buy_dex"]] = r["buy_price"]

            if prices:
                detector._price_cache[pair] = prices

        # Update Graph
        scanner.update_graph(detector)

        # Check for cycles
        # We assume standard trade size $50 for simulation
        cycles = scanner.find_cycles(amount_in=50.0)

        if cycles:
            profitable = [c for c in cycles if c["profit_pct"] > 0.0]
            if profitable:
                print(f"\n[⏱️ {time.ctime(ts)}] Found {len(profitable)} Tri-Ops:")
                for cyc in profitable:
                    print(
                        f"   🚀 {cyc['path_str']} -> {cyc['profit_pct']:.2f}% (${cyc['net_profit']:.2f})"
                    )
                    found_ops += 1

    print(
        f"\n✅ Analysis Complete. Found {found_ops} potential triangular opportunities in history."
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_history(float(sys.argv[1]))
    else:
        analyze_history(1)
