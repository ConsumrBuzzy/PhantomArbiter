"""
Token Grader Module
===================
Scores tokens daily based on RSI signals, volume, price action, and liquidity.
Persists grading history for promotion/demotion decisions.
"""

import json
import os
import time
from datetime import datetime, timedelta
from config.settings import Settings


class TokenGrader:
    """Grades tokens daily and tracks history for automated promotion."""
    
    # Grading weights (must sum to 1.0)
    WEIGHT_RSI_SIGNALS = 0.30
    WEIGHT_VOLUME = 0.25
    WEIGHT_PRICE_ACTION = 0.25
    WEIGHT_LIQUIDITY = 0.20
    
    # Promotion thresholds
    WATCH_TO_SCOUT = 50      # Daily score > 50 for 1 day
    SCOUT_TO_VOLATILE = 70   # Weekly avg > 70
    VOLATILE_TO_ACTIVE = 85  # Score > 85 for 3 consecutive days
    
    # Demotion thresholds
    DEMOTION_THRESHOLD = 20  # Score < 20 for 2 days -> demote
    REMOVAL_DAYS = 7         # No activity for 7 days -> remove from WATCH
    
    def __init__(self):
        self.history_file = os.path.join(
            os.path.dirname(__file__), 
            "../../config/grading_history.json"
        )
        self.history = self._load_history()
    
    def _load_history(self) -> dict:
        """Load grading history from disk."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"   ⚠️ Failed to load grading history: {e}")
        return {}
    
    def _save_history(self):
        """Persist grading history to disk."""
        try:
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"   ⚠️ Failed to save grading history: {e}")
    
    def grade_token(self, symbol: str, metrics: dict) -> float:
        """
        Calculate daily grade (0-100) for a token.
        
        Args:
            symbol: Token symbol
            metrics: {
                "rsi_signals": int,      # Count of RSI < 30 or > 70 in last 24h
                "volume_ratio": float,   # 24h volume / 7d avg volume
                "positive_candles": float, # Ratio of green candles (0-1)
                "liquidity_ratio": float   # Current liquidity / MIN_LIQUIDITY
            }
            
        Returns:
            Score 0-100
        """
        # Normalize each metric to 0-100
        rsi_score = min(100, metrics.get("rsi_signals", 0) * 20)  # 5 signals = 100
        volume_score = min(100, metrics.get("volume_ratio", 0) * 50)  # 2x volume = 100
        action_score = metrics.get("positive_candles", 0.5) * 100  # 0-1 -> 0-100
        liquidity_score = min(100, metrics.get("liquidity_ratio", 0) * 100)  # >= 1 = 100
        
        # Weighted average
        score = (
            rsi_score * self.WEIGHT_RSI_SIGNALS +
            volume_score * self.WEIGHT_VOLUME +
            action_score * self.WEIGHT_PRICE_ACTION +
            liquidity_score * self.WEIGHT_LIQUIDITY
        )
        
        return round(score, 1)
    
    def record_daily_grade(self, symbol: str, score: float, category: str):
        """
        Record a daily grade for a token.
        
        Args:
            symbol: Token symbol
            score: Daily score (0-100)
            category: Current category (WATCH, SCOUT, VOLATILE, ACTIVE)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        if symbol not in self.history:
            self.history[symbol] = {
                "grades": [],
                "category": category,
                "first_seen": today,
                "last_activity": today
            }
        
        # Append today's grade
        self.history[symbol]["grades"].append({
            "date": today,
            "score": score
        })
        
        # Keep only last 30 days
        self.history[symbol]["grades"] = self.history[symbol]["grades"][-30:]
        self.history[symbol]["last_activity"] = today
        self.history[symbol]["category"] = category
        
        self._save_history()
    
    def get_weekly_avg(self, symbol: str) -> float:
        """Get average score over last 7 days."""
        if symbol not in self.history:
            return 0.0
        
        grades = self.history[symbol].get("grades", [])
        recent = grades[-7:]  # Last 7 entries
        
        if not recent:
            return 0.0
        
        return sum(g["score"] for g in recent) / len(recent)
    
    def get_consecutive_days_above(self, symbol: str, threshold: float) -> int:
        """Count consecutive days with score above threshold (from most recent)."""
        if symbol not in self.history:
            return 0
        
        grades = self.history[symbol].get("grades", [])
        consecutive = 0
        
        # Iterate from most recent backwards
        for grade in reversed(grades):
            if grade["score"] >= threshold:
                consecutive += 1
            else:
                break
        
        return consecutive
    
    def get_days_inactive(self, symbol: str) -> int:
        """Get number of days since last activity."""
        if symbol not in self.history:
            return 999
        
        last_activity = self.history[symbol].get("last_activity", "1970-01-01")
        last_date = datetime.strptime(last_activity, "%Y-%m-%d")
        days = (datetime.now() - last_date).days
        
        return days
    
    def check_promotion(self, symbol: str, current_category: str) -> str | None:
        """
        Check if token is eligible for promotion.
        
        Returns:
            New category if promotion eligible, None otherwise.
        """
        if symbol not in self.history:
            return None
        
        grades = self.history[symbol].get("grades", [])
        if not grades:
            return None
        
        latest_score = grades[-1]["score"]
        weekly_avg = self.get_weekly_avg(symbol)
        consecutive_85 = self.get_consecutive_days_above(symbol, self.VOLATILE_TO_ACTIVE)
        
        if current_category == "WATCH":
            if latest_score >= self.WATCH_TO_SCOUT:
                return "SCOUT"
        
        elif current_category == "SCOUT":
            if weekly_avg >= self.SCOUT_TO_VOLATILE:
                return "VOLATILE"
        
        elif current_category == "VOLATILE":
            if consecutive_85 >= 3:
                return "ACTIVE"
        
        return None
    
    def check_demotion(self, symbol: str, current_category: str, held_assets: set = None) -> str | None:
        """
        Check if token should be demoted.
        
        Args:
            symbol: Token symbol
            current_category: Current category
            held_assets: Set of symbols currently held (these CANNOT be demoted)
        
        Returns:
            New category if demotion needed, "REMOVE" for deletion, None otherwise.
        """
        # V6.1: NEVER demote held assets - they must stay ACTIVE until sold
        if held_assets and symbol in held_assets:
            return None
        
        if symbol not in self.history:
            return None
        
        grades = self.history[symbol].get("grades", [])
        days_inactive = self.get_days_inactive(symbol)
        
        # Removal check (WATCH only)
        if current_category == "WATCH" and days_inactive >= self.REMOVAL_DAYS:
            return "REMOVE"
        
        # Demotion check (consecutive low scores)
        if len(grades) >= 2:
            last_two = grades[-2:]
            if all(g["score"] < self.DEMOTION_THRESHOLD for g in last_two):
                if current_category in ["ACTIVE", "VOLATILE", "SCOUT"]:
                    return "WATCH"
        
        return None


# CLI for testing
if __name__ == "__main__":
    grader = TokenGrader()
    
    print("📊 TOKEN GRADER - Test")
    print("=" * 40)
    
    # Test scoring
    test_metrics = {
        "rsi_signals": 3,
        "volume_ratio": 1.5,
        "positive_candles": 0.6,
        "liquidity_ratio": 1.2
    }
    
    score = grader.grade_token("TEST", test_metrics)
    print(f"   Test score: {score}/100")
    
    # Record it
    grader.record_daily_grade("TEST", score, "WATCH")
    print(f"   Recorded to history")
    
    # Check promotion
    promo = grader.check_promotion("TEST", "WATCH")
    print(f"   Promotion eligible: {promo or 'No'}")
