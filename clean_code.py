"""
PhantomArbiter Code Cleaner
===========================
User-Friendly Entry Point for Project Sanitization.

Usage:
  python clean_code.py          -> Runs audit only
  python clean_code.py --fix    -> Runs audit + Apply Rust fixes
"""

import subprocess
import sys
import os


def main():
    print("🚀 Launching PhantomArbiter Hygiene Sequence...")

    # Locate the sanitizer script
    script_path = os.path.join("scripts", "project_sanitizer.py")
    if not os.path.exists(script_path):
        # Fallback if run from scripts/ dir or elsewhere?
        # Assuming run from root c:\Github\PhantomArbiter
        print(f"❌ Could not find {script_path}")
        return

    # Forward arguments
    cmd = [sys.executable, script_path] + sys.argv[1:]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Sanitization failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n🛑 Aborted by user.")


if __name__ == "__main__":
    main()
