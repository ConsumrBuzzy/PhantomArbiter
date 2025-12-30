# 🎛️ Phase 6: Dashboard Observability Overhaul

> **Status**: 📋 Planning | **Priority**: P1

---

## Goal

Transform the Glass Cockpit dashboard into a comprehensive observability layer that surfaces all Phase 4-5 metrics and provides actionable intelligence at a glance.

---

## Current State Analysis

### Existing Dashboard Sections

| Section | Data Source | Status |
|---------|-------------|--------|
| 🐝 SWARM | DataBroker agents | ✅ Good |
| 📈 MARKET | ThresholdManager, SharedCache | ✅ Good |
| 💰 PAPER | CapitalManager | ✅ Good |
| 🔧 INFRA | WSS, DB, Threads | ✅ Good |
| 🧠 INTELLIGENCE | Whale alerts, Queue, PnL | ⚠️ Needs expansion |
| 🎯 DRIFT | ShadowManager | ✅ New (Phase 5B) |

### Missing High-Value Metrics

1. **Rust FFI Performance** — No visibility into SignalScorer latency
2. **RPC Race Stats** — SlotConsensus wins not surfaced
3. **Signal Pipeline** — No filter rejection rates shown
4. **Capital Risk** — No drawdown or Sharpe estimates

---

## Proposed Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ 🎛️  PHANTOM TRADER v6.0  │  HH:MM:SS  │  Uptime: XXm           │
├────────────────┬─────────────────┬────────────────┬──────────────┤
│ 🐝 SWARM       │ 📈 MARKET       │ 💰 PORTFOLIO   │ 🔧 INFRA     │
│ Scout: ACTIVE  │ SOL: $XXX       │ Val: $XXX.XX   │ WSS: ✅      │
│ Whale: POLL    │ Regime: UP      │ Cash/Gas/Pos   │ RPC: 14ms   │
│ Sniper: X      │ VIX: QUIET      │ W/L: X/X       │ Threads: X  │
├────────────────┴─────────────────┴────────────────┴──────────────┤
│ ⚡ RUST FAST-PATH                                                │
│ Scorer: 142 calls │ 0.8ms avg │ 38 rejected │ FFI: OK          │
├────────────────────────────────────────────────────────────────────┤
│ 🏎️ RPC RACE (Slot Lag: 2)                                        │
│ Helius: 67% │ Alchemy: 28% │ Triton: 5% │ Winner: HELIUS       │
├────────────────────────────────────────────────────────────────────┤
│ 🎯 EXECUTION DRIFT                                                │
│ Status: OK │ Avg: +0.12% │ Last: -0.05% │ 🐋Boost: 3           │
├────────────────────────────────────────────────────────────────────┤
│ 📊 SIGNAL PIPELINE                                                │
│ Generated: 15 │ ML Pass: 8 │ Scorer Pass: 5 │ Executed: 3       │
├────────────────────────────────────────────────────────────────────┤
│ 💹 RISK METRICS                                                   │
│ Drawdown: -4.2% │ Sharpe: 1.2 │ Win Rate: 58% │ Avg Hold: 12m   │
└────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 6A: Data Collection Layer

| Task | Component | Effort |
|------|-----------|--------|
| Add `get_stats()` to SignalScorer | Rust | Low |
| Add `get_race_stats()` to SlotConsensus | Rust | Low |
| Add `get_pipeline_stats()` to SignalScanner | Python | Low |
| Add `get_risk_metrics()` to CapitalManager | Python | Medium |

### Phase 6B: DashboardState Expansion

| Field | Type | Source |
|-------|------|--------|
| `scorer_calls` | int | SignalScorer |
| `scorer_avg_ms` | float | SignalScorer |
| `scorer_rejected` | int | SignalScorer |
| `helius_win_pct` | float | SlotConsensus |
| `signals_generated` | int | SignalScanner |
| `signals_executed` | int | SignalScanner |
| `max_drawdown_pct` | float | CapitalManager |
| `sharpe_ratio` | float | CapitalManager |

### Phase 6C: Display Refactoring

- Reorganize `_print_dashboard()` into modular section builders
- Add conditional section visibility based on available data
- Improve layout to accommodate new rows

---

## Verification

- [ ] All new `get_stats()` methods have unit tests
- [ ] Dashboard renders correctly with no data (graceful defaults)
- [ ] Dashboard renders correctly with full data
- [ ] No performance regression (dashboard refresh < 100ms)

---

## Dependencies

- Phase 4: SignalScorer must be deployed
- Phase 5A: Whale-Pulse must be active
- Phase 5B: ShadowManager must be collecting audits
