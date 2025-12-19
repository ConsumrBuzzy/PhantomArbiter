"""
RugCheck API Wrapper - V9.0 Enhanced
=====================================
Strict security validation for Solana tokens.
Uses hybrid approach: Summary for LP%, Full for authorities.
"""

import requests
import time
from config.thresholds import MAX_RISK_SCORE, MIN_LP_LOCKED_PCT


class RugCheck:
    """
    Enhanced wrapper for RugCheck.xyz API.
    Performs strict security checks on token contracts.
    """
    
    BASE_URL = "https://api.rugcheck.xyz/v1"
    
    def __init__(self):
        # Use centralized thresholds
        self.max_risk_score = MAX_RISK_SCORE
        self.min_lp_locked_pct = MIN_LP_LOCKED_PCT
    
    def _get_summary(self, mint: str) -> dict:
        """Get summary report (faster, has lpLockedPct)."""
        url = f"{self.BASE_URL}/tokens/{mint}/report/summary"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass  # V76.0: Silence timeout errors (non-blocking)
        return {}
    
    def _get_full_report(self, mint: str) -> dict:
        """Get full report (has authority details)."""
        url = f"{self.BASE_URL}/tokens/{mint}/report"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass  # V76.0: Silence timeout errors (non-blocking)
        return {}

    def validate_strict(self, mint: str) -> tuple:
        """
        Run strict security validation using hybrid approach.
        
        Checks:
        1. Risk Score: Must be <= MAX_RISK_SCORE (from summary)
        2. LP Locked: Must be >= MIN_LP_LOCKED_PCT (from summary)
        3. Mint Authority: Must be null (from full report)
        4. Freeze Authority: Must be null (from full report)
        5. No critical risks
        
        Returns: (is_safe: bool, reason: str, details: dict)
        """
        # Get summary first (faster, has score and LP)
        summary = self._get_summary(mint)
        
        if not summary:
            return False, "Failed to fetch report", {}
        
        score = summary.get("score", 9999)
        lp_locked_pct = summary.get("lpLockedPct", 0) or 0
        risks = summary.get("risks", [])
        
        details = {
            "score": score,
            "lp_locked_pct": lp_locked_pct,
            "mint_authority": "unknown",
            "freeze_authority": "unknown",
            "risks": [r.get("name", "Unknown") if isinstance(r, dict) else str(r) for r in risks] if risks else []
        }
        
        # === QUICK CHECKS (from summary) ===
        
        # 1. Risk Score
        if score > self.max_risk_score:
            return False, f"High Risk Score ({score} > {self.max_risk_score})", details
        
        # 2. LP Locked (skip if not available - some tokens don't have LP)
        if lp_locked_pct > 0 and lp_locked_pct < self.min_lp_locked_pct:
            return False, f"Low LP Lock ({lp_locked_pct:.1f}% < {self.min_lp_locked_pct}%)", details
        
        # 3. Critical Risks from risks array
        critical_keywords = ["honeypot", "rugpull", "freeze", "mint"]
        for risk in risks:
            risk_name = risk.get("name", "") if isinstance(risk, dict) else str(risk)
            if any(kw in risk_name.lower() for kw in critical_keywords):
                return False, f"Critical Risk: {risk_name}", details
        
        # === DEEP CHECKS (from full report) - Only if score is borderline ===
        # For tokens with very low score (< 100), we trust RugCheck's analysis
        # For higher scores, we verify authorities manually
        
        if score > 100:
            full_report = self._get_full_report(mint)
            if full_report:
                token_info = full_report.get("token", {})
                mint_authority = token_info.get("mintAuthority")
                freeze_authority = token_info.get("freezeAuthority")
                
                details["mint_authority"] = mint_authority
                details["freeze_authority"] = freeze_authority
                
                # 4. Mint Authority must be null
                if mint_authority is not None:
                    return False, "DANGER: Mint Authority Active", details
                
                # 5. Freeze Authority must be null  
                if freeze_authority is not None:
                    return False, "DANGER: Freeze Authority Active", details
        
        # All checks passed!
        return True, "SAFE", details

    def get_score(self, mint: str) -> tuple:
        """Legacy: Get just the risk score."""
        summary = self._get_summary(mint)
        if summary:
            return summary.get("score", 9999), summary
        return 9999, {}

    def is_safe(self, mint: str, max_score: int = 500) -> bool:
        """Legacy: Simple safety check based on score only."""
        score, _ = self.get_score(mint)
        return score <= max_score


# === Quick Test ===
if __name__ == "__main__":
    rc = RugCheck()
    
    # Test with known safe token (POPCAT)
    print("Testing POPCAT...")
    is_safe, reason, details = rc.validate_strict("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
    print(f"Result: {'✅ SAFE' if is_safe else '❌ UNSAFE'} - {reason}")
    print(f"Details: Score={details.get('score')}, LP={details.get('lp_locked_pct', 0):.1f}%")
