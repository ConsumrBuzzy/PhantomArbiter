"""
PhantomTrader V9.5 - Centralized Thresholds
============================================
All tunable parameters in one place.
"""

# ============================================
# GATEKEEPER / RUGCHECK THRESHOLDS
# ============================================

# RugCheck Security
MAX_RISK_SCORE = 500           # Max acceptable RugCheck score (lower = safer)
MIN_LP_LOCKED_PCT = 50.0       # Minimum LP locked percentage to accept token

# Strategy Validation
MIN_STRATEGY_WIN_RATE = 40.0   # Minimum backtest win rate for new tokens


# ============================================
# AUDITOR THRESHOLDS
# ============================================

AUDIT_INTERVAL_HOURS = 6       # How often to audit Active coins
AUDIT_MIN_WIN_RATE = 35.0      # Min win rate to stay Active (demotion threshold)


# ============================================
# PROMOTION THRESHOLDS (Scout → Active)
# ============================================

PROMOTION_MIN_WIN_RATE = 50.0  # Min win rate to promote Scout → Active
PROMOTION_MIN_TRADES = 3       # Min successful trades before promotion


# ============================================
# WALLET MANAGER (V9.5)
# ============================================

CASH_FLOOR_USD = 5.00          # Minimum USDC reserve (sizer cannot touch)
GAS_FLOOR_SOL = 0.05           # Minimum SOL for gas (triggers alert if below)
DEFAULT_LEGACY_ENTRY_SIZE_USD = 5.00  # Default size for legacy positions missing entry data


# ============================================
# DYNAMIC SIZING (V8.3)
# ============================================

MAX_POSITION_SIZE_PCT = 0.50   # Max % of budget for single trade (default 50%)
BASE_BET_SIZE_USD = 5.00       # Base bet size before win-rate multiplier
WIN_RATE_SCALING = {
    # win_rate_threshold: multiplier
    "hot": (0.60, 1.5),        # 60%+ WR → 150% bet
    "warm": (0.50, 1.2),       # 50%+ WR → 120% bet
    "cold": (0.40, 1.0),       # 40%+ WR → 100% bet (base)
    "freezing": (0.0, 0.5),    # <40% WR → 50% bet
}


# ============================================
# HUNTER / SCRAPER
# ============================================

HUNTER_INTERVAL_SECONDS = 900  # 15 minutes between hunts
MAX_SCOUTS_PER_HUNT = 2        # Max tokens to add per hunt cycle
SCOUT_EXPIRY_HOURS = 48        # Remove Scout tokens older than this


# ============================================
# RISK MANAGEMENT ALERTS
# ============================================

TELEGRAM_ALERTS = {
    "low_gas": True,           # Alert when SOL < GAS_FLOOR
    "low_cash": True,          # Alert when USDC < CASH_FLOOR
    "demotion": True,          # Alert when token demoted
    "promotion": True,         # Alert when Scout promoted
    "new_scout": True,         # Alert when new token discovered
}
