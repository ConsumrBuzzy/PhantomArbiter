"""
Active Coin Auditor - V9.1
===========================
Periodically validates Active coins and demotes underperformers.
Also handles Scout → Active promotion.
"""

import time
import json
import os
from src.core.strategy_validator import StrategyValidator
from src.core.shared_cache import SharedPriceCache
from src.system.logging import Logger
from config.settings import Settings
from config.thresholds import (
    AUDIT_INTERVAL_HOURS, 
    AUDIT_MIN_WIN_RATE,
    PROMOTION_MIN_WIN_RATE,
    PROMOTION_MIN_TRADES
)


class ActiveCoinAuditor:
    """
    V9.1: Periodic health check for Active coins.
    
    - Runs every AUDIT_INTERVAL hours
    - Tests each Active coin's recent profitability
    - Demotes underperformers to WATCH category
    """
    
    WATCHLIST_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/watchlist.json"))
    
    def __init__(self):
        self.strategy = StrategyValidator()
        self.last_audit_time = 0
        # Use centralized thresholds
        self.audit_interval_hours = AUDIT_INTERVAL_HOURS
        self.min_win_rate = AUDIT_MIN_WIN_RATE
        # Promotion thresholds
        self.promotion_min_win_rate = PROMOTION_MIN_WIN_RATE
        self.promotion_min_trades = PROMOTION_MIN_TRADES
        
    def should_run_audit(self) -> bool:
        """Check if enough time has passed since last audit."""
        elapsed = time.time() - self.last_audit_time
        return elapsed >= (self.audit_interval_hours * 3600)
    
    def run_audit(self):
        """Run profitability audit on Active coins and check Scout promotions."""
        Logger.section("📋 COIN AUDIT & PROMOTION")
        self.last_audit_time = time.time()
        
        # Load watchlist
        try:
            with open(self.WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
        except Exception as e:
            Logger.error(f"   Failed to load watchlist: {e}")
            return
        
        assets = data.get("assets", {})
        active_coins = []
        scout_coins = []
        
        # Categorize coins
        for symbol, info in assets.items():
            if isinstance(info, dict):
                cat = info.get("category", "").upper()
                if cat == "ACTIVE":
                    active_coins.append((symbol, info.get("mint")))
                elif cat == "SCOUT":
                    scout_coins.append((symbol, info.get("mint")))
        
        # === PART 1: Audit Active Coins ===
        demoted = []
        passed = []
        
        if active_coins:
            Logger.info(f"   📊 Auditing {len(active_coins)} Active coins...")
            
            for symbol, mint in active_coins:
                is_valid, stats = self.strategy.validate_buy(symbol, mint=mint)
                win_rate = stats.get("win_rate", 0)
                trade_count = stats.get("count", 0)
                
                if win_rate >= self.min_win_rate or trade_count == 0:
                    passed.append(symbol)
                    Logger.info(f"      ✅ {symbol}: WR={win_rate:.1f}% ({trade_count} trades)")
                else:
                    demoted.append(symbol)
                    Logger.warning(f"      ⚠️ {symbol}: WR={win_rate:.1f}% < {self.min_win_rate}% - DEMOTING")
            
            if demoted:
                self._demote_coins(demoted, data)
        
        # === PART 2: Check Scout Promotions ===
        promoted = []
        
        if scout_coins:
            Logger.info(f"   🔭 Checking {len(scout_coins)} Scout coins for promotion...")
            
            for symbol, mint in scout_coins:
                is_valid, stats = self.strategy.validate_buy(symbol, mint=mint)
                win_rate = stats.get("win_rate", 0)
                trade_count = stats.get("count", 0)
                reason = stats.get("reason", "")
                
                # Tier 1: Strict History Check
                if win_rate >= self.promotion_min_win_rate and trade_count >= self.promotion_min_trades:
                    promoted.append(symbol)
                    Logger.success(f"      ⬆️ {symbol}: WR={win_rate:.1f}%, {trade_count} trades - PROMOTING!")
                    continue
                
                # Tier 2: DexScreener Fallback (If Tier 1 failed due to data/age)
                # Allow promotion if Liquidity is healthy (> $50k) even if no history
                try:
                    from src.core.data import DataFeed
                    # Lazy init to avoid blocking backfill
                    feed = DataFeed(mint=mint, symbol=symbol, lazy_init=True)
                    feed.fetch_metadata() # Get latest Liq/Vol from DexScreener
                    
                    liq_usd = feed.liquidity_usd
                    if liq_usd > 50000:
                        promoted.append(symbol)
                        Logger.success(f"      🛡️ {symbol}: Tier 1 Failed ({reason}) but Liquidity ${liq_usd/1000:.0f}k > $50k - PROMOTING (Tier 2)")
                    else:
                        Logger.warning(f"      🔭 {symbol}: Tier 1 Failed & Low Liq (${liq_usd/1000:.0f}k < $50k) - REMAINING IN SCOUT")
                except Exception as e:
                    Logger.warning(f"      ⚠️ {symbol}: Tier 2 Check Failed: {e}")

            if promoted:
                self._promote_coins(promoted, data)
        
        # Summary
        Logger.section(f"📋 AUDIT COMPLETE: Active: {len(passed)} OK, {len(demoted)} Demoted | Scout: {len(promoted)} Promoted")
    
    def _demote_coins(self, symbols: list, data: dict):
        """Demote coins from ACTIVE to WATCH."""
        try:
            for symbol in symbols:
                if symbol in data["assets"]:
                    data["assets"][symbol]["category"] = "WATCH"
                    data["assets"][symbol]["demoted_at"] = time.time()
                    data["assets"][symbol]["demoted_reason"] = "Low Win Rate"
                    Logger.info(f"      → {symbol} moved to WATCH")
            
            with open(self.WATCHLIST_FILE, 'w') as f:
                json.dump(data, f, indent=4)
                
        except Exception as e:
            Logger.error(f"   Failed to demote coins: {e}")

    def _promote_coins(self, symbols: list, data: dict):
        """Promote coins from SCOUT to ACTIVE."""
        try:
            for symbol in symbols:
                if symbol in data["assets"]:
                    data["assets"][symbol]["category"] = "ACTIVE"
                    data["assets"][symbol]["promoted_at"] = time.time()
                    data["assets"][symbol]["trading_enabled"] = True  # Enable trading!
                    Logger.success(f"      → {symbol} PROMOTED to ACTIVE! 🎉")
            
            with open(self.WATCHLIST_FILE, 'w') as f:
                json.dump(data, f, indent=4)
                
        except Exception as e:
            Logger.error(f"   Failed to promote coins: {e}")


# === Quick Test ===
if __name__ == "__main__":
    auditor = ActiveCoinAuditor()
    auditor.run_audit()
