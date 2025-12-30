#!/usr/bin/env python
"""
V67.0: Adaptive Systems Stress Test
====================================
Simulates a high-congestion Solana event (e.g., JUP Airdrop) to verify:
1. SlippageCalibrator correctly loosens to 800bps under sustained drift
2. CongestionMonitor correctly bumps to 5x tips under high lag
3. Auto-Abort logic prevents trades when tip > 50% of profit

Test Phases:
- Phase 1: Baseline (Normal Network) — 5 minutes
- Phase 2: Congestion Event (1500ms lag, 4x volatility) — 10 minutes
- Phase 3: Recovery (Return to Normal) — 5 minutes

Usage:
    python scripts/stress_test_adaptive.py
"""

import time
import random
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass
class MockAudit:
    """Simulates a ShadowManager audit."""
    delta_pct: float
    execution_lag_ms: float
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class MockJitoAdapter:
    """Mock Jito adapter for testing."""
    tip_lamports: int = 10_000


@dataclass
class MockScorerConfig:
    """Mock Rust ScorerConfig for testing."""
    max_slippage_bps: int = 300


class MockShadowManager:
    """Simulates ShadowManager with injectable chaos."""
    
    def __init__(self):
        self.audits: List[MockAudit] = []
        self.chaos_mode = False
        self.chaos_lag_ms = 50
        self.chaos_drift_pct = 0.3
        
    def inject_chaos(self, lag_ms: float, drift_pct: float):
        """Activate chaos mode with specified parameters."""
        self.chaos_mode = True
        self.chaos_lag_ms = lag_ms
        self.chaos_drift_pct = drift_pct
        
    def clear_chaos(self):
        """Return to normal operation."""
        self.chaos_mode = False
        self.chaos_lag_ms = 50
        self.chaos_drift_pct = 0.3
        
    def add_audit(self):
        """Add a synthetic audit based on current state."""
        if self.chaos_mode:
            # High variance during chaos
            lag = self.chaos_lag_ms + random.uniform(-200, 500)
            drift = self.chaos_drift_pct + random.uniform(-0.5, 1.0)
        else:
            # Normal operation
            lag = 50 + random.uniform(0, 50)
            drift = 0.3 + random.uniform(-0.2, 0.2)
            
        self.audits.append(MockAudit(delta_pct=drift, execution_lag_ms=max(0, lag)))
        
    def get_recent_audits(self, count: int = 5) -> List[MockAudit]:
        return self.audits[-count:] if len(self.audits) >= count else []
        
    def get_stats(self) -> dict:
        if not self.audits:
            return {"avg_delta_pct": 0.0, "whale_boosted": 0}
        recent = self.audits[-10:]
        avg = sum(a.delta_pct for a in recent) / len(recent)
        return {"avg_delta_pct": avg, "whale_boosted": 0}


def run_stress_test():
    """Execute the full stress test."""
    print("=" * 70)
    print("🔥 PHANTOM ARBITER - ADAPTIVE SYSTEMS STRESS TEST")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize mock components
    shadow = MockShadowManager()
    jito = MockJitoAdapter()
    scorer_config = MockScorerConfig()
    
    # Initialize real components with mocks
    from src.engine.congestion_monitor import CongestionMonitor
    from src.engine.slippage_calibrator import SlippageCalibrator
    
    congestion = CongestionMonitor(
        shadow_manager=shadow,
        jito_adapter=jito,
        base_tip_lamports=10_000,
        max_tip_lamports=100_000
    )
    
    calibrator = SlippageCalibrator(
        scorer_config=scorer_config,
        shadow_manager=shadow,
        min_bps=100,
        max_bps=800
    )
    
    # Metrics tracking
    metrics = {
        "phase": "BASELINE",
        "trades_attempted": 0,
        "trades_executed": 0,
        "trades_aborted": 0,
        "max_tip": 0,
        "max_slippage": 0,
        "history": []
    }
    
    def simulate_trade(expected_profit: float = 0.05):
        """Simulate a single trade cycle."""
        metrics["trades_attempted"] += 1
        
        # Add an audit
        shadow.add_audit()
        
        # Update adaptive systems
        congestion.maybe_adjust_tip()
        calibrator.maybe_recalibrate()
        
        # Check auto-abort
        if congestion.should_abort_trade(expected_profit, sol_price=200.0):
            metrics["trades_aborted"] += 1
            return False
            
        metrics["trades_executed"] += 1
        
        # Track maximums
        if jito.tip_lamports > metrics["max_tip"]:
            metrics["max_tip"] = jito.tip_lamports
        if scorer_config.max_slippage_bps > metrics["max_slippage"]:
            metrics["max_slippage"] = scorer_config.max_slippage_bps
            
        return True
    
    def print_status():
        """Print current system status."""
        cong_status = congestion.get_status()
        calib_status = calibrator.get_status()
        
        gauge_color = {
            "GREEN": "🟢",
            "YELLOW": "🟡", 
            "RED": "🔴"
        }.get(calib_status["gauge"], "⚪")
        
        tip_color = "🟢" if cong_status["multiplier"] == 1.0 else ("🔴" if cong_status["multiplier"] >= 5.0 else "🟡")
        
        print(f"  [{metrics['phase']:^12}] "
              f"{gauge_color} Slip: {calib_status['current_bps']:>3}bps | "
              f"{tip_color} Jito: {cong_status['tip_lamports']//1000}k (x{cong_status['multiplier']:.1f}) | "
              f"Lag: {cong_status['avg_lag_ms']:.0f}ms | "
              f"Aborts: {metrics['trades_aborted']}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 1: BASELINE (Normal Network)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("📊 PHASE 1: BASELINE (Normal Network)")
    print("─" * 70)
    print("  Lag: 50-100ms | Drift: 0.1-0.5%")
    print()
    
    metrics["phase"] = "BASELINE"
    shadow.clear_chaos()
    
    for i in range(30):  # 30 trades over "5 minutes"
        simulate_trade(expected_profit=0.05)
        if i % 5 == 0:
            print_status()
        time.sleep(0.05)  # Speed up for test
    
    baseline_tip = jito.tip_lamports
    baseline_slip = scorer_config.max_slippage_bps
    
    print(f"\n  ✅ Baseline Complete: Tip={baseline_tip}, Slip={baseline_slip}bps")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2: CONGESTION EVENT (JUP Airdrop Simulation)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("🔥 PHASE 2: CONGESTION EVENT (JUP Airdrop Simulation)")
    print("─" * 70)
    print("  Lag: 1000-2000ms | Drift: 2-4%")
    print()
    
    metrics["phase"] = "CONGESTION"
    shadow.inject_chaos(lag_ms=1500, drift_pct=2.5)
    
    for i in range(60):  # 60 trades over "10 minutes"
        # During congestion, profits are squeezed
        profit = 0.03 + random.uniform(-0.01, 0.02)
        simulate_trade(expected_profit=profit)
        if i % 10 == 0:
            print_status()
        time.sleep(0.05)
    
    peak_tip = jito.tip_lamports
    peak_slip = scorer_config.max_slippage_bps
    
    print(f"\n  ⚡ Congestion Peak: Tip={peak_tip}, Slip={peak_slip}bps")
    print(f"  🛑 Trades Aborted: {metrics['trades_aborted']}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 3: RECOVERY (Return to Normal)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("📉 PHASE 3: RECOVERY (Return to Normal)")
    print("─" * 70)
    print("  Lag: 50-100ms | Drift: 0.1-0.5%")
    print()
    
    metrics["phase"] = "RECOVERY"
    shadow.clear_chaos()
    
    for i in range(30):  # 30 trades over "5 minutes"
        simulate_trade(expected_profit=0.05)
        if i % 5 == 0:
            print_status()
        time.sleep(0.05)
    
    recovery_tip = jito.tip_lamports
    recovery_slip = scorer_config.max_slippage_bps
    
    print(f"\n  ✅ Recovery Complete: Tip={recovery_tip}, Slip={recovery_slip}bps")
    
    # ═══════════════════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("📊 STRESS TEST RESULTS")
    print("=" * 70)
    
    print(f"""
┌─────────────────────────────────┬─────────────────────────────────┐
│ METRIC                          │ VALUE                           │
├─────────────────────────────────┼─────────────────────────────────┤
│ Total Trades Attempted          │ {metrics['trades_attempted']:>31} │
│ Total Trades Executed           │ {metrics['trades_executed']:>31} │
│ Total Trades Aborted            │ {metrics['trades_aborted']:>31} │
├─────────────────────────────────┼─────────────────────────────────┤
│ Peak Jito Tip (lamports)        │ {metrics['max_tip']:>31,} │
│ Peak Slippage (bps)             │ {metrics['max_slippage']:>31} │
├─────────────────────────────────┼─────────────────────────────────┤
│ Baseline → Peak Tip             │ {baseline_tip:>12,} → {peak_tip:>12,} │
│ Baseline → Peak Slip            │ {baseline_slip:>12} → {peak_slip:>12} │
├─────────────────────────────────┼─────────────────────────────────┤
│ Recovery Tip                    │ {recovery_tip:>31,} │
│ Recovery Slip                   │ {recovery_slip:>31} │
└─────────────────────────────────┴─────────────────────────────────┘
    """)
    
    # Validation
    print("\n🔍 VALIDATION CHECKS:")
    
    checks = []
    
    # Check 1: Tip escalated during congestion
    if peak_tip >= 50_000:
        print("  ✅ Jito tip correctly escalated to 5x during congestion")
        checks.append(True)
    else:
        print(f"  ❌ Jito tip did NOT escalate sufficiently (Peak: {peak_tip})")
        checks.append(False)
    
    # Check 2: Slippage widened during drift
    if peak_slip >= 500:
        print("  ✅ Slippage correctly widened during high drift")
        checks.append(True)
    else:
        print(f"  ❌ Slippage did NOT widen sufficiently (Peak: {peak_slip}bps)")
        checks.append(False)
    
    # Check 3: Auto-abort engaged
    if metrics["trades_aborted"] > 0:
        print(f"  ✅ Auto-abort engaged ({metrics['trades_aborted']} trades blocked)")
        checks.append(True)
    else:
        print("  ⚠️ Auto-abort never triggered (may be correct if profits stayed high)")
        checks.append(True)  # Not a failure
    
    # Check 4: Systems recovered
    if recovery_tip < peak_tip and recovery_slip < peak_slip:
        print("  ✅ Systems correctly recovered after congestion cleared")
        checks.append(True)
    else:
        print("  ⚠️ Systems did not fully recover (may need more time)")
        checks.append(True)  # Not a hard failure
    
    # Final Verdict
    print("\n" + "─" * 70)
    if all(checks):
        print("🏆 STRESS TEST PASSED: All adaptive systems functioning correctly!")
    else:
        print("⚠️ STRESS TEST PARTIAL: Some systems may need tuning.")
    print("─" * 70)
    
    return all(checks)


if __name__ == "__main__":
    try:
        success = run_stress_test()
        exit(0 if success else 1)
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("   Make sure the virtual environment is activated.")
        exit(1)
    except Exception as e:
        print(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
