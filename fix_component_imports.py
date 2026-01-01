import os

TARGET_DIR = "src"
MOVED_MODULES = [
    "trade_executor",
    "decision_engine",
    "data_feed_manager",
    "watcher_manager",
    "signal_scanner",
    "shadow_manager",
    "slippage_calibrator",
    "congestion_monitor",
    "maintenance_service",
    "config_sync_service",
    "position_sizer",
    "heartbeat_reporter"
]

def scan_and_fix(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    modified = False
    
    for mod in MOVED_MODULES:
        old_import = f"src.engine.{mod}"
        new_import = f"src.strategies.components.{mod}"
        if old_import in new_content:
            new_content = new_content.replace(old_import, new_import)
            modified = True
            
        # Also check for "from src.engine import X" if X is one of the modules?
        # Typically people do "from src.engine.X import Class".
        
    if modified:
        print(f"🔧 Fixing {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

def main():
    print(f"🛠️  Fixing component imports in {TARGET_DIR}...")
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                scan_and_fix(path)
    print("✅ Done.")

if __name__ == "__main__":
    main()
