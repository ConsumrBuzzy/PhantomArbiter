import sys
import os

# quick hack to add src
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.normpath(os.path.join(current_dir, "../"))
sys.path.insert(0, root_dir)

from src.shared.structure.constellation_manager import ConstellationManager

print("--- Testing Billboard Generation ---")
billboards = ConstellationManager.get_sector_billboards()

count = 0
for b in billboards:
    count += 1
    print(f"[{count}] {b['label']}")
    print(f"    Pos: ({b['x']}, {b['y']}, {b['z']})")
    print(f"    Color: {b['hex_color']}")
    
if count >= 7:
    print(f"✅ Successfully generated {count} billboards.")
else:
    print(f"❌ Failed: Only generated {count} billboards.")
