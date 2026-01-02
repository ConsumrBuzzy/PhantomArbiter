import sys
import os

# quick hack to add src relative to this script
current_dir = os.path.dirname(os.path.abspath(__file__))
# up one level to 'tests', up one to 'galaxy', then into 'src'
galaxy_src = os.path.normpath(os.path.join(current_dir, "../src"))
sys.path.insert(0, galaxy_src)

try:
    from galaxy.constellation_manager import ConstellationManager, TokenCategory
    
    test_cases = [
        ("WIF", TokenCategory.MEME),
        ("JUP", TokenCategory.DEFI),
        ("SOL", TokenCategory.INFRASTRUCTURE),
        ("UNKNOWN_TOKEN_XYZ", TokenCategory.UNKNOWN)
    ]
    
    print("--- Constellation Mapping Test ---")
    for symbol, expected in test_cases:
        category = ConstellationManager.get_category(symbol)
        status = "✅" if category == expected else f"❌ (Got {category})"
        print(f"{symbol}: {status} -> {category}")

except ImportError as e:
    print(f"Import Error: {e}")
    print(f"Path was: {sys.path}")
