import subprocess
import sys
import shutil

REQUIRED_PYTHON = (3, 12)

def check_python_version():
    """Ensure the script is running with Python 3.12+."""
    if sys.version_info[:2] < REQUIRED_PYTHON:
        print(f"❌ Error: Python 3.12+ is required. Found {sys.version.split()[0]}")
        sys.exit(1)
    print(f"✅ Python Version Check: {sys.version.split()[0]}")

def setup_venv():
    """Initialize and sync the virtual environment using uv."""
    uv_executable = shutil.which("uv")
    
    if uv_executable:
        print("🚀 UV detected. Installing dependencies...")
        try:
            # Create venv if it doesn't exist (uv venv handles idempotency)
            subprocess.run(["uv", "venv"], check=True)
            # Sync dependencies from pyproject.toml
            subprocess.run(["uv", "sync"], check=True)
            print("✅ Environment synced successfully using UV.")
        except subprocess.CalledProcessError as e:
            print(f"❌ UV Sync Failed: {e}")
            sys.exit(1)
    else:
        print("⚠️ UV not found in PATH.")
        print("   Recommendation: Install UV for instant setup (curl -LsSf https://astral.sh/uv/install.sh | sh)")
        print("   Falling back to standard 'venv' and 'pip'...")
        
        # Fallback logic
        venv_path = ".venv"
        if not shutil.which("python3") and not shutil.which("python"):
             print("❌ Python executable not found per shutil. This is unexpected.")
             sys.exit(1)

        # Create venv
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
        
        # Install deps (requires activation logic or direct path usage)
        # On Windows, pip is in .venv/Scripts/pip
        pip_path = f"{venv_path}\\Scripts\\pip" if sys.platform == "win32" else f"{venv_path}/bin/pip"
        
        try:
            subprocess.run([pip_path, "install", "."], check=True) # Installs from pyproject.toml
            print("✅ Environment setup complete using standard pip.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Pip Install Failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    check_python_version()
    setup_venv()
