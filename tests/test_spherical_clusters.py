import sys
import os
import math

# quick hack to add src
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.normpath(os.path.join(current_dir, "../"))
sys.path.insert(0, root_dir)

from src.shared.structure.constellation_manager import ConstellationManager, ISLAND_CENTROIDS, TokenSector

print("--- Testing Spherical Cluster Generation ---")

# Mock tokens for DEFI sector
tokens = [
    {"mint": "MINT_A", "symbol": "TOKEN_A", "volume": 100000000}, # High vol
    {"mint": "MINT_B", "symbol": "TOKEN_B", "volume": 50000},     # Low vol
    {"mint": "MINT_C", "symbol": "TOKEN_C", "volume": 1000},      # Very low vol
]

centroid = ISLAND_CENTROIDS[TokenSector.DEFI]
print(f"DEFI Centroid: ({centroid.x}, {centroid.z}) Radius: {centroid.radius}")

for t in tokens:
    x, y, z = ConstellationManager.get_island_position_3d(
        mint=t["mint"],
        symbol=t["symbol"],
        category="DEFI",
        volume=t["volume"]
    )
    
    # Calculate distance from key centroid (note: y centroid is 0)
    dx = x - centroid.x
    dy = y - 0
    dz = z - centroid.z
    dist = math.sqrt(dx*dx + dy*dy + dz*dz)
    
    print(f"Token {t['symbol']} (Vol: ${t['volume']}):")
    print(f"    Pos: ({x}, {y}, {z})")
    print(f"    Dist from Core: {dist:.2f} (Max Radius: {centroid.radius})")
    
    if y != 0:
        print("    ✅ Y-axis utilized (3D confirmed)")
    else:
        print("    ⚠️ Y-axis is 0 (Flat disc?)")

print("\n--- Testing CoordinateTransformer Integration ---")
from src.arbiter.coordinate_transformer import CoordinateTransformer

data = {
    "mint": "MINT_A",
    "symbol": "TOKEN_A",
    "category": "DEFI",
    "volume_24h": 100000000,
    "rsi": 70 # Should add upward momentum
}

fx, fy, fz = CoordinateTransformer.get_xyz(data)
print(f"Transformer Output (RSI 70): ({fx}, {fy}, {fz})")

# Check if RSI influenced Height
# Base Y approx 0?
base_x, base_y, base_z = ConstellationManager.get_island_position_3d(
    mint=data["mint"], symbol=data["symbol"], category="DEFI", volume=data["volume_24h"]
)
print(f"Base Sphere Pos: ({base_x}, {base_y}, {base_z})")
if fy != base_y:
     print(f"✅ RSI Modified Height: {base_y} -> {fy}")
else:
     print(f"⚠️ RSI Did not modify height")
