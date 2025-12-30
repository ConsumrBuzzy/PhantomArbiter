import difflib
import sys
import os

def compare_files(file1, file2):
    print(f"Comparing:\n1: {file1}\n2: {file2}\n")
    
    if not os.path.exists(file1):
        print(f"❌ File 1 missing: {file1}")
        return
    if not os.path.exists(file2):
        print(f"❌ File 2 missing: {file2}")
        return

    with open(file1, 'r', encoding='utf-8') as f1:
        lines1 = f1.readlines()
    with open(file2, 'r', encoding='utf-8') as f2:
        lines2 = f2.readlines()

    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    diff = difflib.unified_diff(
        lines1, lines2, 
        fromfile='src/core/capital_manager.py', 
        tofile='src/shared/system/capital_manager.py', 
        lineterm=''
    )
    
    diff_list = list(diff)
    
    if not diff_list:
        print("✅ FILES ARE IDENTICAL. Safe to delete duplicate.")
    else:
        print(f"⚠️ FILES DIFFER ({len(diff_list)} lines of diff).")
        print("First 20 lines of difference:")
        for line in diff_list[:20]:
            print(line)
            
        print("\nChecking for unique methods in Deprecated file...")
        methods1 = get_methods(lines1)
        methods2 = get_methods(lines2)
        
        unique = methods1 - methods2
        if unique:
            print(f"❌ UNIQUE METHODS in Deprecated file (DO NOT DELETE yet):")
            for m in unique:
                print(f"  - {m}")
        else:
            print("✅ No unique methods found in Deprecated file.")

def get_methods(lines):
    methods = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def "):
            name = stripped.split("(")[0].replace("def ", "")
            methods.add(name)
    return methods

if __name__ == "__main__":
    compare_files(
        "src/core/capital_manager.py",
        "src/shared/system/capital_manager.py"
    )
