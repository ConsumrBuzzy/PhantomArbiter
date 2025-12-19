"""
V17.0: Longtail Engine Configuration
====================================
Slower timeframe, trend-following parameters.
"""

# Engine Identification
ENGINE_NAME = "LONGTAIL"

# Risk Parameters (Wider for Trend Following)
TAKE_PROFIT_PCT = 0.08    # +8% TP (Higher for longer holds)
STOP_LOSS_PCT = -0.05     # -5% SL (Wider to avoid noise)

# TSL Parameters (Overridden in main_v7.py but can be changed here)
TSL_ACTIVATION_PCT = 0.03  # +3% activates trailing stop
TSL_TRAIL_PCT = 0.04       # 4% trailing distance
