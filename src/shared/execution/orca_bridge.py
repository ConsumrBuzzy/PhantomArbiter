import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any
from src.shared.system.logging import Logger


class OrcaBridge:
    """
    Python wrapper for the persistent Orca Node.js Daemon.
    Handles IPC via stdin/stdout for sub-50ms latency.
    """

    _instance = None

    def __new__(cls, bridge_path: str = None):
        if cls._instance is None:
            cls._instance = super(OrcaBridge, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, bridge_path: str = None):
        if self._initialized:
            return

        if bridge_path:
            self.bridge_path = Path(bridge_path)
        else:
            # Auto-detect path relative to project root
            self.bridge_path = (
                Path(__file__).parent.parent.parent.parent
                / "bridges"
                / "orca_daemon.js"
            )

        # State
        self.process = None
        self._initialized = True

    def _ensure_process(self):
        """Ensure the Node.js daemon is running."""
        if self.process and self.process.poll() is None:
            return

        try:
            Logger.info(f"[ORCA] Starting Daemon: {self.bridge_path}")

            # Start process with pipes
            self.process = subprocess.Popen(
                ["node", str(self.bridge_path), "daemon"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=str(self.bridge_path.parent),
            )

            # Read startup line (optional, purely for debug)
            # Our daemon prints "DEBUG: Orca Daemon Ready" to stderr on start

        except Exception as e:
            Logger.error(f"[ORCA] Failed to start daemon: {e}")
            self.process = None

    def get_price(self, pool_address: str) -> Optional[Dict[str, Any]]:
        """
        Get price for a specific pool via Daemon.
        """
        self._ensure_process()
        if not self.process:
            return None

        request = {"cmd": "price", "pool": pool_address}

        try:
            # Send request
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()

            # Read response
            output = self.process.stdout.readline()
            if not output:
                Logger.warning("[ORCA] Daemon closed connection")
                self.process = None
                return None

            return json.loads(output)

        except Exception as e:
            Logger.error(f"[ORCA] IPC error: {e}")
            # Kill process to force restart on next call
            if self.process:
                self.process.kill()
                self.process = None
            return None


if __name__ == "__main__":
    # Internal test
    print("Orca Bridge Test")
    bridge = OrcaBridge()
    # Test with SOL/USDC Whirlpool (Czfq... is the main one)
    # Actually need to find a valid whirlpool address first.
    # Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE is SOL/USDC (64)
    res = bridge.get_price("Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE")
    print(f"Result: {res}")
