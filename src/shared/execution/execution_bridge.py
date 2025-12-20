"""
Unified Execution Bridge
=========================
Python wrapper for the TypeScript Unified Execution Engine.

Enables atomic multi-DEX swaps with a single call:
- Buy on Meteora, sell on Orca (or any combination)
- Automatic Compute Budget optimization
- Jito bundle support (optional)

Usage:
    bridge = ExecutionBridge()
    result = bridge.atomic_arb(
        leg1={'dex': 'meteora', 'pool': '...', 'inputMint': '...', 'outputMint': '...', 'amount': 1000000},
        leg2={'dex': 'meteora', 'pool': '...', 'inputMint': '...', 'outputMint': '...', 'amount': 1000000}
    )
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

try:
    from src.shared.system.logging import Logger
except ImportError:
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def error(msg): print(f"[ERROR] {msg}")
        @staticmethod
        def debug(msg): pass


@dataclass
class SwapLeg:
    """Represents one leg of a multi-DEX swap."""
    dex: str  # 'meteora', 'orca', 'jupiter'
    pool: str
    input_mint: str
    output_mint: str
    amount: int
    slippage_bps: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            'dex': self.dex,
            'pool': self.pool,
            'inputMint': self.input_mint,
            'outputMint': self.output_mint,
            'amount': self.amount,
            'slippageBps': self.slippage_bps,
        }


@dataclass
class LegResult:
    """Result from one swap leg."""
    dex: str
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    price_impact: float = 0.0


@dataclass
class ExecutionResult:
    """Result from unified execution engine."""
    success: bool
    command: str
    signature: Optional[str] = None
    legs: List[LegResult] = field(default_factory=list)
    error: Optional[str] = None
    simulation_success: Optional[bool] = None
    simulation_error: Optional[str] = None
    compute_units_used: Optional[int] = None
    timestamp: int = 0


class ExecutionBridge:
    """
    Python wrapper for the Unified TypeScript Execution Engine.
    
    Enables atomic multi-DEX swaps via persistent Node.js daemon.
    """
    
    def __init__(self, engine_path: Optional[str] = None):
        """
        Initialize the bridge.
        """
        if engine_path:
            self.engine_path = Path(engine_path)
        else:
            project_root = Path(__file__).parent.parent.parent.parent
            self.engine_path = project_root / "bridges" / "execution_engine.js"
        
        if not self.engine_path.exists():
            Logger.warning(f"[EXEC] Engine not found at {self.engine_path}")
            Logger.warning("[EXEC] Run: cd bridges && npm install && npm run build")
            
        self._daemon = None

    def _ensure_daemon(self):
        """Start daemon if not running."""
        if self._daemon and self._daemon.poll() is None:
            return

        try:
            cmd = ["node", str(self.engine_path), "daemon"]
            self._daemon = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.engine_path.parent),
                bufsize=1
            )
            Logger.info("[EXEC] Daemon started (PID: %s)", self._daemon.pid)
        except Exception as e:
            Logger.error(f"[EXEC] Failed to start daemon: {e}")
            self._daemon = None

    def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send command to daemon via IPC."""
        self._ensure_daemon()
        if not self._daemon:
            return {"success": False, "error": "Daemon failed to start"}
            
        try:
            payload = json.dumps(command) + "\n"
            self._daemon.stdin.write(payload)
            self._daemon.stdin.flush()
            
            line = self._daemon.stdout.readline()
            if not line:
                Logger.error("[EXEC] Daemon closed stream")
                self._daemon = None
                return {"success": False, "error": "Daemon closed stream"}
                
            return json.loads(line.strip())
        except Exception as e:
            Logger.error(f"[EXEC] IPC error: {e}")
            if self._daemon:
                self._daemon.kill()
                self._daemon = None
            return {"success": False, "error": str(e)}

    def _run_engine(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy wrapper: run command via Daemon."""
        return self._send_command(command)

    def _parse_result(self, data: Dict[str, Any]) -> ExecutionResult:
        """Parse engine response into ExecutionResult."""
        legs = []
        for leg_data in data.get('legs', []):
            legs.append(LegResult(
                dex=leg_data.get('dex', ''),
                input_mint=leg_data.get('inputMint', ''),
                output_mint=leg_data.get('outputMint', ''),
                input_amount=int(leg_data.get('inputAmount', 0)),
                output_amount=int(leg_data.get('outputAmount', 0)),
                price_impact=float(leg_data.get('priceImpact', 0)),
            ))
        
        return ExecutionResult(
            success=data.get('success', False),
            command=data.get('command', ''),
            signature=data.get('signature'),
            legs=legs,
            error=data.get('error'),
            simulation_success=data.get('simulationSuccess'),
            simulation_error=data.get('simulationError'),
            compute_units_used=data.get('computeUnitsUsed'),
            timestamp=int(data.get('timestamp', 0)),
        )

    def health_check(self) -> bool:
        """Check if the engine is available and working."""
        if not self.engine_path.exists():
            return False
        
        result = self._run_engine({"command": "health"})
        return result.get('success', False)

    def get_quotes(self, legs: List[SwapLeg]) -> ExecutionResult:
        """
        Get quotes for multiple swap legs without executing.
        
        Args:
            legs: List of SwapLeg objects
            
        Returns:
            ExecutionResult with quote data for each leg
        """
        command = {
            "command": "quote",
            "legs": [leg.to_dict() for leg in legs],
        }
        
        data = self._run_engine(command)
        return self._parse_result(data)

    def simulate(
        self,
        legs: List[SwapLeg],
        private_key: str,
        priority_fee: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Simulate a multi-leg swap without executing (seatbelt check).
        
        Use this to verify a transaction would succeed before spending gas.
        
        Args:
            legs: List of SwapLeg objects
            private_key: Base58-encoded wallet private key
            priority_fee: Priority fee in microlamports per CU
            
        Returns:
            ExecutionResult with simulation status (no signature)
        """
        Logger.info(f"[EXEC] Simulating {len(legs)}-leg swap (seatbelt check)...")
        
        command = {
            "command": "simulate",
            "legs": [leg.to_dict() for leg in legs],
            "privateKey": private_key,
        }
        
        if priority_fee is not None:
            command["priorityFee"] = priority_fee
        
        data = self._run_engine(command)
        result = self._parse_result(data)
        
        if result.success:
            Logger.info(f"[EXEC] ✅ Simulation passed! CU: {result.compute_units_used}")
        else:
            Logger.warning(f"[EXEC] ⚠️ Simulation failed: {result.simulation_error}")
        
        return result

    def execute_swap(
        self,
        legs: List[SwapLeg],
        private_key: str,
        priority_fee: Optional[int] = None,
        jito_tip_lamports: int = 0,
    ) -> ExecutionResult:
        """
        Execute atomic multi-leg swap.
        
        ⚠️ LIVE EXECUTION - Uses real funds!
        
        Args:
            legs: List of SwapLeg objects (executed atomically)
            private_key: Base58-encoded wallet private key
            priority_fee: Priority fee in microlamports per CU (default: 50,000)
            jito_tip_lamports: Tip for Jito bundles (0 = no tip, 10000+ recommended)
            
        Returns:
            ExecutionResult with transaction signature
        """
        Logger.info(f"[EXEC] Executing {len(legs)}-leg atomic swap...")
        
        command = {
            "command": "swap",
            "legs": [leg.to_dict() for leg in legs],
            "privateKey": private_key,
            "jitoTipLamports": jito_tip_lamports,
        }
        
        if priority_fee is not None:
            command["priorityFee"] = priority_fee
        
        data = self._run_engine(command)
        result = self._parse_result(data)
        
        if result.success:
            Logger.info(f"[EXEC] ✅ Atomic swap success: {result.signature}")
        else:
            Logger.error(f"[EXEC] ❌ Atomic swap failed: {result.error}")
        
        return result

    def atomic_arb(
        self,
        leg1: Dict[str, Any],
        leg2: Dict[str, Any],
        private_key: Optional[str] = None,
        priority_fee: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Execute a two-leg atomic arbitrage.
        
        Convenience method for the common case of buy→sell arb.
        
        Args:
            leg1: First leg dict with keys: dex, pool, inputMint, outputMint, amount
            leg2: Second leg dict with same keys
            private_key: Optional private key (falls back to env var)
            priority_fee: Optional priority fee
            
        Returns:
            ExecutionResult
        """
        # Get private key from env if not provided
        pk = private_key or os.getenv('PHANTOM_PRIVATE_KEY')
        if not pk:
            return ExecutionResult(
                success=False,
                command='swap',
                error='No private key provided or found in PHANTOM_PRIVATE_KEY env var',
            )
        
        legs = [
            SwapLeg(
                dex=leg1['dex'],
                pool=leg1['pool'],
                input_mint=leg1.get('inputMint', leg1.get('input_mint', '')),
                output_mint=leg1.get('outputMint', leg1.get('output_mint', '')),
                amount=leg1['amount'],
                slippage_bps=leg1.get('slippageBps', leg1.get('slippage_bps', 100)),
            ),
            SwapLeg(
                dex=leg2['dex'],
                pool=leg2['pool'],
                input_mint=leg2.get('inputMint', leg2.get('input_mint', '')),
                output_mint=leg2.get('outputMint', leg2.get('output_mint', '')),
                amount=leg2['amount'],
                slippage_bps=leg2.get('slippageBps', leg2.get('slippage_bps', 100)),
            ),
        ]
        
        return self.execute_swap(legs, pk, priority_fee)

    def is_available(self) -> bool:
        """Check if the engine JS file exists."""
        return self.engine_path.exists()


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Unified Execution Bridge Test")
    print("=" * 60)
    
    bridge = ExecutionBridge()
    
    if not bridge.is_available():
        print("❌ Engine not available. Run:")
        print("   cd bridges; npm install; npm run build")
        exit(1)
    
    print("\n1. Health check...")
    if bridge.health_check():
        print("   ✅ Engine is healthy")
    else:
        print("   ❌ Engine health check failed")
    
    print("\n" + "=" * 60)
    print("Test complete!")
