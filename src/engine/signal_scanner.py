"""
V133: SignalScanner - Extracted from TradingCore (SRP Refactor)
================================================================
Encapsulates signal generation logic from watchers.

Responsibilities:
- Scan watchers for buy/sell signals
- Calculate ML confidence scores
- Apply whale vouch bonuses
- Check stop-loss and take-profit exits
- Update app state with pulse data
"""

import time
from typing import Dict, List, Any, Optional

from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.state.app_state import state
from src.strategy.watcher import Watcher


class SignalScanner:
    """
    V133: Generates trading signals from watchers.
    
    This component was extracted from TradingCore to follow SRP.
    It handles all signal generation including ML scoring and exit checks.
    """
    
    def __init__(
        self, 
        engine_name: str,
        decision_engine: Any,
        paper_wallet: Any,
        ml_model: Optional[Any] = None
    ):
        """
        Initialize SignalScanner.
        
        Args:
            engine_name: Identifier for this engine
            decision_engine: DecisionEngine for trade analysis
            paper_wallet: PaperWallet for exit checks
            ml_model: Optional sklearn model for confidence scoring
        """
        self.engine_name = engine_name
        self.decision_engine = decision_engine
        self.paper_wallet = paper_wallet
        self.ml_model = ml_model
        
        # Cached results for status reporting
        self._last_scan_results: Dict = {}
    
    def scan_signals(
        self,
        watchers: Dict[str, Watcher],
        scout_watchers: Dict[str, Watcher],
        data_manager: Any,
        portfolio: Any,
        tick_count: int
    ) -> List[Dict]:
        """
        V45.0: Generate signals without executing them.
        Used by DataBroker to collect and resolve conflicts.
        
        Args:
            watchers: Primary watchers dict
            scout_watchers: Scout watchers dict
            data_manager: DataFeedManager for price updates
            portfolio: PortfolioManager for cash updates
            tick_count: Current tick number
            
        Returns:
            List of signal dicts with action, symbol, price, confidence, etc.
        """
        signals = []
        combined_watchers = {**watchers, **scout_watchers}
        
        # Update prices and portfolio
        portfolio.update_cash(watchers)
        data_manager.update_prices(watchers, scout_watchers)
        
        for symbol, watcher in combined_watchers.items():
            price = watcher.data_feed.get_last_price()
            if price <= 0:
                continue
            
            # Check exits for Paper Wallet assets
            exit_signal = self._check_paper_exits(symbol, watcher, price)
            if exit_signal:
                signals.append(exit_signal)
                continue
            
            # Analyze for new signals
            action, reason, size_usd = self.decision_engine.analyze_tick(watcher, price)
            
            if action in ['BUY', 'SELL']:
                confidence = self._calculate_confidence(watcher, price)
                confidence, reason = self._apply_whale_bonus(watcher, confidence, reason)
                
                signals.append({
                    "engine": self.engine_name,
                    "symbol": symbol,
                    "action": action,
                    "reason": reason,
                    "size_usd": size_usd,
                    "price": price,
                    "confidence": confidence,
                    "watcher": watcher
                })
        
        # Cache results and update state
        self._cache_results(combined_watchers, signals)
        self._update_pulse_state(combined_watchers, signals)
        
        return signals
    
    def _check_paper_exits(
        self, 
        symbol: str, 
        watcher: Watcher, 
        price: float
    ) -> Optional[Dict]:
        """Check stop-loss and take-profit for paper positions."""
        if Settings.ENABLE_TRADING:
            return None
            
        if symbol not in self.paper_wallet.assets:
            return None
            
        asset = self.paper_wallet.assets[symbol]
        entry_price = asset.avg_price or 0.0
        
        if entry_price <= 0:
            return None
            
        current_pnl_pct = (price - entry_price) / entry_price
        
        # Check Stop Loss
        if current_pnl_pct <= Settings.STOP_LOSS_PCT:
            return {
                "engine": self.engine_name,
                "symbol": symbol,
                "action": "SELL",
                "reason": f"🚨 CRITICAL EXIT: TSL HIT (${price:.4f}) (Net: {current_pnl_pct*100:.1f}%)",
                "size_usd": 0,
                "price": price,
                "confidence": 1.0,
                "watcher": watcher
            }
        
        # Check Take Profit
        if current_pnl_pct >= Settings.TAKE_PROFIT_PCT:
            return {
                "engine": self.engine_name,
                "symbol": symbol,
                "action": "SELL",
                "reason": f"💰 TAKE PROFIT (+{current_pnl_pct*100:.2f}%)",
                "size_usd": 0,
                "price": price,
                "confidence": 1.0,
                "watcher": watcher
            }
        
        return None
    
    def _calculate_confidence(self, watcher: Watcher, price: float) -> float:
        """Calculate ML confidence score for a signal."""
        confidence = 0.5  # Default neutral
        
        if not self.ml_model:
            return confidence
            
        try:
            import numpy as np
            rsi = watcher.get_rsi()
            atr = watcher.data_feed.get_atr() if hasattr(watcher.data_feed, 'get_atr') else 0.0
            volatility_pct = (atr / price * 100) if price > 0 else 0.0
            log_liq = np.log1p(watcher.get_liquidity())
            latency = 50
            features = np.array([[rsi, volatility_pct, log_liq, latency]])
            confidence = self.ml_model.predict_proba(features)[0][1]
        except Exception:
            pass
            
        return confidence
    
    def _apply_whale_bonus(
        self, 
        watcher: Watcher, 
        confidence: float, 
        reason: str
    ) -> tuple:
        """V85.1: Apply Whale Vouch Bonus if applicable."""
        try:
            from src.shared.infrastructure.smart_scraper import get_scrape_intelligence
            scrape = get_scrape_intelligence()
            if hasattr(watcher, 'mint') and scrape.has_whale_vouch(watcher.mint):
                bonus = getattr(Settings, 'WHALE_VOUCH_BONUS', 0.15)
                confidence += bonus
                reason = f"🐋 WHALE VOUCHED (+{bonus*100:.0f}%) | {reason}"
        except Exception:
            pass
            
        return confidence, reason
    
    def _cache_results(self, watchers: Dict, signals: List[Dict]) -> None:
        """Cache scan results for status reporting."""
        self._last_scan_results = {
            "tracked": len(watchers),
            "signals": len(signals),
            "best_play": None
        }
        
        # Find best candidate
        best_conf = 0
        best_sym = None
        
        for s in signals:
            if s['confidence'] > best_conf:
                best_conf = s['confidence']
                best_sym = s['symbol']
                
        if best_sym:
            self._last_scan_results['best_play'] = {"symbol": best_sym, "conf": best_conf}
    
    def _update_pulse_state(self, watchers: Dict, signals: List[Dict]) -> None:
        """V90.0: Update app state with pulse data for dashboard."""
        pulse_data = {}
        
        for symbol, watcher in watchers.items():
            price = watcher.get_price()
            rsi = watcher.get_rsi()
            pulse_data[symbol] = {"price": price, "rsi": rsi, "conf": 0.0}
        
        # Merge signal confidences
        for s in signals:
            if s['symbol'] in pulse_data:
                pulse_data[s['symbol']]['conf'] = s['confidence']
                pulse_data[s['symbol']]['action'] = s['action']
        
        state.update_pulse_batch(pulse_data)
    
    def get_status_summary(self) -> str:
        """V89.0: Return a human-readable status pulse."""
        if not self._last_scan_results:
            return "Warming up..."
            
        res = self._last_scan_results
        tracked = res.get('tracked', 0)
        best = res.get('best_play')
        
        pulse = f"Tracking {tracked} assets."
        if best:
            pulse += f" Top Play: {best['symbol']} ({best['conf']*100:.0f}% Conf)."
        else:
            pulse += " Waiting for setup..."
            
        return pulse
