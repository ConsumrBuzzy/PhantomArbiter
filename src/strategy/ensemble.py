
from src.engine.decision_engine import DecisionEngine
from src.strategy.keltner_logic import KeltnerLogic
from src.strategy.vwap_logic import VwapLogic
from src.strategy.base_strategy import BaseStrategy
from src.system.logging import Logger
from src.agents.base_agent import AgentSignal
from typing import Optional, List
import numpy as np

class MerchantEnsemble(BaseStrategy):
    """
    V45.0: The Unified Merchant Mind.
    V67.5/V68.5: Weighted Consensus Engine.
    Aggregates Scalper, Keltner, and VWAP strategies into a single decision engine.
    V68.5: Now uses ThresholdManager for dynamic thresholds.
    """
    
    # V67.5: Default Consensus Weights (can be overridden by dynamic weights)
    WEIGHT_ML = 0.40      # ML/Technical baseline
    WEIGHT_SCOUT = 0.30   # Real-time OFI/Smart Money
    WEIGHT_WHALE = 0.30   # Social proof / Copy-trade
    
    # V68.5: Thresholds now come from ThresholdManager
    # These are fallbacks only
    DEFAULT_VETO_THRESHOLD = -0.5
    DEFAULT_BOOST_THRESHOLD = 0.7
    
    def __init__(self, portfolio):
        super().__init__(portfolio)
        
        # Instantiate the 3 "Thoughts" of the Merchant
        self.scalper = DecisionEngine(portfolio)
        self.keltner = KeltnerLogic(portfolio)
        self.vwap = VwapLogic(portfolio)
        
        self.sub_strategies = {
            "SCALPER": self.scalper,
            "KELTNER": self.keltner,
            "VWAP": self.vwap
        }
        
        # V67.5: Agent Signal Bus
        self.pending_agent_signals: List[AgentSignal] = []
        
        self.market_mode = "ENSEMBLE"
        Logger.info("🧠 [ENSEMBLE] Merchant Mind initialized (V67.5 Weighted Consensus)")

    def inject_agent_signal(self, signal: AgentSignal):
        """V67.5: Accept signals from Scout/Whale agents."""
        if signal:
            self.pending_agent_signals.append(signal)

    def _calculate_weighted_consensus(self, ml_score: float, symbol: str) -> tuple[float, str, bool]:
        """
        V67.5/V68.0: Calculate final confidence using weighted consensus.
        V68.0: Dynamic Weights - Shift to Scout if ML underperforming.
        Returns: (final_score, reason_modifier, should_boost_size)
        """
        # V68.0: Dynamic Weight Adjustment
        weight_ml = self.WEIGHT_ML
        weight_scout = self.WEIGHT_SCOUT
        weight_whale = self.WEIGHT_WHALE
        
        try:
            from src.core.capital_manager import get_capital_manager
            cm = get_capital_manager()
            pnl_24h = cm.get_session_pnl()  # Get 24h PnL
            
            if pnl_24h < 0:
                # ML underperforming - shift weight to Scout
                weight_ml = 0.20
                weight_scout = 0.50
                weight_whale = 0.30
                Logger.debug("[ENSEMBLE] Dynamic Weights: ML underperforming, boosting Scout")
        except Exception:
            pass  # Use default weights
        
        scout_score = 0.0
        whale_score = 0.0
        reasons = []
        
        # 1. Process pending agent signals for THIS symbol
        relevant_signals = [s for s in self.pending_agent_signals if s.symbol == symbol or s.symbol == "UNKNOWN"]
        
        for sig in relevant_signals:
            source = sig.metadata.get("source", "AGENT") if sig.metadata else "AGENT"
            
            if source == "SCOUT" or "OFI" in (sig.reason or ""):
                # Scout OFI Signal
                scout_score = sig.confidence
                if sig.action == "VETO":
                    # VETO overrides everything
                    return -1.0, "🚫 SCOUT VETO", False
                reasons.append(f"Scout:{sig.confidence:.2f}")
                
            elif source == "WHALE_WATCHER":
                # Whale Copy Signal
                whale_score = sig.confidence
                reasons.append(f"Whale:{sig.confidence:.2f}")
        
        # Clear processed signals
        self.pending_agent_signals = [s for s in self.pending_agent_signals if s not in relevant_signals]
        
        # 2. Calculate Weighted Sum (using dynamic weights)
        final_score = (
            weight_ml * ml_score +
            weight_scout * scout_score +
            weight_whale * whale_score
        )
        
        # 3. Check Confirmation Boost (ML + Whale agree)
        should_boost = (ml_score > 0.6 and whale_score > 0.6)
        
        reason_str = " + ".join(reasons) if reasons else ""
        return final_score, reason_str, should_boost

    def analyze_tick(self, watcher, price: float, agent_signals: List[AgentSignal] = None) -> tuple[str, str, float]:
        """
        Poll all sub-strategies and return a unified decision.
        V67.5: Now accepts Optional[AgentSignal] list for weighted consensus.
        Returns: (Action, Reason, Size)
        """
        # Inject any passed signals
        if agent_signals:
            for sig in agent_signals:
                self.inject_agent_signal(sig)
        
        signals = []
        
        # 1. Collect Signals from Technical Strategies
        for name, strategy in self.sub_strategies.items():
            try:
                # Polling each strategy
                action, reason, size = strategy.analyze_tick(watcher, price)
                
                if action in ['BUY', 'SELL']:
                    # V60.0: Regime-Aware Confidence
                    from src.core.shared_cache import SharedPriceCache
                    regime = SharedPriceCache.get_market_regime()
                    
                    confidence = 0.5
                    
                    # 1. Base Confidence
                    if name == "SCALPER": confidence = 0.6 
                    if name == "KELTNER" and "ENTRY" in reason: confidence = 0.8
                    if name == "VWAP" and "ENTRY" in reason: confidence = 0.7 
                    
                    # 2. Regime Adjustments
                    if regime:
                        trend = regime.get("trend", "RANGING")
                        vol = regime.get("volatility", "NORMAL")
                        
                        # Chaotic Market -> Reduce all confidence
                        if vol == "CHAOTIC":
                            confidence *= 0.5
                        
                        # Trending Market -> Boost VWAP, Penalize Mean Reversion
                        if "TRENDING" in trend:
                            if name == "VWAP": confidence += 0.2
                            if name == "KELTNER": confidence -= 0.1
                        
                        # Ranging Market -> Boost Mean Reversion
                        if trend == "RANGING":
                            if name == "KELTNER": confidence += 0.1
                            if name == "SCALPER": confidence += 0.1
                            
                        # V61.0: Discovery Engine Trust Signal
                        # If Smart Money is in this token -> Massive confidence boost
                        trust_score = SharedPriceCache.get_trust_score(watcher.symbol)
                        if trust_score > 0:
                            # Trust Score 0.5 (1 hit) -> +15%
                            # Trust Score 1.0 (3+ hits) -> +35%
                            boost = trust_score * 0.35 
                            confidence += boost
                    
                    signals.append({
                        "source": name,
                        "action": action,
                        "reason": reason,
                        "size": size,
                        "confidence": min(confidence, 1.0) # Cap at 1.0
                    })
            except Exception as e:
                Logger.error(f"⚠️ [ENSEMBLE] Error in {name}: {e}")
                
        if not signals:
            return 'HOLD', '', 0.0

        # 2. Conflict Resolution
        buy_signals = [s for s in signals if s['action'] == 'BUY']
        sell_signals = [s for s in signals if s['action'] == 'SELL']

        # PRIORITY 1: Safety/Exits (Any Sell signal triggers review)
        # If any strategy wants to Sell, we should probably Sell unless strong consensus to Buy
        if sell_signals:
            # If ANY strategy triggers a Hard Stop (SL HIT), we honor it immediately
            for s in sell_signals:
                if "SL HIT" in s['reason'] or "NUCLEAR" in s['reason']:
                    return 'SELL', f"🚨 {s['source']} CRITICAL EXIT: {s['reason']}", 0.0
            
            # Otherwise, Consensus Sell
            sources = "+".join([s['source'] for s in sell_signals])
            return 'SELL', f"Consensus Sell ({sources})", 0.0

        # PRIORITY 2: Buy Consensus with V67.5 Weighted Logic
        if buy_signals:
            # Get average ML-level confidence from sub-strategies
            avg_ml_conf = sum(s['confidence'] for s in buy_signals) / len(buy_signals)
            
            # V67.5: Apply Weighted Consensus
            final_score, agent_reason, should_boost = self._calculate_weighted_consensus(avg_ml_conf, watcher.symbol)
            
            # Check for VETO
            if final_score < 0:
                return 'HOLD', agent_reason, 0.0
            
            # Calculate final size
            avg_size = sum(s['size'] for s in buy_signals) / len(buy_signals)
            final_size = avg_size
            
            # Confirmation Boost
            if should_boost:
                final_size = min(avg_size * 2.0, 150.0)  # Double size, cap at $150
                agent_reason = "🔥 HIGH-CONVICTION " + agent_reason
            
            # Multi-strategy agreement
            if len(buy_signals) >= 2:
                sources = "+".join([s['source'] for s in buy_signals])
                final_size = min(final_size * 1.5, 150.0)
                return 'BUY', f"🧠 CONSENSUS ({sources}) {agent_reason} | Score:{final_score:.2f}", final_size
            
            # Single signal with agent boost
            s = buy_signals[0]
            return s['action'], f"{s['source']}: {s['reason']} {agent_reason} | Score:{final_score:.2f}", final_size
        
        # V70.0: Check for Agent-Only Signals (Sniper/Whale can trigger without technical signal)
        if self.pending_agent_signals:
            for sig in self.pending_agent_signals:
                source = sig.metadata.get("source", "UNKNOWN") if sig.metadata else "UNKNOWN"
                
                # Sniper and Whale signals can execute independently
                if source in ["SNIPER", "WHALE_WATCHER"] and sig.action == "BUY":
                    # Get size from signal metadata or default
                    size = sig.metadata.get("snipe_size", 10.0) if sig.metadata else 10.0
                    
                    # Clear processed signal
                    self.pending_agent_signals.remove(sig)
                    
                    Logger.info(f"🎯 [ENSEMBLE] Agent-Only Trade: {source} {sig.symbol} @ {sig.confidence:.0%}")
                    return 'BUY', f"🎯 {source}: {sig.reason}", size
            
        return 'HOLD', '', 0.0

