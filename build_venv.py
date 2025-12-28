import subprocess
import sys
import shutil
import os
from pathlib import Path

REQUIRED_VERSION = "3.12"

def find_python_312():
    """Attempt to find a Python 3.12 executable."""
    # Check current interpreter
    if sys.version_info[:2] == (3, 12):
        return sys.executable

    # Check 'py' launcher on Windows
    if sys.platform == "win32" and shutil.which("py"):
        try:
            # Check if 3.12 is available via py
            res = subprocess.run(["py", "-3.12", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                print("✅ Found Python 3.12 via 'py' launcher.")
                return "py -3.12" # We will use this style for commands, but for venv we might need full path if not using uv
        except Exception:
            pass
            
    # Check explicit binaries
    candidates = ["python3.12", "python3.12.exe", "python-3.12"]
    for cand in candidates:
        path = shutil.which(cand)
        if path:
             return path
             
    return None

def setup_venv():
    """Initialize and sync the virtual environment using uv or standard venv."""
    uv_executable = shutil.which("uv")
    
    if uv_executable:
        print("🚀 UV detected. Enforcing Python 3.12...")
        try:
            # Force creating specific python version venv
            subprocess.run(["uv", "venv", "--python", REQUIRED_VERSION], check=True)
            subprocess.run(["uv", "sync"], check=True)
            print("✅ Environment synced successfully using UV with Python 3.12.")
            return
        except subprocess.CalledProcessError as e:
            print(f"❌ UV Sync Failed: {e}")
            # If uv fails to find python 3.12, we fall through to manual method or exit?
            # UV usually manages python versions well. If it fails, likely network or strict missing version.
            print("Attempting fallback...")

    print("⚠️ UV not found or failed. Falling back to standard 'venv'...")
    
    python_exe = find_python_312()
    if not python_exe:
        print(f"❌ Critical Error: Python {REQUIRED_VERSION} not found on this system.")
        print("Please install Python 3.12 via python.org or standard package manager.")
        sys.exit(1)
        
    venv_path = Path(".venv")
    
    # If using 'py -3.12' string, we need to handle it
    cmd = []
    if python_exe.startswith("py "):
        cmd = python_exe.split() + ["-m", "venv", str(venv_path)]
    else:
        cmd = [python_exe, "-m", "venv", str(venv_path)]

    print(f"Creating venv with: {cmd}")
    subprocess.run(cmd, check=True)
    
    # Install dependencies
    pip_path = venv_path / "Scripts" / "pip" if sys.platform == "win32" else venv_path / "bin" / "pip"
    
    try:
        # Added timeout to handle slow connections
        subprocess.run([str(pip_path), "install", ".", "--default-timeout=1000"], check=True)
        print("✅ Environment setup complete using standard pip.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Pip Install Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_venv()
