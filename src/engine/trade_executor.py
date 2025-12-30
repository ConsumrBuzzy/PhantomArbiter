"""
V48.0: Trade Executor Module
============================
Extracted from trading_core.py to improve SRP compliance.

Handles:
- Buy/sell order execution
- Pre-flight checks (cash, gas, liquidity, position limits)
- ML predictive filtering
- Paper trading simulation (slippage, delays, failures)

Dependencies are injected via __init__ for testability.
"""

import time
import random
from typing import Dict, Optional, Tuple, Any, TYPE_CHECKING
from dataclasses import dataclass

from config.settings import Settings
from src.shared.system.priority_queue import priority_queue
from src.shared.system.logging import Logger

if TYPE_CHECKING:
    from src.strategy.watcher import Watcher
    from src.shared.execution.paper_wallet import PaperWallet
    from src.shared.system.capital_manager import CapitalManager
    from src.shared.infrastructure.validator import TokenValidator
    from src.core.prices.pyth_adapter import PythAdapter, PythPrice
    from src.shared.infrastructure.jito_adapter import JitoAdapter
    from src.shared.execution.execution_backend import ExecutionBackend
    from src.engine.slippage_calibrator import SlippageCalibrator


@dataclass
class ExecutionResult:
    """Result of a trade execution attempt."""
    success: bool
    message: str
    tx_id: Optional[str] = None
    pnl_usd: Optional[float] = None


class TradeExecutor:
    """
    V48.0: Dedicated trade execution handler.
    
    Extracted from TradingCore to isolate execution logic and improve testability.
    All dependencies are injected for flexibility and testing.
    """
    
    # ML filter threshold
    # V85.0: Use aggressive threshold in paper mode
    @property
    def ML_THRESHOLD(self):
        if not self.live_mode and getattr(Settings, 'PAPER_AGGRESSIVE_MODE', False):
            return getattr(Settings, 'PAPER_ML_THRESHOLD', 0.45)
        return 0.65
    
    def __init__(
        self,
        engine_name: str,
        capital_mgr: 'CapitalManager',
        paper_wallet: 'PaperWallet',
        swapper: Any,
        portfolio: Any,
        ml_model: Optional[Any] = None,
        watchers: Optional[Dict] = None,
        scout_watchers: Optional[Dict] = None,
        validator: Optional['TokenValidator'] = None,
        pyth_adapter: Optional['PythAdapter'] = None,
        jito_adapter: Optional['JitoAdapter'] = None,
        execution_backend: Optional['ExecutionBackend'] = None
    ):
        """
        Initialize TradeExecutor with all required dependencies.
        
        Args:
            engine_name: Unique identifier for this engine
            capital_mgr: Centralized capital management
            paper_wallet: Paper trading wallet
            swapper: Jupiter swap executor
            portfolio: Portfolio manager for locks
            ml_model: Optional ML predictive filter
            watchers: Dict of active watchers (for price lookups)
            scout_watchers: Dict of scout watchers
            validator: Optional TokenValidator for safety checks
        """
        self.engine_name = engine_name
        self.capital_mgr = capital_mgr
        self.paper_wallet = paper_wallet
        self.swapper = swapper
        self.portfolio = portfolio
        self.ml_model = ml_model
        self.watchers = watchers or {}
        self.scout_watchers = scout_watchers or {}
        self.validator = validator
        self.pyth_adapter = pyth_adapter
        self.jito_adapter = jito_adapter
        self.live_mode = getattr(Settings, 'ENABLE_TRADING', False)
        
        # V48.0: Price divergence tolerance
        self.PRICE_DIVERGENCE_TOLERANCE = 0.005  # 0.5%
        
        # V48.0: Jito settings
        self.JITO_ENABLED = getattr(Settings, 'JITO_ENABLED', True)
        self.JITO_TIP_LAMPORTS = getattr(Settings, 'JITO_TIP_LAMPORTS', 10000)
        
        # V49.0: Unified Execution Backend (Paper/Live parity)
        self.execution_backend = execution_backend
        
        # V67.0: Auto-Slippage Calibrator (Phase 5C)
        self.slippage_calibrator: Optional['SlippageCalibrator'] = None
        
        # Tracking
        self._last_paper_pnl = 0.0
        self.consecutive_losses = 0
    
    def update_watchers(self, watchers: Dict, scout_watchers: Dict) -> None:
        """Update watcher references (called from TradingCore)."""
        self.watchers = watchers
        self.scout_watchers = scout_watchers
    
    def update_ml_model(self, ml_model: Any) -> None:
        """Hot-reload ML model."""
        self.ml_model = ml_model
    
    # ═══════════════════════════════════════════════════════════════════
    # PRE-FLIGHT CHECKS
    # ═══════════════════════════════════════════════════════════════════
    
    def _check_preflight_buy(self, watcher: 'Watcher', size_usd: float) -> Tuple[bool, str]:
        """
        V39.4: Pre-flight checks for buy orders.
        V48.0: Added Token-2022 safety check.
        V85.0: Aggressive paper mode with looser thresholds.
        
        Returns:
            (can_execute, reason)
        """
        # V85.0: Check if in aggressive paper mode
        # V89.14: Diagnostic logging disabled
        is_paper_aggressive = False
        
        # V48.0: Token-2022 Safety Check
        if self.validator and hasattr(watcher, 'mint'):
            if self.validator.is_token_2022(watcher.mint):
                # V85.0: Allow Token-2022 in aggressive paper mode
                if is_paper_aggressive and getattr(Settings, 'PAPER_ALLOW_TOKEN_2022', False):
                    pass  # Allow it with warning logged elsewhere
                else:
                    if is_paper_aggressive:
                        print(f"      ❌ Pre-flight FAILED: Token-2022 (unsupported)")
                    return False, "Token-2022 (unsupported)"
        
        # 1. Check Cash Balance (Paper Trading)
        if not self.live_mode:
            min_buy_size = 2.0
            if is_paper_aggressive:
                print(f"      🔍 Cash Check: ${self.paper_wallet.cash_balance:.2f} >= ${min_buy_size}? {self.paper_wallet.cash_balance >= min_buy_size}")
            if self.paper_wallet.cash_balance < min_buy_size:
                if is_paper_aggressive:
                    print(f"      ❌ Pre-flight FAILED: Insufficient cash (${self.paper_wallet.cash_balance:.2f} < ${min_buy_size})")
                return False, "Insufficient cash"
        
        # 2. Check Gas Balance
        if not self.live_mode:
            min_gas = 0.005
            if is_paper_aggressive:
                print(f"      🔍 Gas Check: {self.paper_wallet.sol_balance:.4f} SOL >= {min_gas}? {self.paper_wallet.sol_balance >= min_gas}")
            if self.paper_wallet.sol_balance < min_gas:
                refilled = self.paper_wallet.ensure_gas(min_sol=0.01)
                if not refilled or self.paper_wallet.sol_balance < min_gas:
                    if is_paper_aggressive:
                        print(f"      ❌ Pre-flight FAILED: Insufficient SOL for gas ({self.paper_wallet.sol_balance:.4f} < {min_gas})")
                    return False, "Insufficient SOL for gas"
        
        # 3. Liquidity Gate
        # V85.0: Use lower threshold in aggressive paper mode
        min_liq = getattr(Settings, 'PAPER_MIN_LIQUIDITY', 100000) if is_paper_aggressive else 100000
        liq = watcher.get_liquidity()
        if is_paper_aggressive:
            print(f"      🔍 Liquidity Check: ${liq:,.0f} >= ${min_liq:,.0f}? {liq >= min_liq or liq == 0}")
        if liq > 0 and liq < min_liq:
            if is_paper_aggressive:
                print(f"      ❌ Pre-flight FAILED: Low Liquidity ${liq/1000:.1f}k < ${min_liq/1000:.0f}k")
            return False, f"Low Liquidity ${liq/1000:.1f}k < ${min_liq/1000:.0f}k"
        
        # 4. Position Limit
        max_positions = getattr(Settings, 'MAX_POSITIONS_PER_ENGINE', 999)
        open_count = len(self.paper_wallet.assets) if hasattr(self, 'paper_wallet') else 0
        if is_paper_aggressive:
            print(f"      🔍 Position Limit: {open_count} < {max_positions}? {open_count < max_positions}")
        if open_count >= max_positions:
            if is_paper_aggressive:
                print(f"      ❌ Pre-flight FAILED: MAX_POSITIONS ({open_count}/{max_positions})")
            return False, f"MAX_POSITIONS ({open_count}/{max_positions})"
        
        if is_paper_aggressive:
            print(f"      ✅ Pre-flight PASSED: All checks OK")
        
        return True, "OK"
    
    def _check_price_divergence(self, watcher: 'Watcher', signal_price: float) -> Tuple[bool, str, float]:
        """
        V48.0: Validate price consistency between data sources.
        
        Compares Pyth (fast) vs signal price (DexScreener) to detect
        stale or manipulated data.
        
        Args:
            watcher: Token watcher with symbol
            signal_price: Price from DexScreener/primary source
            
        Returns:
            (is_valid, reason, pyth_price) - pyth_price is 0.0 if unavailable
        """
        if not self.pyth_adapter:
            return True, "No Pyth adapter", 0.0
        
        symbol = getattr(watcher, 'symbol', '')
        if not self.pyth_adapter.has_feed(symbol):
            # Token not on Pyth - skip check (meme tokens)
            return True, "No Pyth feed", 0.0
        
        try:
            pyth_price = self.pyth_adapter.fetch_single(symbol)
            if not pyth_price:
                return True, "Pyth fetch failed", 0.0
            
            # Check for stale data
            if pyth_price.is_stale:
                priority_queue.add(3, 'LOG', {
                    'level': 'WARNING',
                    'message': f"⚠️ [PYTH] {symbol} price is stale"
                })
            
            # Calculate divergence
            divergence = abs(pyth_price.price - signal_price) / signal_price
            
            if divergence > self.PRICE_DIVERGENCE_TOLERANCE:
                msg = f"Price divergence {divergence*100:.2f}% (Pyth: ${pyth_price.price:.4f} vs Signal: ${signal_price:.4f})"
                priority_queue.add(2, 'LOG', {
                    'level': 'WARNING',
                    'message': f"⚠️ [DIVERGENCE] {symbol}: {msg}"
                })
                return False, msg, pyth_price.price
            
            # Log confidence for ML
            if pyth_price.confidence_pct < 0.1:
                priority_queue.add(4, 'LOG', {
                    'level': 'DEBUG',
                    'message': f"🎯 [PYTH] {symbol}: High confidence ({pyth_price.confidence_pct:.4f}%)"
                })
            
            return True, "OK", pyth_price.price
            
        except Exception as e:
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"⚠️ [PYTH] {symbol} check failed: {e}"
            })
            return True, str(e), 0.0  # Fail open
            
    def _check_stop_loss(self, watcher: 'Watcher', current_price: float) -> Tuple[bool, str, float]:
        """
        V53.0: Check for Stop Loss or Trailing Stop trigger.
        
        Returns:
            (should_exit, reason, exit_price)
        """
        # 1. Hard Stop Loss
        entry_price = watcher.entry_price
        if entry_price > 0:
            sl_pct = Settings.STOP_LOSS_PCT  # e.g. -0.05
            hard_stop_price = entry_price * (1 + sl_pct)
            
            if current_price < hard_stop_price:
                return True, f"HARD STOP ({sl_pct*100:.1f}%)", current_price
        
        # 2. Trailing Stop Loss (High Volatility)
        # Only applicable if we are in profit or near breakeven logic
        if hasattr(watcher, 'max_price_achieved') and watcher.max_price_achieved > entry_price:
            trailing_clawback_pct = 0.15 # V53.0: Tight 15% trail from peak for bonding curves
            
            # Dynamic trail based on volatility could be added here
            trail_price = watcher.max_price_achieved * (1 - trailing_clawback_pct)
            
            if current_price < trail_price and current_price > entry_price:
                # We are still in profit but dropped from peak
                return True, f"TRAILING STOP (-{trailing_clawback_pct*100:.0f}% from High)", current_price
                
        return False, "", 0.0

    def _apply_ml_filter(self, watcher: 'Watcher', price: float, liq: float) -> Tuple[bool, float]:
        """
        V36.0: Apply ML predictive filter.
        
        Returns:
            (passed, probability)
        """
        if self.ml_model is None:
            return True, 0.5  # No model = pass by default
        
        try:
            import numpy as np
            import time
            from src.strategy.signals import TechnicalAnalysis
            
            # 1. Base Metrics
            prices = [p[1] for p in watcher.data_feed.raw_prices] if hasattr(watcher.data_feed, 'raw_prices') else []
            timestamps = [p[0] for p in watcher.data_feed.raw_prices] if hasattr(watcher.data_feed, 'raw_prices') else []
            
            current_price = prices[-1] if prices else price
            
            # RSI (Classic)
            rsi = TechnicalAnalysis.calculate_rsi(prices)
            
            # V62.0 Feature: RSI Delta (Momentum Acceleration)
            # RSI now - RSI 5 mins ago
            rsi_delta = 0.0
            if len(timestamps) > 20: 
                # Find index ~5 mins ago
                cutoff_ts = time.time() - 300
                # Fast search (assuming sorted)
                idx = -1
                for i in range(len(timestamps)-1, -1, -1):
                   if timestamps[i] < cutoff_ts:
                       idx = i
                       break
                
                if idx > 14: # Need enough data for RSI
                    past_rsi = TechnicalAnalysis.calculate_rsi(prices[:idx+1])
                    rsi_delta = rsi - past_rsi
            
            # V62.0 Feature: Spread Variance (Volatility Proxy) & Bar Pressure (OBI Proxy)
            # Construct synthetic 1-minute candle
            spread_var = 0.0
            bar_pressure = 0.0
            
            candle_window = 60 # 1 minute
            window_start = time.time() - candle_window
            
            # Get ticks in last minute
            recent_ticks = [p for i, p in enumerate(prices) if timestamps[i] > window_start]
            
            if len(recent_ticks) > 0:
                 open_p = recent_ticks[0]
                 close_p = recent_ticks[-1]
                 high_p = max(recent_ticks)
                 low_p = min(recent_ticks)
                 
                 # Spread Variance: (High - Low) / Open
                 spread_var = ((high_p - low_p) / open_p) * 100
                 
                 # Bar Pressure: (Close - Open) / (High - Low)
                 rng = high_p - low_p
                 if rng > 0:
                     bar_pressure = (close_p - open_p) / rng
            
            log_liq = np.log1p(liq)
            latency = 50 # Placeholder or fetch from latency stats
            
            # V62.0: Feature Vector (6 Features)
            # [close, rsi, rsi_delta, bar_pressure, spread_var, log_liquidity, latency] 
            # Note: FeatureGenerator doesn't use Close in X usually, just for labeling.
            # Generator output: [['close', 'rsi', 'rsi_delta', 'bar_pressure', 'spread_var', 'target']]
            # Wait, FeatureGenerator creates features in specific Loop order. 
            # features = [rsi, rsi_delta, spread_var, log_liq, bar_pressure, latency] ?
            # Let's align with FeatureGenerator.create_features columns implicitly or explicitly.
            # Generator code:
            # candles['rsi'] = ...
            # candles['rsi_delta'] = ...
            # candles['spread_var'] = ...
            # candles['log_liquidity'] = ...
            # candles['bar_pressure'] = ...
            # candles['latency_smooth'] = ...
            # And Model usually trained on a subset.
            # Assuming typically: [rsi, rsi_delta, bar_pressure, spread_var, log_liq, latency]
            
            features_v62 = np.array([[rsi, rsi_delta, bar_pressure, spread_var, log_liq, latency]])
            
            # Fallback for V36 Model (4 Features: RSI, Vol, Liq, Latency)
            # Reusing spread_var as volatility_pct since they are similar ((H-L)/O)
            features_v36 = np.array([[rsi, spread_var, log_liq, latency]])

            try:
                # Try new features first
                prob = self.ml_model.predict_proba(features_v62)[0][1]
            except (ValueError, AttributeError):
                # Fallback to old shape if model not retrained
                prob = self.ml_model.predict_proba(features_v36)[0][1]
            
            if prob < self.ML_THRESHOLD:
                return False, prob
            return True, prob
            
        except Exception as e:
            # Logger.debug(f"ML Filter Error: {e}")
            return True, 0.5  # Fail open
    
    def _check_congestion(self, watcher: 'Watcher') -> Tuple[bool, float, int]:
        """
        V26.1: Check for network congestion based on volatility.
        
        Returns:
            (is_congested, failure_rate, delay_max_ms)
        """
        failure_rate = Settings.TRANSACTION_FAILURE_RATE_PCT
        delay_max = Settings.EXECUTION_DELAY_MAX_MS
        is_congested = False
        
        try:
            if len(watcher.data_feed.raw_prices) > 5:
                current_p = watcher.data_feed.raw_prices[-1][1]
                past_p = watcher.data_feed.raw_prices[-5][1]
                vol_change = abs((current_p - past_p) / past_p)
                if vol_change > Settings.HIGH_VOLATILITY_THRESHOLD_PCT:
                    is_congested = True
                    failure_rate = Settings.CONGESTION_FAILURE_RATE_PCT
                    delay_max = Settings.CONGESTION_DELAY_MAX_MS
        except:
            pass
        
        return is_congested, failure_rate, delay_max
    
    def _get_execution_price(self, watcher: 'Watcher', signal_price: float, delay_ms: int) -> float:
        """
        V21.1: Get execution price after latency delay.
        
        Returns:
            Execution price (may differ from signal price due to latency)
        """
        try:
            if hasattr(watcher, 'data_feed') and watcher.data_feed:
                latest_price = watcher.data_feed.get_price()
                if latest_price and latest_price > 0:
                    slippage_pct = ((latest_price - signal_price) / signal_price) * 100
                    if abs(slippage_pct) > 0.01:
                        direction = "📈" if slippage_pct > 0 else "📉"
                        priority_queue.add(3, 'LOG', {
                            'level': 'INFO', 
                            'message': f"{direction} [LATENCY SLIP] {watcher.symbol}: {slippage_pct:+.2f}% ({delay_ms}ms delay)"
                        })
                    return latest_price
        except Exception:
            pass
        return signal_price
    
    # ═══════════════════════════════════════════════════════════════════
    # BUY EXECUTION
    # ═══════════════════════════════════════════════════════════════════
    
    def execute_buy(
        self,
        watcher: 'Watcher',
        price: float,
        reason: str,
        size_usd: float,
        decision_engine: Optional[Any] = None
    ) -> ExecutionResult:
        """
        Execute a buy order with pre-flight checks and ML filtering.
        
        Args:
            watcher: Token watcher
            price: Signal price
            reason: Buy reason
            size_usd: Requested position size
            decision_engine: Optional decision engine for cooldown
            
        Returns:
            ExecutionResult with success status and details
        """
        # V134: Null safety for price
        if price is None or price <= 0:
            price = watcher.get_price() if hasattr(watcher, 'get_price') else 0.0
            if price is None or price <= 0:
                return ExecutionResult(False, "No valid price for buy")
        
        # Pre-flight checks
        can_execute, preflight_reason = self._check_preflight_buy(watcher, size_usd)
        if not can_execute:
            return ExecutionResult(False, preflight_reason)
            
        # -------------------------------------------------------------------
        # V63.0: SIMULATION INTERCEPT
        # -------------------------------------------------------------------
        if getattr(Settings, 'DRY_RUN', False):
            # Calculate confidence explicitly or pass it in? 
            # execute_buy doesn't take confidence. ml_prob is calc'd below.
            # We'll calculate ML filter first to be realistic.
            pass

        # Liquidity for ML
        liq = watcher.get_liquidity()
        
        # V89.14: Check if in paper aggressive mode
        # V89.14: Diagnostic logging disabled
        is_paper_aggressive = False
        
        # ML Filter
        ml_passed, ml_prob = self._apply_ml_filter(watcher, price, liq)
        
        if is_paper_aggressive:
            print(f"      🧠 ML Filter: Prob={ml_prob:.1%} vs Threshold={self.ML_THRESHOLD:.0%} → {'PASS' if ml_passed else 'FAIL'}")
        
        # V89.14: Skip ML filter in paper aggressive mode
        if not ml_passed and not is_paper_aggressive:
            msg = f"ML REJECT: {watcher.symbol} Prob={ml_prob:.1%} < {self.ML_THRESHOLD:.0%}"
            if is_paper_aggressive:
                print(f"      ❌ ML REJECTED (but bypassed in paper mode)")
            priority_queue.add(2, 'LOG', {'level': 'INFO', 'message': f"🧠 {msg}"})
            return ExecutionResult(False, msg)
        elif not ml_passed and is_paper_aggressive:
            print(f"      ⚠️ ML would reject, but bypassing in PAPER_AGGRESSIVE_MODE")
            
        if getattr(Settings, 'DRY_RUN', False):
            if is_paper_aggressive:
                print(f"      🎭 DRY_RUN mode intercepting - simulated trade only (DB logging)")
            try:
                # V63.1: Log to DB
                self._log_simulated_trade("BUY", watcher.symbol, size_usd, price, reason, ml_prob)
            except Exception as e:
                import traceback
                traceback.print_exc()

            
            watcher.last_signal_time = time.time()
            return ExecutionResult(True, f"SIMULATED BUY {watcher.symbol}", "sim_tx_id")
        
        # Global Lock
        if is_paper_aggressive:
            print(f"      🔐 Requesting portfolio lock...")
        if not self.portfolio.request_lock(watcher.symbol):
            if is_paper_aggressive:
                print(f"      ❌ Lock unavailable!")
            return ExecutionResult(False, "Lock unavailable")
        if is_paper_aggressive:
            print(f"      ✅ Lock acquired")
        
        # Log execution attempt
        mode_prefix = "LIVE" if self.live_mode else "MOCK"
        icon = "🚀" if self.live_mode else "🔧"
        priority_queue.add(2, 'LOG', {
            'level': 'INFO', 
            'message': f"{icon} EXECUTING {mode_prefix} BUY: {watcher.symbol} (${size_usd:.2f})"
        })
        
        tx_id = None
        
        if self.live_mode:
            # LIVE EXECUTION
            tx_id = self.swapper.execute_swap(
                direction="BUY",
                amount_usd=size_usd,
                reason=reason,
                target_mint=watcher.mint
            )
        else:
            # PAPER EXECUTION
            if is_paper_aggressive:
                print(f"      📝 Calling _execute_paper_buy()...")
            tx_id = self._execute_paper_buy(watcher, price, reason, liq, decision_engine, size_usd=size_usd)
            if is_paper_aggressive:
                print(f"      📋 Paper buy returned: {tx_id}")
        
        if tx_id:
            # Success path
            time.sleep(2)  # Execution pacing
            
            # V51.0: Use Template
            from src.shared.system.telegram_templates import TradeTemplates
            msg = TradeTemplates.entry(
                symbol=watcher.symbol,
                action="BUY",
                amount=size_usd,
                price=price,
                engine=self.engine_name,
                reason=reason
            )
            
            from src.shared.system.comms_daemon import send_telegram
            tg_priority = "HIGH" if Settings.ENABLE_TRADING else "LOW"
            send_telegram(msg, source="PRIMARY", priority=tg_priority)
            
            # Log success
            Logger.success(f"[{self.engine_name}] 🚀 BUY COMPLETE: {watcher.symbol} Tx:{tx_id}")
            time.sleep(1)
            
            watcher.enter_position(price, size_usd)
            watcher.last_signal_time = time.time()
            
            return ExecutionResult(True, f"BUY {watcher.symbol}", tx_id)
        else:
            self.portfolio.release_lock()
            priority_queue.add(2, 'LOG', {'level': 'ERROR', 'message': f"BUY FAILED: {watcher.symbol}"})
            return ExecutionResult(False, "Execution failed")
    
    def _execute_paper_buy(
        self,
        watcher: 'Watcher',
        price: float,
        reason: str,
        liq: float,
        decision_engine: Optional[Any],
        size_usd: float = 0.0  # V135: Accept passed size
    ) -> Optional[str]:
        """
        Execute paper buy with realistic simulation.
        
        Returns:
            Mock transaction ID or None on failure
        """
        tx_id = f"MOCK_TX_BUY_{int(time.time())}"
        
        # Position sizing
        current_price_map = {}
        for s, w in {**self.watchers, **self.scout_watchers}.items():
            current_price_map[s] = w.get_price()
        
        total_equity = self.paper_wallet.get_total_value(current_price_map)
        
        # V135: Use passed size if available, else derive
        if size_usd > 0:
            calculated_size = size_usd
        else:
            # Fallback to internal risk calc
            risk_amount = total_equity * Settings.RISK_PER_TRADE_PCT
            sl_dist_pct = abs(Settings.STOP_LOSS_PCT)
            if sl_dist_pct == 0: sl_dist_pct = 0.03
            calculated_size = risk_amount / sl_dist_pct
            
        max_allowed = total_equity * Settings.MAX_CAPITAL_PER_TRADE_PCT
        final_size = min(calculated_size, max_allowed, self.paper_wallet.cash_balance)
        
        priority_queue.add(4, 'LOG', {
            'level': 'DEBUG',
            'message': f"📐 SIZING: Eq=${total_equity:.0f} | Risk=${risk_amount:.2f} | Size=${calculated_size:.0f} -> ${final_size:.0f}"
        })
        
        if final_size <= 0:
            Logger.warning(f"⚠️ [PAPER] Insufficient Funds for {watcher.symbol}")
            return None
        
        # Gas check
        self.paper_wallet.ensure_gas(min_sol=Settings.MIN_SOL_RESERVE * 2)
        if self.paper_wallet.sol_balance < Settings.MIN_SOL_RESERVE:
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"❌ [MOCK TXN FAILED] {watcher.symbol} BUY - Insufficient SOL for gas"
            })
            return None
        
        # Congestion check
        is_congested, failure_rate, delay_max = self._check_congestion(watcher)
        if is_congested:
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"⚠️ [CONGESTION] High Volatility detected on {watcher.symbol}"
            })
        
        # Transaction failure simulation
        if random.random() < failure_rate:
            self.paper_wallet.sol_balance -= Settings.SIMULATION_SWAP_FEE_SOL
            self.paper_wallet.stats['fees_paid_usd'] += Settings.SIMULATION_SWAP_FEE_SOL * 150
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"❌ [MOCK TXN FAILED] {watcher.symbol} BUY failed (gas lost)"
            })
            return None
        
        # Execution delay
        delay_ms = random.randint(Settings.EXECUTION_DELAY_MIN_MS, delay_max)
        time.sleep(delay_ms / 1000.0)
        
        # Partial fill simulation
        if random.random() < Settings.PARTIAL_FILL_RATE_PCT:
            fill_pct = random.uniform(Settings.MIN_FILL_PCT, 0.99)
            unfilled_usd = final_size * (1 - fill_pct)
            final_size = final_size * fill_pct
            priority_queue.add(3, 'LOG', {
                'level': 'INFO',
                'message': f"⚠️ [PARTIAL FILL] {watcher.symbol}: {fill_pct*100:.0f}% filled"
            })
        
        # Get execution price
        execution_price = self._get_execution_price(watcher, price, delay_ms)
        
        # MEV simulation
        if random.random() < Settings.MEV_RISK_RATE_PCT:
            mev_penalty_pct = random.uniform(0.01, Settings.MEV_PENALTY_MAX_PCT)
            execution_price = execution_price * (1 + mev_penalty_pct)
            priority_queue.add(3, 'LOG', {
                'level': 'INFO',
                'message': f"🥪 [MEV ATTACK] {watcher.symbol} Sandwich Bot: +{mev_penalty_pct*100:.2f}%"
            })
        
        # Log paper buy
        self._log_paper_buy(watcher.symbol, execution_price, reason, final_size)
        
        # Execute via CapitalManager
        is_vol = is_congested
        success, msg = self.capital_mgr.execute_buy(
            self.engine_name,
            watcher.symbol,
            watcher.mint,
            execution_price,
            final_size,
            liquidity_usd=liq,
            is_volatile=is_vol
        )
        
        if not success:
            priority_queue.add(2, 'LOG', {'level': 'WARN', 'message': f"⚠️ [PAPER] Buy Failed: {msg}"})
            return None
        
        # Set cooldown
        if decision_engine and hasattr(decision_engine, 'set_signal_cooldown'):
            decision_engine.set_signal_cooldown(watcher)
        
        return tx_id
    
    def _log_paper_buy(self, symbol: str, price: float, reason: str, size_usd: float) -> None:
        """Log paper buy to console and telegram."""
        from src.shared.system.data_source_manager import DataSourceManager
        dsm = DataSourceManager()
        volatility = dsm.get_volatility(symbol)
        
        # V51.0: Use Template
        from src.shared.system.telegram_templates import TradeTemplates
        msg = TradeTemplates.entry(
            symbol=symbol,
            action="BUY",
            amount=size_usd,
            price=price,
            engine="PAPER",
            reason=f"{reason} (Vol: {volatility:.1f}%)"
        )
        
        from src.shared.system.comms_daemon import send_telegram
        send_telegram(msg, source="PAPER", priority="LOW")
        
        # V51.0: Rich Console Log
        Logger.info(f"[PAPER] 📝 BUY {symbol} @ ${price:.6f} ({reason})")

    
    # ═══════════════════════════════════════════════════════════════════
    # SELL EXECUTION
    # ═══════════════════════════════════════════════════════════════════
    
    def execute_sell(
        self,
        watcher: 'Watcher',
        price: float,
        reason: str
    ) -> ExecutionResult:
        """
        Execute a sell order with realistic simulation.
        
        Args:
            watcher: Token watcher
            price: Signal price
            reason: Sell reason
            
        Returns:
            ExecutionResult with success status, message, and PnL
        """
        # V134: Null safety for price
        if price is None or price <= 0:
            price = watcher.get_price() if hasattr(watcher, 'get_price') else 0.0
            if price is None or price <= 0:
                return ExecutionResult(False, "No valid price for sell")
        
        # Guard - only sell assets we hold
        if not self.live_mode:
            if watcher.symbol not in self.paper_wallet.assets:
                return ExecutionResult(False, "No position to sell")
        
        # Log execution attempt
        mode_prefix = "LIVE" if self.live_mode else "MOCK"
        if getattr(Settings, 'DRY_RUN', False): mode_prefix = "SIMULATION"
        
        icon = "📉" if self.live_mode else "🔧"
        priority_queue.add(2, 'LOG', {
            'level': 'INFO',
            'message': f"{icon} EXECUTING {mode_prefix} SELL: {watcher.symbol} ({reason})"
        })
        
        # Capture state before exit (guard against None)
        entry_price_log = watcher.entry_price or 0.0
        cost_basis_log = watcher.cost_basis or 0.0
        size_token_log = watcher.token_balance or 0.0
        
        # V63.0: SIMULATION INTERCEPT
        # V63.0: SIMULATION INTERCEPT
        if getattr(Settings, 'DRY_RUN', False):
            # Mock success side effects
            pnl_usd = (size_token_log * price) - cost_basis_log
            pnl_pct = ((price - entry_price_log) / entry_price_log) * 100 if entry_price_log > 0 else 0
            
            # V63.1: Log with PnL
            self._log_simulated_trade("SELL", watcher.symbol, size_token_log * price, price, reason, 1.0, pnl=pnl_usd)
            
            # Check for "Smart Money" correlation here?
            
            # Log success
            Logger.success(f"[{self.engine_name}] 🧪 SIMULATED SELL: {watcher.symbol} (PnL: ${pnl_usd:.2f})")
            
            watcher.exit_position()
            watcher.last_signal_time = time.time()
            return ExecutionResult(True, f"SIMULATED SELL {watcher.symbol}", "sim_tx_id", pnl_usd)
        
        tx_id = None
        pnl_usd = 0.0
        
        if self.live_mode:
            # LIVE EXECUTION
            tx_id = self.swapper.execute_swap(
                direction="SELL",
                amount_usd=0,  # 0 means ALL
                reason=reason,
                target_mint=watcher.mint
            )
        else:
            # PAPER EXECUTION
            tx_id, pnl_usd = self._execute_paper_sell(watcher, price, reason)
        
        if tx_id:
            # Success path
            time.sleep(2)
            
            # PnL calculation
            if not self.live_mode:
                pnl_usd = self._last_paper_pnl
            else:
                exit_value = size_token_log * price
                pnl_usd = exit_value - cost_basis_log
            
            if pnl_usd is None:
                pnl_usd = 0.0
            
            pnl_pct = ((price - entry_price_log) / entry_price_log) * 100 if entry_price_log > 0 else 0
            
            # V51.0: Use Template
            from src.shared.system.telegram_templates import TradeTemplates
            msg = TradeTemplates.exit(
                symbol=watcher.symbol,
                pnl=pnl_usd,
                pnl_pct=pnl_pct,
                hold_time_mins=(time.time() - watcher.entry_time) / 60 if (hasattr(watcher, 'entry_time') and watcher.entry_time is not None) else 0,
                exit_reason=reason
            )
            
            from src.shared.system.comms_daemon import send_telegram
            tg_priority = "HIGH" if self.live_mode else "LOW"
            send_telegram(msg, source="PRIMARY", priority=tg_priority)
            
            # Log success
            icon = "📈" if pnl_usd >= 0 else "📉"
            Logger.success(f"[{self.engine_name}] {icon} SELL COMPLETE: {watcher.symbol} (PnL: ${pnl_usd:.2f})")
            self.portfolio.release_lock()
            
            # Track consecutive losses
            if pnl_usd > 0:
                self.consecutive_losses = 0
                self.portfolio._consecutive_losses = 0
                Logger.info(f"[{self.engine_name}] 📈 WIN: ${pnl_usd:.2f}")
            else:
                self.consecutive_losses += 1
                self.portfolio._consecutive_losses = self.consecutive_losses
                Logger.warning(f"[{self.engine_name}] 📉 LOSS: ${abs(pnl_usd):.2f} - Streak = {self.consecutive_losses}")
            
            # Log trade
            priority_queue.add(2, 'TRADE_RECORD', {
                'symbol': watcher.symbol,
                'entry_price': entry_price_log,
                'exit_price': price,
                'size_usd': cost_basis_log,
                'pnl_usd': pnl_usd,
                'net_pnl_pct': pnl_pct,
                'exit_reason': reason,
                'is_win': pnl_usd > 0,
                'consecutive_losses': self.consecutive_losses,
                'timestamp': time.time()
            })
            
            watcher.exit_position()
            watcher.last_signal_time = time.time()
            
            # Capital health check
            self.capital_mgr.perform_maintenance(self.engine_name)
            
            # V67.0: Trigger slippage recalibration after trade
            if self.slippage_calibrator:
                self.slippage_calibrator.maybe_recalibrate()
            
            return ExecutionResult(True, f"SELL {watcher.symbol}", tx_id, pnl_usd)
        else:
            priority_queue.add(2, 'LOG', {'level': 'ERROR', 'message': f"SELL FAILED: {watcher.symbol}"})
            return ExecutionResult(False, "Execution failed")
    
    def _execute_paper_sell(
        self,
        watcher: 'Watcher',
        price: float,
        reason: str
    ) -> Tuple[Optional[str], float]:
        """
        Execute paper sell with realistic simulation.
        
        Returns:
            (tx_id, pnl_usd) or (None, 0.0) on failure
        """
        tx_id = f"MOCK_TX_SELL_{int(time.time())}"
        self._paper_sell_occurred = False
        
        # Gas check
        self.paper_wallet.ensure_gas(min_sol=Settings.MIN_SOL_RESERVE * 2)
        if self.paper_wallet.sol_balance < Settings.MIN_SOL_RESERVE:
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"❌ [MOCK TXN FAILED] {watcher.symbol} SELL - Insufficient SOL for gas"
            })
            return None, 0.0
        
        # Congestion check
        is_congested, failure_rate, delay_max = self._check_congestion(watcher)
        
        # Transaction failure simulation
        if random.random() < failure_rate:
            self.paper_wallet.sol_balance -= Settings.SIMULATION_SWAP_FEE_SOL
            self.paper_wallet.stats['fees_paid_usd'] += Settings.SIMULATION_SWAP_FEE_SOL * 150
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING',
                'message': f"❌ [MOCK TXN FAILED] {watcher.symbol} SELL failed (gas lost, position held)"
            })
            return None, 0.0
        
        # Execution delay
        delay_ms = random.randint(Settings.EXECUTION_DELAY_MIN_MS, delay_max)
        time.sleep(delay_ms / 1000.0)
        
        # Check we have the asset
        if watcher.symbol not in self.paper_wallet.assets:
            return None, 0.0
        
        # Get execution price
        execution_price = self._get_execution_price(watcher, price, delay_ms)
        
        # Get liquidity
        data_feed_meta = getattr(watcher.data_feed, 'meta', {}) if hasattr(watcher, 'data_feed') else {}
        liquidity = data_feed_meta.get('liquidity_usd', 1000000) if data_feed_meta else 1000000
        
        # Execute via CapitalManager
        success, msg, paper_pnl = self.capital_mgr.execute_sell(
            self.engine_name,
            watcher.symbol,
            execution_price,
            reason,
            liquidity_usd=liquidity,
            is_volatile=is_congested
        )
        
        if not success:
            priority_queue.add(2, 'LOG', {'level': 'WARN', 'message': f"⚠️ [PAPER] Sell Failed: {msg}"})
            return None, 0.0
        
        self._last_paper_pnl = paper_pnl if paper_pnl else 0
        self._paper_sell_occurred = True
        
        print(f"\n📝 [PAPER] SELL {watcher.symbol} @ ${execution_price:.6f} ({reason}) PnL: ${paper_pnl:.2f}")
        
        return tx_id, paper_pnl

    def _log_simulated_trade(self, side, symbol, size_usd, price, reason, confidence, pnl=0.0):
        """V63.1: Log trade to DB for simulation analysis."""
        try:
            from src.data_storage.db_manager import db_manager
            
            trade_data = {
                "timestamp": time.time(),
                "symbol": symbol,
                "side": side,
                "price": price,
                "size_usd": size_usd,
                "reason": reason,
                "confidence": confidence,
                "pnl_usd": pnl,
                "is_win": pnl > 0
            }
            db_manager.insert_simulated_trade(trade_data)
                
            Logger.info(f"🧪 [SIMULATION] {side} {symbol} @ ${price:.4f} (${size_usd:.0f}) | {reason} (Conf: {confidence:.2f} PnL: ${pnl:.2f})")
            
        except Exception as e:
            Logger.error(f"Failed to log sim trade: {e}")
