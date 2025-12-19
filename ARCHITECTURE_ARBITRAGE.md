# Arbiter Architecture & Goals

## 🎯 Current State (V2.0)

Spatial arbitrage system scanning 4 core pairs across Jupiter, Raydium, and Orca.

### Active Features
- ✅ Multi-DEX price feeds (Jupiter, Raydium, Orca)
- ✅ Spread detection with min threshold filtering
- ✅ Paper trading with simulated fees (0.2% round-trip)
- ✅ Live trading with atomic execution
- ✅ Session logging and P&L tracking

### Current Limitations
- 4 pairs only (SOL, BONK, WIF, JUP)
- Single-thread scanning
- No MEV protection (Jito bundles available but not default)

---

## 🚀 Desired Goal (V3.0)

### Phase 1: Reliability
- [ ] Connection health monitoring with auto-reconnect
- [ ] Rate limit detection and backoff
- [ ] Graceful degradation (skip DEX if unavailable)

### Phase 2: Profitability
- [ ] Dynamic fee estimation (actual gas costs)
- [ ] Slippage prediction based on liquidity depth
- [ ] Position sizing: Kelly criterion or fixed fraction

### Phase 3: Scale
- [ ] Expand to 20+ pairs (filtered by volume)
- [ ] Parallel DEX scanning with asyncio
- [ ] Jito bundles enabled by default for MEV protection

### Phase 4: Intelligence
- [ ] Historical spread patterns (best times to trade)
- [ ] Anomaly detection (unusual spread = possible rug)
- [ ] Integration with ScoutAgent for smart money signals

---

## 📁 Module Structure

```
src/arbiter/
├── arbiter.py           # PhantomArbiter orchestrator
├── core/
│   ├── executor.py      # ArbitrageExecutor (paper/live)
│   ├── spread_detector.py
│   ├── risk_manager.py
│   ├── orchestrator.py
│   └── atomic_executor.py
├── strategies/
│   ├── spatial_arb.py   # Buy DEX A → Sell DEX B
│   ├── triangular_arb.py
│   └── funding_arb.py   # Spot + Perp
└── monitoring/
    ├── live_dashboard.py
    └── telegram_alerts.py
```

---

## 🔄 Main Loop

```python
async def run(duration_minutes, scan_interval):
    while time < end_time:
        # 1. Scan all pairs across DEXs
        opportunities = await scan_opportunities()
        
        # 2. Filter by min_spread and profitability
        profitable = [o for o in opportunities if o.net_profit > 0]
        
        # 3. Execute best opportunity (cooldown per pair)
        for opp in sorted(profitable, key=lambda x: x.spread_pct):
            if not on_cooldown(opp.pair):
                await execute_trade(opp)
                break
        
        await asyncio.sleep(scan_interval)
```

---

## ⚙️ Configuration

```python
# Via ArbiterConfig dataclass
budget: float = 50.0        # Starting paper balance
min_spread: float = 0.20    # Minimum spread to consider
max_trade: float = 10.0     # Max trade size per execution
live_mode: bool = False     # Default to paper trading
full_wallet: bool = False   # Use entire wallet balance
```

---

## 📊 Success Metrics

| Metric | Target |
|--------|--------|
| Spread Detection Latency | < 500ms |
| Execution Success Rate | > 95% |
| Daily ROI (Paper) | > 0.5% |
| Scans Per Minute | 12+ |
