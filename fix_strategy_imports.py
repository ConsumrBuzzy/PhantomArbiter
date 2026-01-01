import os

TARGET_DIR = "src"
REPLACEMENTS = {
    "from src.strategy": "from src.strategies.logic",
    "import src.strategy": "import src.strategies.logic",
    "src.strategy": "src.strategies.logic",
}

def scan_and_fix(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            content = f.read()
        except:
            return
    
    new_content = content
    modified = False
    for old, new in REPLACEMENTS.items():
        if old in new_content:
            new_content = new_content.replace(old, new)
            modified = True
            
    if modified:
        print(f"🔧 Fixing {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

def main():
    print(f"🛠️  Fixing strategy imports in {TARGET_DIR}...")
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                scan_and_fix(path)
    print("✅ Done.")

if __name__ == "__main__":
    main()
