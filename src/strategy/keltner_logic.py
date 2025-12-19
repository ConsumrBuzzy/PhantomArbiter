"""
V31.1: Keltner Strategy Logic (V37.0/V70.5 Refactored)
=================================================
Trend/Mean-Reversion strategy using ATR Bands.
V70.5: Adaptive thresholds via ThresholdManager.
"""

from config.settings import Settings
import time
from src.strategy.base_strategy import BaseStrategy
from src.strategy.watcher import Watcher
from src.strategy.risk import PositionSizer
from src.system.logging import Logger
from src.strategy.signals import TechnicalAnalysis as TA

class KeltnerLogic(BaseStrategy):
    """
    V31.1 Logic Engine for Keltner Strategy.
    V37.0: Now inherits from BaseStrategy.
    V70.5: Adaptive thresholds via ThresholdManager.
    """
    
    # V70.5: Base parameters (can be adjusted by ThresholdManager)
    EMA_PERIOD = 20
    ATR_PERIOD = 10
    ATR_MULT_DEFAULT = 2.0
    
    def __init__(self, portfolio):
        super().__init__(portfolio)
        self.market_mode = "KELTNER"
        
    def update_market_mode(self):
        """Standard Win Rate update."""
        if time.time() - self.last_mode_update < 300:
            return
            
        from src.system.db_manager import db_manager
        self.win_rate = db_manager.get_win_rate(limit=20)
        self.last_mode_update = time.time()
        Logger.info(f"🌊 Keltner Mode: EMA 20 / ATR 10 (Win Rate: {self.win_rate*100:.1f}%)")

    def _get_adaptive_atr_mult(self) -> float:
        """
        V70.5: Get adaptive ATR multiplier based on regime.
        Lower multiplier = wider bands = more entries.
        """
        try:
            from src.core.threshold_manager import get_threshold_manager
            tm = get_threshold_manager()
            regime = tm.current_regime
            
            # Adaptive ATR Multiplier:
            # TRENDING_UP: 1.5 (looser - catch dips in uptrend)
            # TRENDING_DOWN: 2.5 (stricter - avoid catching falling knives)
            # CHAOTIC: 3.0 (very strict)
            # RANGING: 1.8 (moderate - mean reversion works well)
            
            if regime == "TRENDING_UP":
                return 1.5
            elif regime == "TRENDING_DOWN":
                return 2.5
            elif regime == "CHAOTIC":
                return 3.0
            else:  # RANGING
                return 1.8
        except:
            return self.ATR_MULT_DEFAULT

    def analyze_tick(self, watcher: Watcher, price: float) -> tuple:
        """
        Analyze a single watcher tick using Keltner logic.
        Returns: (Action, Reason, Size)
        """
        self.update_market_mode()
        
        # V37.0: Use shared cooldown check
        if self.check_cooldown(watcher):
            return 'HOLD', '', 0.0

        # Get history (Raw prices)
        history = list(watcher.data_feed.raw_prices)
        if len(history) < max(self.EMA_PERIOD, self.ATR_PERIOD) + 5:
            return 'HOLD', '', 0.0
            
        # 1. Calculate Indicators
        ema = TA.calculate_ema(history, self.EMA_PERIOD)
        
        # Approximate ATR on simple price stream: Average Absolute Deviation
        tr_list = [abs(history[i] - history[i-1]) for i in range(1, len(history))]
        atr = TA.calculate_ema(tr_list, self.ATR_PERIOD) if tr_list else 0.0
        
        # V70.5: Use adaptive ATR multiplier
        atr_mult = self._get_adaptive_atr_mult()
        lower_band = ema - (atr * atr_mult)
        
        # 2. Check Exits
        if watcher.in_position:
            # V37.0: Use shared TSL check
            triggered, tsl_reason = self.update_trailing_stop(watcher, price)
            if triggered:
                return 'SELL', self.get_net_pnl_reason(watcher, price, tsl_reason), 0.0
                
            # V37.0: Use shared Hard SL check
            sl_hit, sl_reason = self.check_hard_stop_loss(watcher, price)
            if sl_hit:
                return 'SELL', sl_reason, 0.0
                
            # STRATEGY EXIT: Price > EMA (Mean Reversion Complete)
            if price > ema:
                return 'SELL', self.get_net_pnl_reason(watcher, price, "🌊 KELTNER MEAN REVERSION"), 0.0
                
            return 'HOLD', '', 0.0
            
        # 3. Check Entries
        # V70.5: Lower warmup from 30 to 20 for faster activation
        size_usd = self.calculate_position_size(atr)
        if size_usd < 5.0: return 'HOLD', '', 0.0
        if watcher.get_price_count() < 20: return 'HOLD', '', 0.0  # V70.5: Reduced from 30
        if price < Settings.MIN_PRICE_THRESHOLD: return 'HOLD', '', 0.0
        
        if price < lower_band:
            # Oversold!
            info = PositionSizer.get_size_info(atr, size_usd)
            reason = f"🌊 KELTNER ENTRY (Price:{price:.6f} < Low:{lower_band:.6f}) [ATR:{atr_mult:.1f}x] [{info}]"
            return 'BUY', reason, size_usd
            
        return 'HOLD', '', 0.0
