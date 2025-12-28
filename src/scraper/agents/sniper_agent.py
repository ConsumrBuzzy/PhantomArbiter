
import asyncio
import time
from typing import Dict, Optional, Callable
from src.scraper.agents.base_agent import BaseAgent, AgentSignal
from src.infrastructure.token_scraper import get_token_scraper
from src.core.threshold_manager import get_threshold_manager
from src.shared.system.logging import Logger

class SniperAgent(BaseAgent):
    """
    V68.0/V68.5: Sniper Agent (Fast-Entry Executor)
    
    Role: Execute rapid entries on newly discovered tokens.
    V68.5: Now uses ThresholdManager for dynamic thresholds.
    
    Input: New pool signals from SauronDiscovery
    Output: AgentSignal(SNIPE) for immediate small-size entry
    """
    
    # V68.5: These are now fallbacks - ThresholdManager overrides
    DEFAULT_MIN_LIQUIDITY = 1000.0
    DEFAULT_MAX_AGE = 300
    SNIPE_SIZE_USD = 10.0
    
    def __init__(self, config: Dict = None):
        super().__init__(name="SNIPER", config=config or {})
        self.scraper = get_token_scraper()
        self.pending_snipes: list = []  # Queue of pending snipe opportunities
        self.sniped_mints: set = set()  # Track already-sniped tokens
        self.cooldown_seconds = 60      # Minimum time between snipes on same token
        self.last_snipe_time: Dict[str, float] = {}
        
        Logger.info(f"[{self.name}] Sniper Agent Initialized")

    async def start(self):
        """Start the Sniper Agent."""
        self.running = True
        Logger.info(f"[{self.name}] 🎯 Sniper Ready for Action")

    def stop(self):
        self.running = False
        Logger.info(f"[{self.name}] Sniper Stopped")

    def on_new_pool(self, mint: str, source: str = "UNKNOWN"):
        """
        Callback from SauronDiscovery when a new pool is detected.
        
        Args:
            mint: Token mint address
            source: Platform (PUMPFUN, RAYDIUM, etc.)
        """
        if not self.running:
            return
        
        # Quick dedupe
        if mint in self.sniped_mints:
            return
        
        # Cooldown check
        last_attempt = self.last_snipe_time.get(mint, 0)
        if time.time() - last_attempt < self.cooldown_seconds:
            return
        
        # Queue for processing
        self.pending_snipes.append({
            "mint": mint,
            "source": source,
            "discovered_at": time.time()
        })
        
        Logger.info(f"[{self.name}] 📡 New target queued: {mint[:8]}... from {source}")

    def on_tick(self, market_data: Dict) -> Optional[AgentSignal]:
        """
        Process pending snipe opportunities.
        Called by DataBroker on each tick.
        """
        if not self.running or not self.pending_snipes:
            return None
        
        # Process first pending snipe
        target = self.pending_snipes.pop(0)
        mint = target["mint"]
        source = target["source"]
        discovered_at = target["discovered_at"]
        
        # Lookup token metadata
        info = self.scraper.lookup(mint)
        symbol = info.get("symbol", mint[:8])
        liquidity = info.get("liquidity", 0)
        
        # V68.5: Get dynamic thresholds
        tm = get_threshold_manager()
        min_liquidity = tm.get("sniper_min_liquidity")
        max_age = tm.get("sniper_max_age")
        snipe_confidence = tm.get("sniper_confidence")
        
        # Check age (using dynamic threshold)
        age = time.time() - discovered_at
        if age > max_age:
            Logger.debug(f"[{self.name}] Skipping stale target: {mint[:8]} (age: {age:.0f}s > {max_age:.0f}s)")
            return None
        
        # Safety checks (using dynamic threshold)
        if liquidity < min_liquidity:
            Logger.debug(f"[{self.name}] Skipping {symbol}: Low liquidity (${liquidity:.0f} < ${min_liquidity:.0f})")
            return None
        
        # V69.0: Flash Audit (Score Phase) - Check if Smart Money bought early
        smart_money_boost = 0.0
        try:
            if hasattr(self, 'scout_agent') and self.scout_agent:
                # Quick audit of first buyers
                audit_result = self.scout_agent.flash_audit(mint)
                if audit_result:
                    smart_money_count = audit_result.get("smart_money_count", 0)
                    if smart_money_count >= 2:
                        smart_money_boost = 0.15  # Boost confidence if 2+ Smart Money wallets
                        Logger.info(f"[{self.name}] 🧠 Flash Audit: {smart_money_count} Smart Money wallets! (+{smart_money_boost:.0%} boost)")
                    elif smart_money_count == 0 and audit_result.get("rug_risk", False):
                        Logger.warning(f"[{self.name}] 🚫 VETO: Rug risk detected - skipping {symbol}")
                        return None
        except Exception as e:
            Logger.debug(f"[{self.name}] Flash Audit skipped: {e}")
        
        # Mark as sniped
        self.sniped_mints.add(mint)
        self.last_snipe_time[mint] = time.time()
        
        # Emit SNIPE signal (with Smart Money boost)
        final_confidence = snipe_confidence + smart_money_boost
        Logger.info(f"[{self.name}] 🎯 SNIPE: {symbol} | Liq: ${liquidity:,.0f} | Conf: {final_confidence:.0%} | Source: {source}")
        
        return AgentSignal(
            action="BUY",
            symbol=symbol,
            confidence=final_confidence,
            reason=f"🎯 SNIPE from {source}" + (f" (+SM)" if smart_money_boost else ""),
            metadata={
                "source": "SNIPER",
                "mint": mint,
                "liquidity": liquidity,
                "snipe_size": self.SNIPE_SIZE_USD,
                "smart_money_boost": smart_money_boost
            }
        )

    def get_stats(self) -> Dict:
        """Get sniper statistics."""
        return {
            "pending": len(self.pending_snipes),
            "sniped_count": len(self.sniped_mints),
            "running": self.running
        }
