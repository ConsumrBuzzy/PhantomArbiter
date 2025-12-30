# ⚙️ Phase 5C: Auto-Slippage Calibrator

> **Status**: ✅ Complete | **Priority**: P1

---

## Goal

Automatically adjust `max_slippage_bps` in response to sustained drift, protecting capital during high-volatility or congestion periods.

---

## Logic Flow

```
ShadowManager.audits[]
       │
       ▼ Every 5 trades
DriftAnalyzer.check_calibration()
       │
       ├─ Avg drift < 0.5%  → DECREASE slippage (tighten)
       ├─ Avg drift 0.5-1.5% → NO CHANGE
       └─ Avg drift > 1.5%  → INCREASE slippage (loosen)
       │
       ▼
ScorerConfig.max_slippage_bps updated
       │
       ▼ Alert
🔔 "[AUTO-CAL] Slippage: 300→350 bps (Drift: +1.8%)"
```

---

## Implementation

### New File: `src/engine/slippage_calibrator.py`

```python
class SlippageCalibrator:
    def __init__(self, shadow_manager, scorer_config):
        self.shadow = shadow_manager
        self.config = scorer_config
        self.check_interval = 5  # trades
        self.min_bps = 100
        self.max_bps = 800
    
    def maybe_recalibrate(self) -> bool:
        """Check drift and adjust slippage if needed."""
        audits = self.shadow.get_recent_audits(self.check_interval)
        if len(audits) < self.check_interval:
            return False
        
        avg_drift = sum(a.delta_pct for a in audits) / len(audits)
        
        if abs(avg_drift) > 1.5:
            # INCREASE slippage tolerance
            new_bps = min(self.config.max_slippage_bps + 50, self.max_bps)
            self._apply(new_bps, avg_drift, "LOOSEN")
            return True
        elif abs(avg_drift) < 0.5 and self.config.max_slippage_bps > self.min_bps:
            # DECREASE slippage (tighten)
            new_bps = max(self.config.max_slippage_bps - 25, self.min_bps)
            self._apply(new_bps, avg_drift, "TIGHTEN")
            return True
        return False
    
    def _apply(self, new_bps, drift, action):
        old = self.config.max_slippage_bps
        self.config.max_slippage_bps = new_bps
        Logger.info(f"⚙️ [AUTO-CAL] Slippage: {old}→{new_bps} bps ({action}, Drift: {drift:+.2f}%)")
```

### Integration Points

1. **TradeExecutor** — Call `calibrator.maybe_recalibrate()` after each trade
2. **ShadowManager** — Already provides `get_recent_audits(n)`
3. **SignalScorer** — Config is mutable, changes take effect next tick

---

## Thresholds (Configurable)

| Setting | Default | Description |
|---------|---------|-------------|
| `SLIPPAGE_MIN_BPS` | 100 | Floor (1%) |
| `SLIPPAGE_MAX_BPS` | 800 | Ceiling (8%) |
| `DRIFT_LOOSEN_THRESHOLD` | 1.5% | Trigger to increase |
| `DRIFT_TIGHTEN_THRESHOLD` | 0.5% | Trigger to decrease |
| `CALIBRATION_WINDOW` | 5 trades | Sample size |

---

## Verification

- [ ] Unit test: drift > 1.5% → slippage increases
- [ ] Unit test: drift < 0.5% → slippage decreases
- [ ] Integration: runs in live loop without errors
- [ ] Dashboard: shows current slippage_bps
