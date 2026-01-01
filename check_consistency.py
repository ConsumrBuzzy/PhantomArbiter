import os
import ast
import sys

TARGET_DIR = "src"
FORBIDDEN_PATTERNS = [
    "src.scraper",
    "src.scalper",
    "spl.token",
    "find_program_address",
    "create_associated_token_account"
]

def scan_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            print(f"❌ Syntax Error in {filepath}")
            return []
    
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for pattern in FORBIDDEN_PATTERNS:
                    if pattern in alias.name:
                        issues.append(f"Import: {alias.name} (matches {pattern})")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for pattern in FORBIDDEN_PATTERNS:
                    if pattern in node.module:
                        issues.append(f"ImportFrom: {node.module} (matches {pattern})")
        elif isinstance(node, ast.Attribute):
            # Check for direct attribute usage if possible (harder with AST)
            pass
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_PATTERNS:
                     issues.append(f"Call: {node.func.id}")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in FORBIDDEN_PATTERNS:
                     issues.append(f"Call: {node.func.attr}")

    return issues

def main():
    print(f"🔍 Scanning {TARGET_DIR} for forbidden patterns: {FORBIDDEN_PATTERNS}")
    count = 0
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                issues = scan_file(path)
                if issues:
                    print(f"\n📂 {path}")
                    for issue in issues:
                        print(f"   ⚠️ {issue}")
                    count += 1
    
    print(f"\nFound issues in {count} files.")

if __name__ == "__main__":
    main()
