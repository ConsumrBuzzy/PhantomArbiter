"""
Generate Market Map
===================
Phase 24: Visual Cartography

CLI tool to export the persistent market graph into WebGL-ready JSON.
Output: data/viz/nodes.json, data/viz/links.json
"""

import sys
import os
import argparse

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.shared.persistence.market_manager import MarketManager


def run(output_dir="data/viz"):
    print(f"🗺️  Generating Market Map (Output: {output_dir})...")

    manager = MarketManager()

    # Optional: Force rehydration first to ensure we have latest cold storage if DB is empty
    # But usually DB is hot. Let's assume hot DB or auto-hydrated.
    # If DB empty, try rehydrate.
    if not manager.repo.get_all_pools():
        print("   ⚠️ DB Empty. Attempting rehydration from archives...")
        manager.rehydrate()

    success = manager.export_graph_data(output_dir)

    if success:
        print("   ✅ Export Successful.")
        print(f"      - {output_dir}/nodes.json")
        print(f"      - {output_dir}/links.json")
    else:
        print("   ❌ Export Failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Market Graph to JSON")
    parser.add_argument("--out", type=str, default="data/viz", help="Output directory")
    args = parser.parse_args()

    run(args.out)
