"""
Signal Coordinator
==================
Centralizes external signal ingestion for the Arbiter.

Responsibilities:
1. Manages WSS connection and Log subscriptions (Real-time).
2. Polls SharedPriceCache for Scraper signals (Discovery).
3. Normalizes signals into a unified event stream for the AdaptiveScanner.
"""

import time
import asyncio
from typing import List, Callable, Optional, Dict, Set
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.core.shared_cache import SharedPriceCache
from config.settings import Settings

@dataclass
class CoordinatorConfig:
    wss_enabled: bool = True
    scraper_poll_interval: int = 60
    min_trust_score: float = 0.8
    pairs: List[tuple] = None  # [(symbol, mint, decimal_mint)] for WSS subscription


class SignalCoordinator:
    """
    Orchestrates real-time and polled signals to trigger Arbiter scans.
    """
    
    def __init__(self, config: CoordinatorConfig, on_activity: Callable[[str], None]):
        self.config = config
        self.on_activity = on_activity  # Callback(symbol)
        
        self.wss = None
        self.running = False
        self.last_signal_check = 0.0
        self.monitored_mints: Set[str] = set()
        
        # Track added tokens to avoid spam
        self.dynamic_tokens: Set[str] = set()

    async def start(self):
        """Start signal coordination (WSS + Poller)."""
        self.running = True
        
        # 1. Start WSS if enabled
        if self.config.wss_enabled:
            await self._setup_wss()
            
    async def stop(self):
        """Stop all signal sources."""
        self.running = False
        if self.wss:
            await self.wss.disconnect()
            Logger.info("[SIGNAL] WSS Disconnected")

    async def _setup_wss(self):
        """Initialize WSS and subscribe to initial pairs."""
        try:
            from src.shared.infrastructure.solana_wss import get_solana_wss
            self.wss = get_solana_wss()
            
            if await self.wss.connect():
                Logger.info("[SIGNAL] 🔌 WSS Connected")
                
                # Subscribe to initial pairs
                if self.config.pairs:
                    for pair_tuple in self.config.pairs:
                        await self._subscribe_pair(pair_tuple)
                        
                Logger.info(f"[SIGNAL] 📡 WSS Monitoring {len(self.monitored_mints)} tokens")
        except Exception as e:
            Logger.error(f"[SIGNAL] WSS setup failed: {e}")
            self.wss = None

    async def _subscribe_pair(self, pair_tuple: tuple):
        """Subscribe to logs for a single pair tuple."""
        if not self.wss: return
        
        pair_symbol = pair_tuple[0]
        base_mint = pair_tuple[1]
        
        if base_mint in self.monitored_mints:
            return

        async def make_callback(p_name=pair_symbol):
            async def on_log(result):
                # Trigger callback
                if self.on_activity:
                     # This might run in WSS loop, so simple non-blocking call
                     # If on_activity is sync, just call. If async, create task.
                     # AdaptiveScanner.trigger_activity is sync (just sets var).
                     self.on_activity(p_name)
                     
                     # We assume the caller handles the 'wake event' setting if needed,
                     # or we can accept an Event object.
                     # Better: Arbiter passes a lambda that sets event too.
            return on_log

        callback = await make_callback()
        await self.wss.subscribe_logs([base_mint], callback)
        self.monitored_mints.add(base_mint)

    def poll_signals(self) -> List[tuple]:
        """
        Poll Scraper signals. Returns list of NEW pairs to add to Arbiter config.
        Should be called periodically by the main loop.
        """
        if time.time() - self.last_signal_check < self.config.scraper_poll_interval:
            return []
            
        self.last_signal_check = time.time()
        new_pairs = []
        
        try:
            # Poll Cache
            hot_tokens = SharedPriceCache.get_all_trust_scores(min_score=self.config.min_trust_score)
            
            if not hot_tokens: return []
            
            for symbol, score in hot_tokens.items():
                # Avoid duplicates if we already added it OR if it's in initial list
                # (Caller manages master list, but we track dynamic ones locally to filter)
                if symbol in self.dynamic_tokens: continue
                
                # Resolve Mint
                mint = Settings.ASSETS.get(symbol)
                if not mint: continue
                
                # Check if already monitored (in case it was in initial list)
                if mint in self.monitored_mints: continue
                
                # Found new hot token
                Logger.info(f"[SIGNAL] 🧠 Scraper Found: {symbol} (Trust: {score:.1f})")
                
                # Create pair tuple
                # Assuming USDC quote for now
                usdc_mint = Settings.USDC_MINT
                new_pair = (f"{symbol}/USDC", mint, usdc_mint)
                
                new_pairs.append(new_pair)
                self.dynamic_tokens.add(symbol)
                
                # Auto-subscribe WSS
                if self.wss and self.config.wss_enabled:
                    # We need to run async in sync method?
                    # poll_signals is called from main loop which is async.
                    # Wait, poll_signals is synchronous signature? 
                    # Let's make it async to be safe if we add WSS calls.
                    pass # We will handle WSS sub separately or make this async

        except Exception as e:
            Logger.debug(f"[SIGNAL] Poll error: {e}")
            
        return new_pairs

    async def register_new_pairs(self, new_pairs: List[tuple]):
        """Register new pairs for WSS monitoring."""
        if not new_pairs: return
        
        for pair in new_pairs:
            await self._subscribe_pair(pair)
            
        if new_pairs:
             Logger.info(f"[SIGNAL] 📡 WSS Added {len(new_pairs)} new tokens")
