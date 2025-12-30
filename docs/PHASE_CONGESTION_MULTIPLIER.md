# ⚡ Phase 5D: Congestion Multiplier

> **Status**: ✅ Complete | **Priority**: P1

---

## Goal

Dynamically scale Jito tips based on network congestion to ensure transaction inclusion during high-competition periods.

---

## Problem

Even with perfect slippage, transactions can fail to land if:

1. Block engine is saturated
2. Competitors are tipping higher
3. RPC latency causes stale slot submission

---

## Solution: Adaptive Tip Scaling

```
ShadowManager.execution_lag_ms
       │
       ▼ Every 5 trades
CongestionMonitor.check_health()
       │
       ├─ Lag < 100ms    → BASE_TIP (10k lamports)
       ├─ Lag 100-500ms  → 2x TIP
       ├─ Lag 500-1000ms → 3x TIP
       └─ Lag > 1000ms   → 5x TIP (EMERGENCY)
       │
       ▼
JitoAdapter.tip_lamports updated
       │
       ▼ Alert
🔥 "[CONGESTION] Tip: 10k→50k lamports (Lag: 1200ms)"
```

---

## Implementation

### New File: `src/engine/congestion_monitor.py`

```python
class CongestionMonitor:
    def __init__(self, shadow_manager, jito_adapter):
        self.shadow = shadow_manager
        self.jito = jito_adapter
        self.base_tip = 10_000  # 10k lamports
        self.max_tip = 100_000  # 100k lamports
        self.window_size = 5
    
    def maybe_adjust_tip(self) -> bool:
        """Adjust tip based on execution lag."""
        audits = self.shadow.get_recent_audits(self.window_size)
        if len(audits) < self.window_size:
            return False
        
        avg_lag = sum(a.execution_lag_ms for a in audits) / len(audits)
        
        # Tiered multiplier
        if avg_lag > 1000:
            multiplier = 5.0
        elif avg_lag > 500:
            multiplier = 3.0
        elif avg_lag > 100:
            multiplier = 2.0
        else:
            multiplier = 1.0
        
        new_tip = min(int(self.base_tip * multiplier), self.max_tip)
        if new_tip != self.jito.tip_lamports:
            old = self.jito.tip_lamports
            self.jito.tip_lamports = new_tip
            Logger.info(f"🔥 [CONGESTION] Tip: {old}→{new_tip} lamports (Lag: {avg_lag:.0f}ms)")
            return True
        return False
```

### Integration Points

1. **TradeExecutor** — Call `congestion_monitor.maybe_adjust_tip()` after each trade
2. **ShadowManager** — Already tracks `execution_lag_ms`
3. **JitoAdapter** — `tip_lamports` is mutable

---

## Thresholds (Configurable)

| Setting | Default | Description |
|---------|---------|-------------|
| `JITO_BASE_TIP` | 10,000 | Floor tip (lamports) |
| `JITO_MAX_TIP` | 100,000 | Ceiling tip |
| `LAG_TIER_1_MS` | 100 | Normal threshold |
| `LAG_TIER_2_MS` | 500 | Elevated threshold |
| `LAG_TIER_3_MS` | 1000 | Emergency threshold |

---

## Dashboard Addition

```
│ 🔥 JITO: 10k (x1.0) │ Lag: 45ms │ Status: NORMAL                 │
```

---

## Verification

- [x] Unit test: lag > 1000ms → 5x tip
- [x] Unit test: lag < 100ms → base tip
- [x] Integration: tips actually change in JitoAdapter
- [x] Dashboard: shows current tip multiplier

---

## Auto-Abort Logic (Added)

Prevents trades when Jito tip exceeds 50% of expected profit:

```python
def should_abort_trade(expected_profit_usd: float) -> bool:
    """Returns True if tip > 50% of profit."""
    tip_usd = (tip_lamports / 1e9) * sol_price
    ratio = tip_usd / expected_profit_usd
    return ratio > 0.50
```

---

## Stress Test

Run `scripts/stress_test_adaptive.py` to simulate:

1. **Baseline**: Normal network (50ms lag, 0.3% drift)
2. **Congestion**: JUP Airdrop (1500ms lag, 2.5% drift, 4x volatility)
3. **Recovery**: Return to normal

Validates:

- Jito tip escalates to 5x during congestion
- Slippage widens to 800bps during high drift
- Auto-abort engages when tip > 50% of profit
- Systems recover after congestion clears
