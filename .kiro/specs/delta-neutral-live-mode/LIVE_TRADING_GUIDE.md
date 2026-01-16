# Live Trading Quick Start Guide

**System**: Delta Neutral Engine (Funding Engine)  
**Mode**: Live Mainnet Trading with Auto-Rebalancing  
**Date**: 2026-01-15

---

## 🚀 Quick Start (3 Steps)

### Step 1: Start the Dashboard

```bash
python run_dashboard.py
```

**Expected Output**:
```
🚀 Starting Phantom Arbiter Command Center...
📊 Frontend available at http://localhost:8000
📈 Live price feed connected (Pyth WebSocket)
🔌 WebSocket server starting on ws://localhost:8765
🎛️  COMMAND CENTER ONLINE
```

### Step 2: Open Web UI

Navigate to: **http://localhost:8000**

### Step 3: Start Funding Engine in LIVE Mode

1. Find the **"Delta Neutral Engine"** card
2. Click **START** button
3. Select **LIVE** mode (not Paper)
4. Wait for connection confirmation

**Expected Log**:
```
[FUNDING] Initializing live mode with DriftAdapter...
[FUNDING] ✅ Connected to Drift Protocol (Live Mode)
```

---

## ✅ You're Now Live!

The system will automatically:

### 1. Monitor Delta Drift (Every 60 seconds)
```
Spot SOL: 10.0 SOL
Perp Position: -9.5 SOL (short)
Net Delta: +0.5 SOL
Drift: +5.0% ⚠️ (exceeds 1% tolerance)
```

### 2. Execute Auto-Rebalancing
```
[REBALANCER] Net delta +0.500000 SOL - expanding short by 0.500000
[REBALANCER] 🔴 LIVE MODE: Executing EXPAND_SHORT for 0.500000 SOL
[REBALANCER] ✅ Rebalance executed: EXPAND_SHORT 0.500000 SOL-PERP
[REBALANCER] Transaction: 5Kq7x8Ym3...
```

### 3. Maintain Delta Neutrality
```
Spot SOL: 10.0 SOL
Perp Position: -10.0 SOL (short)
Net Delta: 0.0 SOL ✅
Drift: 0.0% ✅
```

---

## 📊 What You'll See in the UI

### Health Gauge
- **Green (>50%)**: Safe ✅
- **Yellow (20-50%)**: Warning ⚠️
- **Red (<20%)**: Critical 🚨

### Position Table (Combat Zone)
| Market | Side | Size | Entry | Mark | uPnL | Liq. Price | Actions |
|--------|------|------|-------|------|------|------------|---------|
| SOL-PERP | SHORT | 10.000 | 145.23 | 147.50 | -$22.70 | $180.00 | Close |

### Delta Neutrality
- **Net Delta**: 0.05 SOL
- **Status**: NEUTRAL ✅

### Leverage Meter
- **Current**: 2.1x
- **Maximum**: 20x
- **Safe Zone**: <5x ✅

---

## 🎯 Manual Position Management

### Opening Positions

**From Market Opportunities Table**:
1. Scroll to "📈 Market Opportunities"
2. Find your market (SOL-PERP, BTC-PERP, ETH-PERP, etc.)
3. Click **"Start"** button
4. Enter size (e.g., `0.1` for 0.1 SOL)
5. Confirm

**From Best Opportunities Cards**:
1. Click on an opportunity card
2. Enter size when prompted
3. Confirm

**Result**:
```
✅ Position opened: short 0.1 SOL-PERP
Transaction: 5Kq7x...
```

### Closing Positions

1. Find position in "⚔️ Combat Zone" table
2. Click **"Close"** button
3. Confirm closure

**Result**:
```
✅ Position closed: SOL-PERP
Transaction: 3Hm9z...
PnL Settled: +$0.45
```

---

## ⚙️ Configuration

### Default Settings

```python
drift_tolerance_pct = 1.0%      # Rebalance when drift > 1%
cooldown_seconds = 1800         # 30 minutes between rebalances
min_trade_size = 0.005 SOL      # Minimum rebalance size
max_leverage = 5.0x             # Maximum leverage
loop_interval = 60 seconds      # Check delta every 60s
```

### Custom Configuration (Optional)

Edit `src/engines/funding/logic.py`:

```python
config = RebalanceConfig(
    drift_tolerance_pct=0.5,      # Tighter tolerance (0.5%)
    cooldown_seconds=900,          # Shorter cooldown (15 min)
    min_trade_size=0.01,           # Larger minimum size
    max_leverage=3.0,              # Lower leverage limit
    loop_interval_seconds=30       # More frequent checks
)
```

---

## 🛡️ Safety Features

### 1. Leverage Limit (5x)
- Rebalances blocked if leverage would exceed 5x
- Protects against liquidation risk

### 2. Cooldown Period (30 min)
- Prevents excessive trading costs
- Ensures economic viability

### 3. Minimum Trade Size (0.005 SOL)
- Filters out dust trades
- Ensures trades are economically viable

### 4. Health Monitoring
- **Warning**: Health < 50%
- **Critical**: Health < 20%
- Real-time alerts to UI

### 5. Transaction Simulation
- All trades simulated before submission
- Failed simulations prevent execution
- Saves gas on invalid trades

### 6. Vault Synchronization
- Syncs after every operation
- Retry logic with exponential backoff
- Ensures accurate capital tracking

---

## 📈 Example Trading Session

### Initial State
```
Time: 10:00 AM
Spot SOL: 10.0 SOL
Perp Position: -10.0 SOL (short)
Net Delta: 0.0 SOL
Drift: 0.0%
Status: NEUTRAL ✅
```

### User Deposits 1 SOL
```
Time: 10:05 AM
Action: Deposit 1.0 SOL via UI
Spot SOL: 11.0 SOL
Perp Position: -10.0 SOL (short)
Net Delta: +1.0 SOL
Drift: +9.1% ⚠️
Status: DRIFTING
```

### Auto-Rebalance Triggered
```
Time: 10:06 AM (next tick)
Action: EXPAND_SHORT by 1.0 SOL
Spot SOL: 11.0 SOL
Perp Position: -11.0 SOL (short)
Net Delta: 0.0 SOL
Drift: 0.0%
Status: NEUTRAL ✅
Transaction: 5Kq7x...
```

### Cooldown Active
```
Time: 10:15 AM
Drift: +1.5% (exceeds tolerance)
Action: Skip rebalance (cooldown active, 21 min remaining)
```

### Cooldown Expired
```
Time: 10:36 AM
Drift: +1.5% (exceeds tolerance)
Action: EXPAND_SHORT by 0.15 SOL
Transaction: 3Hm9z...
Status: NEUTRAL ✅
```

---

## 🔍 Monitoring & Logs

### Key Log Messages

**Engine Started**:
```
[FUNDING] Initializing live mode with DriftAdapter...
[FUNDING] ✅ Connected to Drift Protocol (Live Mode)
```

**Delta Drift Detected**:
```
[REBALANCER] Net delta +0.150000 SOL - expanding short by 0.150000
```

**Rebalance Executing**:
```
[REBALANCER] 🔴 LIVE MODE: Executing EXPAND_SHORT for 0.150000 SOL
```

**Rebalance Success**:
```
[REBALANCER] ✅ Rebalance executed: EXPAND_SHORT 0.150000 SOL-PERP
[REBALANCER] Transaction: 5Kq7x8Ym3...
[FUNDING] ✅ Vault synchronized with Drift
```

**Rebalance Blocked**:
```
[REBALANCER] Rebalance blocked by validation: Leverage would exceed 5.0x
```

**Health Warning**:
```
[FUNDING] ⚠️  WARNING: Health ratio 45.2% - Consider adding collateral
```

**Health Critical**:
```
[FUNDING] 🚨 CRITICAL: Health ratio 18.7% - Risk of liquidation!
```

---

## ⚠️ Troubleshooting

### Engine Won't Start

**Problem**: "Failed to connect to Drift Protocol"

**Solution**:
1. Check `.env` file has `SOLANA_PRIVATE_KEY`
2. Verify Drift account is initialized
3. Check RPC endpoint is accessible

### Rebalance Not Executing

**Problem**: Drift exceeds 1% but no rebalance

**Possible Causes**:
1. **Cooldown Active**: Wait for cooldown to expire (check logs)
2. **Size Too Small**: Correction < 0.005 SOL (check logs)
3. **Leverage Limit**: Would exceed 5x (check logs)
4. **Health Too Low**: Health < 60% (check UI)

### Position Not Appearing in UI

**Problem**: Opened position but not in Combat Zone table

**Solution**:
1. Wait for next SYSTEM_STATS broadcast (1 second)
2. Check transaction on Solscan
3. Verify WebSocket connection (check browser console)

### High Drift Persists

**Problem**: Drift stays high despite rebalancing

**Possible Causes**:
1. **Price Movement**: SOL price changed during rebalance
2. **Partial Fill**: Order not fully filled
3. **Multiple Markets**: Positions on multiple markets (only SOL-PERP auto-rebalances)

**Solution**: Manually close/open positions to correct drift

---

## 📞 Support

### Check System Status
1. Open browser console (F12)
2. Look for WebSocket messages
3. Check for errors

### View Logs
```bash
# Real-time logs
tail -f logs/funding_engine.log

# Search for errors
grep ERROR logs/funding_engine.log

# Search for rebalances
grep REBALANCER logs/funding_engine.log
```

### Verify On-Chain State
1. Visit: https://app.drift.trade
2. Connect your wallet
3. Compare positions with UI

---

## 🎉 You're Ready!

Your automated delta-neutral trading system is now operational on mainnet. The engine will:

✅ Monitor delta drift every 60 seconds  
✅ Auto-rebalance when drift exceeds 1%  
✅ Respect cooldown periods (30 minutes)  
✅ Enforce leverage limits (5x)  
✅ Sync vault state after trades  
✅ Alert on health issues  
✅ Log all operations comprehensively  

**Happy trading! 🚀**

---

**Document Version**: 1.0  
**Created**: 2026-01-15  
**Author**: Kiro AI Assistant
