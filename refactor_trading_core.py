import os

TARGET_DIR = "src"
REPLACEMENTS = {
    "from src.engine.trading_core import TradingCore": "from src.strategies.tactical import TacticalStrategy",
    "src.engine.trading_core": "src.strategies.tactical",
    "TradingCore": "TacticalStrategy"
}

def scan_and_fix(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    modified = False
    
    # 1. Import statements
    if "from src.engine.trading_core import TradingCore" in new_content:
        new_content = new_content.replace(
            "from src.engine.trading_core import TradingCore", 
            "from src.strategies.tactical import TacticalStrategy"
        )
        modified = True
    
    # 2. Module references
    if "src.engine.trading_core" in new_content:
        new_content = new_content.replace("src.engine.trading_core", "src.strategies.tactical")
        modified = True
        
    # 3. Class Usage (TradingCore)
    # Be careful not to replace partial words if any
    # But TradingCore is CamelCase, unlikely to be substring of something else common.
    if "TradingCore" in new_content:
        new_content = new_content.replace("TradingCore", "TacticalStrategy")
        modified = True

    if modified:
        print(f"🔧 Fixing {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

def main():
    print(f"🛠️  Refactoring TradingCore in {TARGET_DIR}...")
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith(".py") or file.endswith(".md"):
                path = os.path.join(root, file)
                # Skip the file defining the class itself if I handle it manually?
                # No, I already renamed the class definition in Step 840 using replace_file_content.
                # So renaming usages in tactical.py is also fine (docstrings).
                scan_and_fix(path)
    print("✅ Done.")

if __name__ == "__main__":
    main()
