from solders.pubkey import Pubkey
import requests
from typing import Dict
from config.settings import Settings
from src.shared.system.logging import Logger


class PumpFunMonitor:
    """
    Pump.fun Bonding Curve Monitor
    Program ID: 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P

    Responsible for tracking the "Infancy" stage.
    """

    PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
    GRADUATION_THRESHOLD_SOL = 85.0  # Approx amount to trigger migration

    def __init__(self):
        self.rpc_url = Settings.RPC_URL

    def get_bonding_curve_address(self, mint_str: str) -> Pubkey:
        """Derive the Bonding Curve PDA."""
        mint = Pubkey.from_string(mint_str)
        pda, _ = Pubkey.find_program_address(
            [b"bonding-curve", bytes(mint)], self.PROGRAM_ID
        )
        return pda

    def check_status(self, mint_str: str) -> Dict:
        """
        Check the status of the bonding curve.
        Returns:
            {
                'active': bool,
                'sol_reserves': float,
                'progress_pct': float, # 0.0 to 1.0 (1.0 = Graduation)
                'curve_address': str
            }
        """
        try:
            curve_pda = self.get_bonding_curve_address(mint_str)

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [str(curve_pda)],
            }

            resp = requests.post(self.rpc_url, json=payload, timeout=3)
            data = resp.json()

            if "result" in data:
                lamports = data["result"]["value"]
                sol_balance = lamports / 1_000_000_000

                # Heuristic: If balance > 0, it's likely active (or complete but not closed)
                # If balance is 0, it might be migrated or closed.

                progress = min(sol_balance / self.GRADUATION_THRESHOLD_SOL, 1.0) * 100

                return {
                    "active": True,
                    "sol_reserves": sol_balance,
                    "progress_pct": progress,
                    "curve_address": str(curve_pda),
                }

        except Exception as e:
            Logger.debug(f"[PUMP-MON] Check failed: {e}")

        return {
            "active": False,
            "sol_reserves": 0,
            "progress_pct": 0,
            "curve_address": "",
        }


# Singleton Concept (optional, for now just class)
