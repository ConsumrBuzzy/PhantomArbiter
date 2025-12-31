"""
After-Action Report (AAR) Generator
===================================
Phase 18: Advanced Command & Control

Generates a detailed session report upon shutdown.
Captures key metrics:
- Session Duration
- Total Cycles Found
- Net Profit (Ghost/Paper)
- Win Rate
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, Any

from src.shared.system.logging import Logger
from src.shared.system.hydration_manager import HydrationManager

class AARGenerator:
    """
    Collects session metrics and generates a JSON report.
    """
    
    def __init__(self, context: Any):
        self.context = context
        self.start_time = time.time()
        self.stats = {
            "cycles_detected": 0,
            "trades_attempted": 0,
            "trades_successful": 0,
            "total_profit_pct": 0.0,
            "net_profit_sol": 0.0, # Estimated
            "ghost_collections": 0
        }
        
    def log_cycle_found(self):
        self.stats["cycles_detected"] += 1
        
    def log_trade_attempt(self):
        self.stats["trades_attempted"] += 1
        
    def log_trade_success(self, profit_pct: float):
        self.stats["trades_successful"] += 1
        self.stats["total_profit_pct"] += profit_pct
        
    def generate_report(self) -> str:
        """
        Generates and saves the AAR. Returns the file path.
        """
        duration = time.time() - self.start_time
        
        report = {
            "mission_id": f"mission_{int(self.start_time)}",
            "timestamp": datetime.now().isoformat(),
            "profile": self.context.strategy_mode,
            "mode": self.context.execution_mode,
            "duration_seconds": duration,
            "metrics": self.stats,
            "performance": {
                "win_rate": (self.stats["trades_successful"] / self.stats["trades_attempted"] * 100) if self.stats["trades_attempted"] > 0 else 0,
                "avg_profit": (self.stats["total_profit_pct"] / self.stats["trades_successful"]) if self.stats["trades_successful"] > 0 else 0
            }
        }
        
        # Ensure reports dir exists
        os.makedirs("reports", exist_ok=True)
        filename = f"reports/aar_{int(self.start_time)}.json"
        
        # Auto-Dehydrate (Nomad Persistence)
        try:
            hydration = HydrationManager()
            archive_path = hydration.dehydrate(context=self.context)
            if archive_path:
                report["archive_path"] = archive_path
        except Exception as e:
            Logger.warning(f"Failed to auto-dehydrate: {e}")
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=4)
            
        return filename
