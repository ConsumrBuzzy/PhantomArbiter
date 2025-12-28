"""
V133: EngineManager - Extracted from DataBroker (SRP Refactor)
=============================================================
Orchestrates the lifecycle and initialization of trading engines and agents.

Responsibilities:
- Initialize the Unified Merchant Engine (MerchantEnsemble)
- Initialize Auxiliary Agents (Scout, Whale Watcher, Sauron, Sniper)
- Manage engine state and provide unified access
"""

from typing import Dict, Any
from config.settings import Settings
from src.shared.system.logging import Logger
from src.engine.trading_core import TradingCore


class EngineManager:
    """
    V133: Manages the initialization and references for all trading components.
    
    This component encapsulates the "Mind" initialization from DataBroker.
    """
    
    def __init__(self):
        self.merchant_engines: Dict[str, TradingCore] = {}
        self.scout_agent = None
        self.whale_watcher = None
        self.sauron = None
        self.sniper = None
        self.bitquery_adapter = None
        
    def initialize_all(self):
        """Initialize all engines and agents."""
        self._init_auxiliary_agents()
        self._init_merchant_engines()
        self._init_bitquery_adapter()
        
    def _init_merchant_engines(self):
        """V45.0: Initialize the Unified Merchant Engine (Ensemble Strategy)."""
        try:
            from src.strategy.ensemble import MerchantEnsemble
            
            # The Unified Merchant
            merchant = TradingCore(strategy_class=MerchantEnsemble, engine_name="MERCHANT")
            self.merchant_engines["MERCHANT"] = merchant
            
            Logger.info("✅ [ENGINE_MGR] Unified Merchant Engine Initialized")
            
        except Exception as e:
            Logger.critical(f"🛑 [ENGINE_MGR] Failed to init Merchant Engines: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _init_auxiliary_agents(self):
        """Initialize Scout, Whale, Sauron, Sniper agents."""
        try:
            from src.scraper.agents.scout_agent import ScoutAgent
            from src.scraper.agents.whale_watcher_agent import WhaleWatcherAgent
            from src.scraper.discovery.sauron_discovery import SauronDiscovery
            from src.scraper.agents.sniper_agent import SniperAgent
            
            self.scout_agent = ScoutAgent()
            self.whale_watcher = WhaleWatcherAgent()
            self.sauron = SauronDiscovery()
            self.sniper = SniperAgent()
            
            Logger.info("✅ [ENGINE_MGR] Auxiliary Agents (Scout, Whale, Sauron, Sniper) Initialized")
        except Exception as e:
            Logger.error(f"[ENGINE_MGR] Failed to init auxiliary agents: {e}")

    def _init_bitquery_adapter(self):
        """Initialize Bitquery adapter if API key is present."""
        if Settings.BITQUERY_API_KEY:
            try:
                from src.shared.infrastructure.bitquery_adapter import BitqueryAdapter
                self.bitquery_adapter = BitqueryAdapter()
                Logger.info("🔌 [ENGINE_MGR] Bitquery Adapter Configured")
            except ImportError:
                 Logger.warning("⚠️ [ENGINE_MGR] Bitquery Adapter Import Failed")
        
    def execute_signals(self, signals):
        """Relay signals to all active merchant engines."""
        for sig in signals:
            for engine in self.merchant_engines.values():
                engine.execute_signal(sig)
