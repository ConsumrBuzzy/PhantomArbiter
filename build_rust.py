import subprocess
import sys
import shutil

def build_rust():
    """Build the Rust extension using Maturin."""
    print("🦀 Building Rust Extension (phantom_core)...")
    
    # Check for maturin
    maturin_executable = shutil.which("maturin") or "maturin"
    
    try:
        # Run maturin develop (builds and installs into current venv)
        # Using the venv's python to ensure proper installation location if possible
        # Or relying on maturin being active in the env.
        # Ideally, we run this *inside* the active venv.
        
        # We assume the user runs this with the venv python: `python build_rust.py`
        # If so, `maturin develop` works best if run as `maturin develop` (if maturin is in path)
        # or `python -m maturin develop` if installed in the venv.
        
        command = [sys.executable, "-m", "maturin", "develop", "--release"]
        
        subprocess.run(command, check=True)
        print("✅ Rust Extension Built & Installed Successfully!")
        
    except subprocess.CalledProcessError:
        print("❌ Build Failed.")
        print("Ensure you have activated the virtual environment and installed dependencies.")
        print("Command: uv sync (or python build_venv.py)")
        sys.exit(1)
    except FileNotFoundError:
         print("❌ `maturin` not found.")
         print("Please run `uv sync` first to install build dependencies.")
         sys.exit(1)

if __name__ == "__main__":
    build_rust()
