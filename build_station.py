import subprocess
import sys
import shutil
from pathlib import Path

REQUIRED_VERSION = "3.12"


def print_step(msg):
    print(f"\n🟦 {msg}")


def print_success(msg):
    print(f"✅ {msg}")


def print_error(msg):
    print(f"❌ {msg}")


def print_warning(msg):
    print(f"⚠️  {msg}")


def find_python_312():
    """Attempt to find a Python 3.12 executable."""
    # Check current interpreter
    if sys.version_info[:2] == (3, 12):
        return sys.executable

    # Check 'py' launcher on Windows
    if sys.platform == "win32" and shutil.which("py"):
        try:
            # Check if 3.12 is available via py
            res = subprocess.run(
                ["py", "-3.12", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode == 0:
                print("Found Python 3.12 via 'py' launcher.")
                return "py -3.12"
        except Exception:
            pass

    # Check explicit binaries
    candidates = ["python3.12", "python3.12.exe", "python-3.12", "python"]
    for cand in candidates:
        path = shutil.which(cand)
        if path:
            # Verify version
            try:
                res = subprocess.run(
                    [path, "--version"], capture_output=True, text=True
                )
                if "3.12" in res.stdout:
                    return path
            except:
                continue

    return None


def check_env_file():
    print_step("Checking Environment Configuration...")
    env_path = Path(".env")
    template_path = Path(".env.template")
    example_path = Path(".env.example")

    if env_path.exists():
        print_success(".env file exists.")
    else:
        print_warning(".env file missing.")
        if template_path.exists():
            shutil.copy(template_path, env_path)
            print_success(f"Created .env from {template_path}")
            print_warning("PLEASE UPDATE .env WITH YOUR KEYS!")
        elif example_path.exists():
            shutil.copy(example_path, env_path)
            print_success(f"Created .env from {example_path}")
            print_warning("PLEASE UPDATE .env WITH YOUR KEYS!")
        else:
            print_error("No .env.template or .env.example found. Creating empty .env.")
            env_path.touch()


def ensure_directories():
    print_step("Verifying Directory Structure...")
    dirs = ["data", "logs", "config"]
    for d in dirs:
        p = Path(d)
        if not p.exists():
            p.mkdir(exist_ok=True)
            print_success(f"Created directory: {d}")
        else:
            print_success(f"Directory exists: {d}")


def setup_venv():
    print_step("Setting up Virtual Environment...")

    # Try UV first
    uv_executable = shutil.which("uv")
    using_uv = False

    if uv_executable:
        print("🚀 UV detected.")
        try:
            print("Syncing environment with UV...")
            subprocess.run(["uv", "venv", "--python", REQUIRED_VERSION], check=True)
            subprocess.run(["uv", "sync"], check=True)
            # UV specific pip install just in case, or rely on internal sync if pyproject.toml matches
            # For this script we assume standard pip install usage often, but UV sync handles deps if configured.
            # If no uv.lock, we forced venv creation. Now let's try to install deps.
            # actually if we just did 'uv venv', we still need to install deps if 'uv sync' didn't thrive.
            # Assuming 'uv sync' might fail if no lockfile/toml setup for it.
            # Let's fallback to standard pip install inside the uv venv logic if sync fails or just do it explicitly.
            using_uv = True
            print_success("UV Setup Complete.")
        except subprocess.CalledProcessError:
            print_warning(
                "UV sync failed or not configured fully. Falling back to standard venv logic but using uv venv."
            )
            using_uv = True

    if not using_uv:
        python_exe = find_python_312()
        if not python_exe:
            print_error(f"Python {REQUIRED_VERSION} not found on this system.")
            sys.exit(1)

        venv_path = Path(".venv")
        if not venv_path.exists():
            print(f"Creating venv at {venv_path}...")
            cmd = []
            if python_exe.startswith("py "):
                cmd = python_exe.split() + ["-m", "venv", str(venv_path)]
            else:
                cmd = [python_exe, "-m", "venv", str(venv_path)]
            subprocess.run(cmd, check=True)
            print_success("Virtual Environment Created.")
        else:
            print_success("Virtual Environment already exists.")

    # Install Dependencies
    print_step("Installing Dependencies...")
    venv_path = Path(".venv")

    # Determine Pip Path
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"

    if not pip_path.exists():
        # Fallback for uv structure sometimes varying?
        # UV creates standard venv structure usually.
        print_error(f"Pip not found at: {pip_path}")
        # Try to find it generically?
        sys.exit(1)

    # Upgrade pip
    try:
        subprocess.run([str(pip_path), "install", "--upgrade", "pip"], check=True)
    except:
        pass

    # Install maturin
    print("Installing build tools (maturin)...")
    subprocess.run([str(pip_path), "install", "maturin"], check=True)

    # Install requirements
    if Path("requirements.txt").exists():
        print("Installing from requirements.txt...")
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"], check=True)
    elif Path("pyproject.toml").exists():
        print("Installing from pyproject.toml...")
        subprocess.run([str(pip_path), "install", "."], check=True)
    else:
        print_warning("No dependency file found (requirements.txt or pyproject.toml).")

    print_success("Dependencies Installed.")


def main():
    print("=" * 60)
    print("    🏗️  PhantomArbiter Station Builder  🏗️")
    print("=" * 60)

    check_env_file()
    ensure_directories()
    setup_venv()

    print("\n" + "=" * 60)
    print("    🎉  Station Setup Complete!  🎉")
    print("=" * 60)
    print("To activate:")
    if sys.platform == "win32":
        print("    .venv\\Scripts\\activate")
    else:
        print("    source .venv/bin/activate")


if __name__ == "__main__":
    main()
