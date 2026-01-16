# Phantom Arbiter Trading Engines Explained

## Overview

Your system has **4 main trading engines**, each implementing a different strategy. Here's what each one does:

---

## 1. 🎯 **Funding Engine** (Delta Neutral Engine)

**File**: `src/engines/funding/logic.py`  
**Strategy**: Earn funding rates while staying market-neutral  
**Status**: ✅ Fully implemented (paper + live mode)

### What It Does
The Funding Engine implements a **delta-neutral strategy** on Drift Protocol:
- **Holds spot SOL** in your wallet
- **Shorts SOL-PERP** futures on Drift Protocol
- **Earns funding rates** (periodic payments between longs and shorts)
- **Stays market-neutral** (no directional risk from SOL price movements)

### How It Works
```
Example Position:
- Spot: +10 SOL in wallet ($1,500)
- Perp: -10 SOL short on Drift ($1,500)
- Net Delta: 0 SOL (perfectly hedged)

If SOL goes up 10%:
- Spot gains: +$150
- Perp loses: -$150
- Net P&L: $0 (market neutral)

But you still earn funding rates:
- If shorts pay longs: You pay funding
- If longs pay shorts: You receive funding ✅
```

### Key Features
1. **Auto-Rebalancing**: Automatically corrects "delta drift" when hedge becomes imperfect
2. **Health Monitoring**: Tracks liquidation risk (health ratio 0-100%)
3. **Safety Gates**: Prevents unprofitable trades (checks fees vs. expected revenue)
4. **Paper Mode**: Simulates everything with VirtualDriver
5. **Live Mode**: Real trading on Drift Protocol mainnet

### Current Work (Delta Neutral Live Mode Spec)
You're working on **Phase 1 & 2** of the spec:
- ✅ **Phase 1**: Backend API to fetch live funding rates from Drift
- ✅ **Phase 2**: Frontend UI to display market opportunities
- ⏳ **Phase 3**: Position management UI (Take/Leave position buttons)
- ⏳ **Phase 4**: WebSocket integration for real-time updates

---

## 2. 💧 **LST Engine** (LST De-Pegger)

**File**: `src/engines/lst_depeg/logic.py`  
**Strategy**: Buy discounted Liquid Staking Tokens  
**Status**: ⚠️ Basic implementation (monitoring only)

### What It Does
The LST Engine monitors **Liquid Staking Token (LST) prices** for de-peg opportunities:
- **Monitors**: jitoSOL, mSOL, bSOL, etc.
- **Detects**: When LST trades below fair value (de-pegged)
- **Executes**: Buys discounted LST, waits for re-peg, sells for profit

### How It Works
```
Example Trade:
- Fair Value: 1 jitoSOL = 1.05 SOL (5% staking premium)
- De-Peg Event: 1 jitoSOL = 1.02 SOL (only 2% premium)
- Opportunity: Buy jitoSOL at discount
- Exit: Sell when price returns to 1.05 SOL

Profit: 3% gain when re-peg occurs
```

### Key Features
1. **Price Monitoring**: Fetches real-time LST/SOL prices from Jupiter
2. **De-Peg Detection**: Alerts when price deviates from fair value
3. **Fair Value Tracking**: Maintains expected LST/SOL ratios
4. **Paper Mode**: Simulates LST purchases with VirtualDriver

### Current Status
- ✅ Monitoring and alerting implemented
- ⚠️ Live trading not fully implemented
- ⚠️ No auto-execution (manual intervention required)

---

## 3. 🎲 **Scalp Engine** (Meme/Token Scalper)

**File**: `src/engines/scalp/logic.py`  
**Strategy**: Quick in-and-out trades on volatile tokens  
**Status**: ✅ Implemented (paper + live mode)

### What It Does
The Scalp Engine trades **high-volatility meme tokens** for quick profits:
- **Scans**: Multiple token pairs for momentum signals
- **Enters**: When strong buy/sell signals detected
- **Exits**: Quickly (seconds to minutes) for small profits
- **Manages**: Multiple "pods" (sub-strategies) simultaneously

### How It Works
```
Example Trade:
- Signal: BONK shows strong buy momentum
- Entry: Buy 10,000 BONK at $0.00001
- Target: +2% profit ($0.000102)
- Stop Loss: -1% loss ($0.0000099)
- Exit: Sell when target hit or stop triggered

Typical hold time: 30 seconds to 5 minutes
```

### Key Features
1. **Multi-Pod System**: Runs multiple strategies in parallel
2. **Signal Detection**: Technical indicators for entry/exit
3. **Risk Management**: Stop losses and position sizing
4. **Paper Mode**: Simulates scalping with VirtualDriver
5. **Live Mode**: Real trades via Jupiter aggregator

### Current Status
- ✅ Fully functional in paper mode
- ✅ Live mode available (use with caution)
- ⚠️ High risk - requires careful monitoring

---

## 4. 🔄 **Arb Engine** (Trip Hopper)

**File**: `src/engines/arb/logic.py`  
**Strategy**: Arbitrage across DEXes  
**Status**: ✅ Implemented (paper + live mode)

### What It Does
The Arb Engine finds **price differences** across decentralized exchanges:
- **Scans**: Multiple DEXes (Orca, Raydium, Jupiter, etc.)
- **Detects**: Price discrepancies for the same token
- **Executes**: Buy on cheap DEX, sell on expensive DEX
- **Profits**: From price difference minus fees

### How It Works
```
Example Arbitrage:
- Orca: SOL/USDC = $150.00
- Raydium: SOL/USDC = $150.50
- Opportunity: Buy on Orca, sell on Raydium

Profit Calculation:
- Buy 10 SOL on Orca: $1,500
- Sell 10 SOL on Raydium: $1,505
- Gross Profit: $5
- Fees: ~$1 (swap fees + gas)
- Net Profit: $4 (0.27%)
```

### Key Features
1. **Multi-DEX Scanning**: Monitors 5+ DEXes simultaneously
2. **Route Optimization**: Finds best multi-hop paths
3. **Fee Calculation**: Accounts for all costs before executing
4. **Jito Integration**: Uses MEV protection for better execution
5. **Paper Mode**: Simulates arbitrage with VirtualDriver
6. **Live Mode**: Real trades via Jupiter aggregator

### Current Status
- ✅ Fully functional in paper mode
- ✅ Live mode available
- ⚠️ Requires fast RPC for profitability

---

## Engine Comparison Table

| Engine | Strategy | Risk Level | Typical Hold Time | Profit Target | Status |
|--------|----------|------------|-------------------|---------------|--------|
| **Funding** | Delta Neutral | 🟢 Low | Days to Weeks | 5-15% APR | ✅ Production |
| **LST** | De-Peg Arbitrage | 🟡 Medium | Hours to Days | 1-5% per trade | ⚠️ Monitoring Only |
| **Scalp** | Momentum Trading | 🔴 High | Seconds to Minutes | 0.5-2% per trade | ✅ Production |
| **Arb** | Cross-DEX Arbitrage | 🟡 Medium | Seconds | 0.1-0.5% per trade | ✅ Production |

---

## How They Work Together

### Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    Web Dashboard                         │
│              (http://localhost:8000)                     │
└─────────────────────────────────────────────────────────┘
                          ↕ WebSocket
┌─────────────────────────────────────────────────────────┐
│                  run_dashboard.py                        │
│              (WebSocket Server :8765)                    │
└─────────────────────────────────────────────────────────┘
         ↓              ↓              ↓              ↓
    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
    │Funding │    │  LST   │    │ Scalp  │    │  Arb   │
    │Engine  │    │ Engine │    │ Engine │    │ Engine │
    └────────┘    └────────┘    └────────┘    └────────┘
         ↓              ↓              ↓              ↓
    ┌────────────────────────────────────────────────────┐
    │              Paper Mode (VirtualDriver)            │
    │                      OR                            │
    │         Live Mode (Drift/Jupiter/DEXes)           │
    └────────────────────────────────────────────────────┘
```

### Shared Components
All engines share:
- **BaseEngine**: Common start/stop/tick logic
- **VirtualDriver**: Paper trading simulation
- **VaultManager**: Capital allocation tracking
- **SafetyGates**: Risk management checks
- **WebSocket**: Real-time UI updates

---

## Your Current Work: Delta Neutral Live Mode

You're specifically working on the **Funding Engine** (Delta Neutral) to add:

### ✅ Completed (Phase 1 & 2)
1. **Backend API**: `/api/drift/markets` endpoint
   - Fetches live funding rates from Drift Protocol
   - Returns market data (APR, OI, volume)
   - Calculates aggregate statistics

2. **Frontend Display**: Market opportunities table
   - Shows all markets with funding rates
   - Highlights top 3 opportunities
   - Auto-refreshes every 30 seconds
   - Displays total OI and volume

### ⏳ Next Steps (Phase 3 & 4)
3. **Position Management UI**:
   - "Take Position" buttons for each market
   - "Leave Position" buttons for active positions
   - Position size input modals
   - Real-time position updates

4. **WebSocket Integration**:
   - Handle FUNDING_UPDATE messages
   - Handle COMMAND_RESULT responses
   - Handle HEALTH_ALERT warnings
   - Update UI in real-time

---

## Quick Reference

### Start an Engine (Paper Mode)
```python
# In run_dashboard.py, engines start automatically
# Control via Web UI at http://localhost:8000
```

### Start an Engine (Live Mode)
```python
# Set live_mode=True in run_dashboard.py
funding_engine = FundingEngine(live_mode=True)
await funding_engine.start()
```

### Check Engine Status
```bash
# Open Web UI
http://localhost:8000

# Check WebSocket connection
ws://localhost:8765
```

### View Logs
```bash
# All engines log to console via Loguru
# Check logs for engine activity
```

---

## Questions?

**Q: Which engine should I use?**  
A: Depends on your risk tolerance:
- **Low Risk**: Funding Engine (delta neutral)
- **Medium Risk**: LST Engine or Arb Engine
- **High Risk**: Scalp Engine

**Q: Can I run multiple engines at once?**  
A: Yes! In paper mode, run as many as you want. In live mode, only one live engine at a time (safety restriction).

**Q: What's the difference between Funding Engine and Delta Neutral Engine?**  
A: They're the same thing! "Funding Engine" is the code name, "Delta Neutral Engine" is the strategy name.

**Q: Where do I see live market data?**  
A: Open http://localhost:8000 and navigate to the "Drift" engine tab. You'll see the funding rates table and opportunity cards (Phase 1 & 2 work you just completed).

---

**Need more details on a specific engine? Let me know!**
