import subprocess
import sys
import shutil
import os
from pathlib import Path


def build_rust():
    """Build the Rust extension using Maturin targeting the local .venv."""
    print("🦀 Building Rust Extension (phantom_core)...")

    # 1. Determine local venv path
    venv_dir = Path.cwd() / ".venv"
    if not venv_dir.exists():
        print("❌ Error: .venv not found.")
        print("Please run 'python build_venv.py' first.")
        sys.exit(1)

    # 2. Set environment variables to force Maturin to use this venv
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)

    # Add venv/Scripts or venv/bin to PATH to ensure we find the right python
    if sys.platform == "win32":
        path_insertion = venv_dir / "Scripts"
    else:
        path_insertion = venv_dir / "bin"

    env["PATH"] = str(path_insertion) + os.pathsep + env.get("PATH", "")

    # 3. Choose Command
    # If UV is available, 'uv run' is the most robust way to run commands in the venv context
    if shutil.which("uv"):
        # Explicitly invoke maturin via uv regardless of where current script is running
        command = ["uv", "run", "maturin", "develop", "--release"]
    else:
        # Fallback: Try to find maturin inside the venv
        maturin_executable = shutil.which("maturin", path=str(path_insertion))
        if not maturin_executable:
            # If not in venv, check global but keep env vars
            maturin_executable = shutil.which("maturin")

        if not maturin_executable:
            print(
                "❌ 'maturin' executable not found. Ensure it is installed in the venv."
            )
            sys.exit(1)

        command = [maturin_executable, "develop", "--release"]

    try:
        print(f"Running: {' '.join(command)}")
        subprocess.run(command, check=True, env=env)
        print("✅ Rust Extension Built Successfully!")

        # V133: Verify import
        print("🔍 Verifying Rust extension import...")
        python_path = (
            venv_dir / "Scripts" / "python"
            if sys.platform == "win32"
            else venv_dir / "bin" / "python"
        )
        verify = subprocess.run(
            [
                str(python_path),
                "-c",
                "import phantom_core; print('SUCCESS: phantom_core loaded successfully')",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        if verify.returncode != 0:
            print(f"❌ Verification failed: {verify.stderr}")
            sys.exit(1)
        print(verify.stdout.strip())
        print("✅ Rust Extension Installed & Verified!")

    except subprocess.CalledProcessError:
        print("❌ Build Failed.")
        sys.exit(1)


if __name__ == "__main__":
    build_rust()
