"""
Phantom Arbiter - Exit Conditions
=================================
The MOST IMPORTANT CODE - tells the bot when to exit.

Exit Triggers:
=============
1. FUNDING_FLIP: Funding rate becomes negative (you START paying)
2. APR_COLLAPSE: Funding drops below breakeven threshold
3. MAX_DURATION: Position held too long (target profit reached or time limit)
4. DELTA_RUNAWAY: Position imbalance too large to rebalance profitably
5. TAKE_PROFIT: Collected enough funding to exit with profit

The Golden Rule:
================
Exit BEFORE your accumulated funding gets eaten by:
- A massive price move that overwhelms your delta hedge
- A funding flip that starts costing you money
- Fees from emergency rebalancing
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from config.settings import Settings
from src.shared.system.logging import Logger


class ExitReason(Enum):
    """Reasons for exiting a position."""
    FUNDING_FLIP = "FUNDING_FLIP"           # Funding turned negative
    APR_COLLAPSE = "APR_COLLAPSE"           # APR dropped below threshold
    TAKE_PROFIT = "TAKE_PROFIT"             # Target profit reached
    MAX_DURATION = "MAX_DURATION"           # Time limit reached
    DELTA_RUNAWAY = "DELTA_RUNAWAY"         # Position too imbalanced
    MANUAL = "MANUAL"                       # Manual exit
    EMERGENCY = "EMERGENCY"                 # Something wrong, get out


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    coin: str
    reason: ExitReason
    urgency: str                # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    details: str
    current_pnl: float
    projected_loss: float       # If we DON'T exit


class ExitConditionMonitor:
    """
    Monitors positions and generates exit signals.
    
    Checks every minute for:
    - Funding rate changes
    - P&L thresholds
    - Delta drift
    - Time-based exits
    """
    
    # Exit thresholds
    MIN_APR_THRESHOLD = 5.0          # Exit if APR drops below 5%
    FUNDING_FLIP_THRESHOLD = -0.001  # Exit if funding goes negative
    MAX_POSITION_HOURS = 168         # 1 week max hold
    TAKE_PROFIT_MULTIPLIER = 3.0     # Exit after 3x breakeven
    MAX_DELTA_DRIFT = 0.15           # Exit if 15% imbalance (too expensive to fix)
    
    def __init__(self, executor=None):
        self.executor = executor
        self._funding_feed = None
        
        # Tracking
        self.exit_signals: List[ExitSignal] = []
        self.exits_triggered = 0
        
    def _get_funding_feed(self):
        """Lazy-load funding feed."""
        if self._funding_feed is None:
            from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed
            self._funding_feed = MockDriftFundingFeed()
        return self._funding_feed
    
    async def check_exit_conditions(self, position) -> Optional[ExitSignal]:
        """
        Check all exit conditions for a position.
        
        Returns ExitSignal if should exit, None if position is healthy.
        """
        coin = position.coin
        
        # Get current funding rate
        feed = self._get_funding_feed()
        funding_info = await feed.get_funding_rate(f"{coin}-PERP")
        
        if not funding_info:
            return ExitSignal(
                coin=coin,
                reason=ExitReason.EMERGENCY,
                urgency="HIGH",
                details="Cannot get funding rate - data feed issue",
                current_pnl=position.funding_collected,
                projected_loss=position.total_usd * 0.01  # Assume 1% risk
            )
        
        current_rate_8h = funding_info.rate_8h
        current_apr = funding_info.rate_annual
        
        # ═══════════════════════════════════════════════════════════════
        # CHECK 1: FUNDING FLIP
        # ═══════════════════════════════════════════════════════════════
        if current_rate_8h < self.FUNDING_FLIP_THRESHOLD:
            # DANGER! We're now PAYING funding instead of receiving
            hourly_cost = position.total_usd * abs(current_rate_8h / 100) / 8
            projected_24h_loss = hourly_cost * 24
            
            return ExitSignal(
                coin=coin,
                reason=ExitReason.FUNDING_FLIP,
                urgency="CRITICAL",
                details=f"Funding flipped negative: {current_rate_8h:.4f}%/8h. You're now PAYING ${hourly_cost:.4f}/hour!",
                current_pnl=position.funding_collected,
                projected_loss=projected_24h_loss
            )
        
        # ═══════════════════════════════════════════════════════════════
        # CHECK 2: APR COLLAPSE
        # ═══════════════════════════════════════════════════════════════
        if current_apr < self.MIN_APR_THRESHOLD:
            return ExitSignal(
                coin=coin,
                reason=ExitReason.APR_COLLAPSE,
                urgency="MEDIUM",
                details=f"APR dropped to {current_apr:.1f}% (below {self.MIN_APR_THRESHOLD}% threshold). No longer worth the fees.",
                current_pnl=position.funding_collected,
                projected_loss=0  # Not losing, just not making enough
            )
        
        # ═══════════════════════════════════════════════════════════════
        # CHECK 3: TAKE PROFIT
        # ═══════════════════════════════════════════════════════════════
        entry_fees = position.total_usd * 0.002  # Entry fees already paid
        exit_fees = position.total_usd * 0.002   # Exit fees to pay
        breakeven = entry_fees + exit_fees
        target_profit = breakeven * self.TAKE_PROFIT_MULTIPLIER
        
        net_pnl = position.funding_collected - exit_fees
        
        if net_pnl >= target_profit:
            return ExitSignal(
                coin=coin,
                reason=ExitReason.TAKE_PROFIT,
                urgency="LOW",
                details=f"Target profit reached! Collected ${position.funding_collected:.4f}, target was ${target_profit:.4f}",
                current_pnl=net_pnl,
                projected_loss=0
            )
        
        # ═══════════════════════════════════════════════════════════════
        # CHECK 4: MAX DURATION
        # ═══════════════════════════════════════════════════════════════
        hours_held = (time.time() - position.entry_time) / 3600
        
        if hours_held >= self.MAX_POSITION_HOURS:
            return ExitSignal(
                coin=coin,
                reason=ExitReason.MAX_DURATION,
                urgency="LOW",
                details=f"Position held {hours_held:.0f} hours (max: {self.MAX_POSITION_HOURS}). Time to take profits and reset.",
                current_pnl=net_pnl,
                projected_loss=0
            )
        
        # ═══════════════════════════════════════════════════════════════
        # CHECK 5: DELTA RUNAWAY
        # ═══════════════════════════════════════════════════════════════
        if hasattr(position, 'delta_ratio'):
            delta_drift = abs(1.0 - position.delta_ratio)
            
            if delta_drift > self.MAX_DELTA_DRIFT:
                rebalance_cost = position.total_usd * delta_drift * 0.002  # Fees to rebalance
                
                return ExitSignal(
                    coin=coin,
                    reason=ExitReason.DELTA_RUNAWAY,
                    urgency="HIGH",
                    details=f"Delta drift {delta_drift*100:.1f}% too high. Rebalancing costs ${rebalance_cost:.2f} - better to exit.",
                    current_pnl=net_pnl,
                    projected_loss=rebalance_cost
                )
        
        # ═══════════════════════════════════════════════════════════════
        # ALL CLEAR
        # ═══════════════════════════════════════════════════════════════
        return None
    
    async def check_all_positions(self) -> List[ExitSignal]:
        """Check all active positions for exit signals."""
        if not self.executor:
            return []
        
        signals = []
        for coin, position in self.executor.positions.items():
            signal = await self.check_exit_conditions(position)
            if signal:
                signals.append(signal)
                self.exit_signals.append(signal)
                
                # Log based on urgency
                if signal.urgency == "CRITICAL":
                    Logger.error(f"[EXIT] 🚨 CRITICAL: {signal.details}")
                elif signal.urgency == "HIGH":
                    Logger.warning(f"[EXIT] ⚠️ {signal.details}")
                else:
                    Logger.info(f"[EXIT] ℹ️ {signal.details}")
        
        return signals
    
    def should_exit(self, signal: ExitSignal) -> bool:
        """
        Decide whether to actually exit based on signal.
        
        Some signals are warnings, some are mandatory exits.
        """
        MANDATORY_EXITS = [
            ExitReason.FUNDING_FLIP,
            ExitReason.DELTA_RUNAWAY,
            ExitReason.EMERGENCY
        ]
        
        return signal.reason in MANDATORY_EXITS or signal.urgency in ["CRITICAL", "HIGH"]
    
    def get_exit_recommendation(self, signals: List[ExitSignal]) -> str:
        """Generate human-readable exit recommendation."""
        if not signals:
            return "✅ All positions healthy - no exit needed"
        
        lines = ["🚨 EXIT SIGNALS DETECTED:\n"]
        
        for signal in signals:
            emoji = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🟢"
            }.get(signal.urgency, "⚪")
            
            lines.append(f"{emoji} {signal.coin}: {signal.reason.value}")
            lines.append(f"   {signal.details}")
            lines.append(f"   Current P&L: ${signal.current_pnl:+.4f}")
            if signal.projected_loss > 0:
                lines.append(f"   Risk if NOT exiting: -${signal.projected_loss:.4f}")
            lines.append("")
        
        # Summary recommendation
        critical = [s for s in signals if s.urgency == "CRITICAL"]
        high = [s for s in signals if s.urgency == "HIGH"]
        
        if critical:
            lines.append("⚡ RECOMMENDATION: EXIT IMMEDIATELY")
        elif high:
            lines.append("⚠️ RECOMMENDATION: EXIT SOON (within 1 hour)")
        else:
            lines.append("ℹ️ RECOMMENDATION: Consider exit at next favorable moment")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from src.arbiter.core.atomic_executor import AtomicExecutor, AtomicPosition
    
    async def test():
        print("=" * 60)
        print("Exit Condition Monitor Test")
        print("=" * 60)
        
        executor = AtomicExecutor(paper_mode=True)
        monitor = ExitConditionMonitor(executor=executor)
        
        # Test 1: Healthy position
        print("\n--- Test 1: Healthy position ---")
        position = AtomicPosition(
            coin="SOL",
            spot_amount=2.0,
            perp_amount=-2.0,  # Perfectly balanced
            entry_spot_price=100.0,
            entry_perp_price=100.0,
            entry_time=time.time() - 3600,  # 1 hour ago
            total_usd=400.0,
            funding_collected=0.05  # Small profit so far
        )
        executor.positions["SOL"] = position
        
        signals = await monitor.check_all_positions()
        print(monitor.get_exit_recommendation(signals))
        
        # Test 2: Long-held position (take profit)
        print("\n--- Test 2: Position at take profit ---")
        position.funding_collected = 5.0  # Made good profit
        position.entry_time = time.time() - 48*3600  # 48 hours ago
        
        signals = await monitor.check_all_positions()
        print(monitor.get_exit_recommendation(signals))
        
        # Test 3: Imbalanced position
        print("\n--- Test 3: Imbalanced position ---")
        position.spot_amount = 2.5  # More spot than perp
        position.perp_amount = -2.0
        
        signals = await monitor.check_all_positions()
        print(monitor.get_exit_recommendation(signals))
    
    asyncio.run(test())
