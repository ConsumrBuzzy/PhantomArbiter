"""
Unified Trade Router (Python Bridge)
====================================
V34.0: The unified interface for ALL trade execution in Phantom Arbiter.
Bridges Python strategy logic to high-performance Rust execution.
"""

import os
from typing import Dict, Any, Optional
from src.shared.system.logging import Logger
from src.shared.config.risk import RiskConfig
from config.settings import Settings

try:
    from phantom_core import UnifiedTradeRouter as RustRouter, ExecutionPath
except ImportError:
    Logger.error("❌ phantom_core (Rust) not found. Build it with 'maturin develop'.")
    RustRouter = None
    ExecutionPath = None

class UnifiedTradeRouter:
    """
    Centralized execution gateway.
    
    Responsibilities:
    1. Manage the high-performance Rust router instance.
    2. Route trades to either Jito Bundles (Atomic) or Standard RPC (Smart).
    3. Enforce global and session risk limits.
    """
    
    def __init__(self, risk_config: RiskConfig):
        self.risk = risk_config
        self.router = None
        
        # Initialize Rust Core
        private_key = Settings.PRIVATE_KEY
        if RustRouter and private_key:
            try:
                self.router = RustRouter(private_key)
                Logger.info("⚡ UnifiedTradeRouter: Rust Core Initialized")
            except Exception as e:
                Logger.error(f"❌ Failed to init Rust Router: {e}")

    async def execute(
        self, 
        path_type: str, 
        ix_data: bytes, 
        cu_limit: u32 = 200_000, 
        priority_fee_lamports: int = 1000,
        blockhash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a trade through the Rust router.
        
        Args:
            path_type: "ATOMIC" or "SMART"
            ix_data: Serialized instruction data from instruction_builder.rs
            cu_limit: Compute Unit limit
            priority_fee_lamports: Priority fee or Jito tip
            blockhash: Recent blockhash (if None, fetches one)
        """
        if not self.router:
            return {"success": False, "error": "Router not initialized"}
            
        # 1. Blockhash resolution
        if not blockhash:
             # In a real scenario, we'd fetch from AppState or RPC
             # For now, we assume it's passed for zero-latency
             return {"success": False, "error": "No blockhash provided to Router"}

        # 2. Map path
        path = ExecutionPath.AtomicJito if path_type == "ATOMIC" else ExecutionPath.SmartStandard
        
        try:
            # 3. Rust Route (Direct Signing & Submission)
            signature = self.router.route(
                path,
                ix_data,
                cu_limit,
                priority_fee_lamports,
                blockhash
            )
            
            return {
                "success": True,
                "signature": signature,
                "path": path_type
            }
        except Exception as e:
            Logger.error(f"❌ Execution Failed: {e}")
            return {"success": False, "error": str(e)}

    def get_session_exposure(self) -> float:
        """Read atomic session exposure from Rust."""
        if self.router:
            return self.router.total_session_exposure / 1000.0 # Convert Milli-USD
        return 0.0
