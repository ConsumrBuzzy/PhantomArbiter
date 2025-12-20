"""
Landlord Bridge: Subprocess wrapper for Landlord strategy.

Since driftpy requires Python 3.11 and the main arbiter may run on 3.14,
this bridge calls the Landlord via subprocess using py -3.11.

Usage in Arbiter:
    from src.arbiter.strategies.landlord_bridge import LandlordBridge
    
    landlord = LandlordBridge()
    status = landlord.get_funding_rate()
    result = landlord.tick(inventory_value=100.0)
"""

import subprocess
import json
from typing import Dict, Any, Optional
from src.shared.system.logging import Logger


class LandlordBridge:
    """
    Subprocess bridge to Landlord strategy.
    
    Runs Landlord commands via `py -3.11` to ensure driftpy compatibility.
    """
    
    PYTHON_CMD = "py"
    PYTHON_VERSION = "-3.11"
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._initialized = False
        self._last_status = None
        
    def _run_command(self, code: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Run Python code via subprocess and parse JSON output."""
        if not self.enabled:
            return None
        
        try:
            result = subprocess.run(
                [self.PYTHON_CMD, self.PYTHON_VERSION, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="c:\\Github\\PhantomArbiter"
            )
            
            if result.returncode != 0:
                Logger.debug(f"[LANDLORD-BRIDGE] Error: {result.stderr[:200]}")
                return None
            
            # Parse JSON from stdout (last line)
            output = result.stdout.strip()
            if not output:
                return None
            
            # Find JSON in output (may have logging before it)
            for line in reversed(output.split('\n')):
                line = line.strip()
                if line.startswith('{'):
                    return json.loads(line)
            
            return None
            
        except subprocess.TimeoutExpired:
            Logger.warning("[LANDLORD-BRIDGE] Command timeout")
            return None
        except json.JSONDecodeError as e:
            Logger.debug(f"[LANDLORD-BRIDGE] JSON parse error: {e}")
            return None
        except Exception as e:
            Logger.debug(f"[LANDLORD-BRIDGE] Error: {e}")
            return None
    
    def check_available(self) -> bool:
        """Check if Landlord (driftpy) is available."""
        code = '''
import json
try:
    import driftpy
    print(json.dumps({"available": True, "version": driftpy.__version__}))
except ImportError:
    print(json.dumps({"available": False}))
'''
        result = self._run_command(code)
        return result.get("available", False) if result else False
    
    def get_account_status(self) -> Optional[Dict[str, Any]]:
        """Get Drift account status."""
        code = '''
import asyncio
import json
from src.shared.infrastructure.drift_adapter import DriftAdapter

async def check():
    adapter = DriftAdapter("mainnet")
    await adapter.connect()
    result = await adapter.verify_drift_account()
    return result

result = asyncio.run(check())
print(json.dumps(result))
'''
        return self._run_command(code, timeout=45)
    
    def get_funding_rate(self, symbol: str = "SOL-PERP") -> Optional[Dict[str, Any]]:
        """Get current funding rate."""
        code = f'''
import asyncio
import json
from src.shared.infrastructure.drift_adapter import DriftAdapter

async def check():
    adapter = DriftAdapter("mainnet")
    await adapter.connect()
    result = await adapter.get_funding_rate("{symbol}")
    return result

result = asyncio.run(check())
print(json.dumps(result) if result else "{{}}")
'''
        return self._run_command(code, timeout=30)
    
    def should_hedge(self, inventory_value: float) -> tuple[bool, str]:
        """Check if we should open a hedge."""
        code = f'''
import asyncio
import json
from src.arbiter.strategies.landlord import Landlord

async def check():
    landlord = Landlord()
    await landlord.initialize()
    should, reason = await landlord.should_hedge({inventory_value})
    return {{"should": should, "reason": reason}}

result = asyncio.run(check())
print(json.dumps(result))
'''
        result = self._run_command(code, timeout=45)
        if result:
            return result.get("should", False), result.get("reason", "Unknown")
        return False, "Bridge error"
    
    def open_hedge(self, inventory_value: float) -> Dict[str, Any]:
        """Open a hedge position."""
        code = f'''
import asyncio
import json
from src.arbiter.strategies.landlord import Landlord

async def run():
    landlord = Landlord()
    await landlord.initialize()
    result = await landlord.open_hedge({inventory_value})
    return {{"success": result.get("success"), "error": result.get("error")}}

result = asyncio.run(run())
print(json.dumps(result))
'''
        result = self._run_command(code, timeout=60)
        return result if result else {"success": False, "error": "Bridge error"}
    
    def close_hedge(self, reason: str = "Manual") -> Dict[str, Any]:
        """Close hedge position."""
        code = f'''
import asyncio
import json
from src.arbiter.strategies.landlord import Landlord

async def run():
    landlord = Landlord()
    await landlord.initialize()
    result = await landlord.close_hedge("{reason}")
    return {{"success": result.get("success"), "error": result.get("error"), "pnl": result.get("pnl", 0)}}

result = asyncio.run(run())
print(json.dumps(result))
'''
        result = self._run_command(code, timeout=60)
        return result if result else {"success": False, "error": "Bridge error"}
    
    def get_status_summary(self) -> str:
        """Get one-line status for dashboard."""
        if not self.enabled:
            return "DISABLED"
        
        funding = self.get_funding_rate()
        if not funding:
            return "OFFLINE"
        
        rate = funding.get("rate_hourly", 0)
        is_positive = funding.get("is_positive", False)
        
        if is_positive and rate > 0.005:
            return f"READY ({rate:.3f}%/h)"
        elif is_positive:
            return f"LOW ({rate:.3f}%/h)"
        else:
            return f"NEG ({rate:.3f}%/h)"


# Quick test
if __name__ == "__main__":
    bridge = LandlordBridge()
    
    print("Testing Landlord Bridge...")
    print(f"Available: {bridge.check_available()}")
    
    print("\nAccount Status:")
    status = bridge.get_account_status()
    if status:
        print(f"  Ready: {status.get('ready')}")
        print(f"  Collateral: ${status.get('collateral', 0):.2f}")
    
    print("\nFunding Rate:")
    funding = bridge.get_funding_rate()
    if funding:
        print(f"  Hourly: {funding.get('rate_hourly', 0):.4f}%")
        print(f"  Annual: {funding.get('rate_annual', 0):.1f}%")
        print(f"  Direction: {'Shorts earn' if funding.get('is_positive') else 'Longs earn'}")
