import sys
import os

# quick hack to add src relative to this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# up one level to 'tests', up one to 'galaxy', up one to 'apps', then into root
root_dir = os.path.normpath(os.path.join(current_dir, "../../../"))
sys.path.insert(0, root_dir)

try:
    from src.shared.intelligence.taxonomy import taxonomy, TokenSector
    from src.shared.structure.constellation_manager import ConstellationManager
    
    test_cases = [
        ("WIF", TokenSector.MEME),
        ("JUP", TokenSector.DEFI),
        ("SOL", TokenSector.INFRA),
        ("UNKNOWN_TOKEN_XYZ", TokenSector.UNKNOWN)
    ]
    
    print("\n--- Taxonomy Classification Test (Tier 2/3) ---")
    for symbol, expected in test_cases:
        # returns Classification object
        classification = taxonomy.classify(symbol) 
        category = classification.sector
        status = "✅" if category == expected else f"❌ (Got {category})"
        print(f"Taxonomy: {symbol} -> {classification} {status}")

    print("\n--- Constellation Positioning Test ---")
    for symbol, expected in test_cases:
        # Check if we get valid coordinates
        # ConstellationManager uses taxonomy internally if category not provided
        x, z = ConstellationManager.get_island_position(mint="test_mint", symbol=symbol)
        print(f"Coords: {symbol} ({expected.value}) -> X:{x}, Z:{z}")
        
        # Verify island color
        color = ConstellationManager.get_island_color(expected)
        print(f"Color:  {color}")

except ImportError as e:
    print(f"Import Error: {e}")
    print(f"Path was: {sys.path}")
    import traceback
    traceback.print_exc()
