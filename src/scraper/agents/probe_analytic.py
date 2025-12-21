
import time
from typing import Dict, List, Optional
from src.shared.system.logging import Logger

class ProbeAnalytic:
    """
    V100: Whale Probe Detector (Sauron)
    Analyzes transaction clusters for 'Laddered Buys' that precede whale moves.
    """
    
    def __init__(self):
        self.wallet_history: Dict[str, List[Dict]] = {} # {wallet_addr: [{"time": ts, "size": usd}]}
        self.PROBE_THRESHOLD = 200.0 # Max size to be considered a 'probe'
        self.LADDER_COUNT = 3       # Number of buys to trigger
        self.WINDOW_SECONDS = 120   # 2-minute window for clusters
        
    def analyze_tx(self, wallet: str, usd_value: float) -> str:
        """
        Analyze a single transaction for probing patterns.
        Returns "PROBE_DETECTED" or "NORMAL".
        """
        now = time.time()
        
        # We only care about small 'probe-sized' buys
        if usd_value < self.PROBE_THRESHOLD:
            history = self.wallet_history.setdefault(wallet, [])
            
            # Clean old history
            history[:] = [h for h in history if now - h['time'] < self.WINDOW_SECONDS]
            
            history.append({"time": now, "size": usd_value})
            
            # Check for Incrementing Ladder (at least 3 buys)
            if len(history) >= self.LADDER_COUNT:
                # Look at the last 3
                if self._is_ladder(history[-3:]):
                    Logger.info(f"🕵️ [PROBE] Ladder detected from {wallet[:8]} (Sizes: {[h['size'] for h in history[-3:]]})")
                    return "PROBE_DETECTED"
                    
        return "NORMAL"

    def _is_ladder(self, cluster: List[Dict]) -> bool:
        """
        Logic: Sizes must be strictly increasing.
        Example: $15 -> $45 -> $120
        """
        sizes = [c['size'] for c in cluster]
        return sizes[0] < sizes[1] < sizes[2]
