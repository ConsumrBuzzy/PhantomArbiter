"""
Gatekeeper V9.0 - Enhanced Security & Profitability Filter
===========================================================
The Bouncer: Filters token candidates through strict validation.

Check 1: Security (RugCheck) - Mint/Freeze Authority, LP Lock, Risk Score
Check 2: Profitability (StrategyValidator) - Historical backtest
"""

from src.tools.rugcheck import RugCheck
from src.core.strategy_validator import StrategyValidator
from src.shared.system.logging import Logger

class Gatekeeper:
    """
    V9.0 Gatekeeper: The Bouncer.
    Filters candidates based on:
    1. Security (RugCheck - Strict Mode)
    2. Profitability (Backtest/StrategyValidator)
    """
    
    def __init__(self):
        self.rugcheck = RugCheck()
        self.strategy = StrategyValidator()
        
    def validate_candidate(self, mint: str, symbol: str) -> tuple:
        """
        Perform full due diligence on a candidate.
        
        Args:
            mint: Token mint address
            symbol: Token symbol
            
        Returns: (passed: bool, reason: str, stats: dict)
        """
        Logger.info(f"🛡️ GATEKEEPER: Investigating {symbol} ({mint[:8]}...)...")
        
        # ============================================
        # CHECK 1: SECURITY (RugCheck Strict Mode)
        # ============================================
        is_secure, security_reason, security_details = self.rugcheck.validate_strict(mint)
        
        score = security_details.get("score", "?")
        lp_pct = security_details.get("lp_locked_pct", 0)
        
        # V12.10: Silent Mode (return result only)
        if not is_secure:
            return False, f"Security Fail: {security_reason}", security_details
        
        # ============================================
        # CHECK 2: PROFITABILITY (Strategy Backtest)
        # ============================================
        # The "Time Machine" - fetch history and run backtest
        is_profitable, strategy_stats = self.strategy.validate_buy(symbol, mint=mint)
        
        win_rate = strategy_stats.get("win_rate", 0)
        trade_count = strategy_stats.get("count", 0)
        strategy_reason = strategy_stats.get("reason", "Unknown")
        
        if not is_profitable:
            return False, f"Strategy Fail: {strategy_reason}", {**security_details, **strategy_stats}
        
        # ============================================
        # ALL CHECKS PASSED
        # ============================================
        return True, "ACCEPTED", {
            "score": score,
            "lp_locked_pct": lp_pct,
            "win_rate": win_rate,
            "trade_count": trade_count
        }


# === Quick Test ===
if __name__ == "__main__":
    gk = Gatekeeper()
    
    # Test with known safe token
    print("Testing POPCAT (known safe)...")
    passed, reason, stats = gk.validate_candidate(
        "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", 
        "POPCAT"
    )
    print(f"\nResult: {'✅ PASSED' if passed else '❌ FAILED'}")
    print(f"Reason: {reason}")
    print(f"Stats: {stats}")
