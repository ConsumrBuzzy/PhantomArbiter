# PhantomArbiter Multi-Market Action Plan
## $14 Capital → $42+ Target (300% ROI in 30 Days)

---

## 📊 Current State (February 14, 2026)

### ✅ Completed Infrastructure
1. **Tensor GraphQL Client** - READY (awaiting API key 24-48hrs)
2. **Magic Eden REST Client** - WORKING (tested, 0 results at 0.009 SOL)
3. **NFT Burn Module** - COMPLETE (buyer, burner, scanner, CLI)
4. **Database System** - OPERATIONAL (workflow tracking)

### 🔍 Market Intelligence
1. **NFT Floors**: Too high for original janitor thesis (>0.6 SOL minimum)
2. **Hadeswap**: 0% fees but complex SDK integration
3. **Star Atlas**: High potential, z.ink launch imminent
4. **ME Volatility**: Unlock events create 15% swings

---

## 🎯 Three-Pronged Strategy

### Strategy A: NFT Janitor + Volatility (Conservative)
**Capital**: $5 (36%)
**Target ROI**: 50-89% in 30 days
**Risk**: LOW

### Strategy B: Star Atlas Arbitrage (Aggressive)
**Capital**: $7 (50%)
**Target ROI**: 300% in 30 days
**Risk**: MEDIUM

### Strategy C: Reserve
**Capital**: $2 (14%)
**Purpose**: Gas, fees, emergency liquidity

---

## 📅 Week-by-Week Implementation

### **WEEK 1: Validation & Foundation** (Feb 14-21)

#### Day 1-2: Hadeswap Research (IMMEDIATE)
**Goal**: Determine if 0% fees unlock NFT Janitor profitability

**Tasks**:
1. Install Hadeswap SDK (`npm install hadeswap-sdk`)
2. Build Node.js wrapper to query NFT pools
3. Create Python bridge via subprocess
4. Query 10 collections for pool prices
5. Compare vs Magic Eden/Tensor

**Deliverable**: `hadeswap_client.py` + price comparison data

**Success Criteria**: Find NFTs <0.011 SOL in Hadeswap pools

---

#### Day 3-4: Magic Eden Price Tracker (PARALLEL)
**Goal**: Capture volatility opportunities from unlock events

**Tasks**:
1. Add historical floor price database
2. Build 5-minute polling loop
3. Create alert system for >15% drops
4. Monitor 10 volatile collections
5. Track next 3 unlock events

**Deliverable**: `magic_eden_tracker.py` + alert system

**Success Criteria**: Catch 1 unlock event before Week 2

---

#### Day 5-7: Tensor API Integration (WHEN KEY ARRIVES)
**Goal**: Compare all 3 marketplaces with real data

**Tasks**:
1. Receive Tensor API key (expected by Day 3-4)
2. Run `test_tensor_real.py` against 49 collections
3. Compare results: Tensor vs Magic Eden vs Hadeswap
4. Calculate profitability per marketplace
5. **FINAL DECISION**: Proceed with NFT Janitor or pivot?

**Deliverable**: Final profitability report + decision document

**Success Criteria**: Identify if NFT Janitor is viable with ANY marketplace

---

### **WEEK 2: Star Atlas Preparation** (Feb 22-28)

#### Day 8-10: Galactic Marketplace Client
**Goal**: Build Star Atlas price discovery system

**Tasks**:
1. Study [Galactic Marketplace API](https://build.staratlas.com/dev-resources/on-chain-game-systems/galactic-marketplace)
2. Build GraphQL client for marketplace queries
3. Implement R4 resource price tracking
4. Map starbase pricing variance
5. Identify arbitrage spreads

**Deliverable**: `star_atlas_client.py` + price tracking

**Success Criteria**: Track price variance across 5+ starbases

---

#### Day 11-13: z.ink Research & Integration
**Goal**: Prepare for z.ink mainnet launch

**Tasks**:
1. Research z.ink testnet access
2. Study SVM compatibility with existing code
3. Build z.ink RPC connection module
4. Test transaction building on testnet
5. Plan deployment strategy

**Deliverable**: `zink_connector.py` + deployment guide

**Success Criteria**: Successfully send test transaction on z.ink testnet

---

#### Day 14: Automation Framework
**Goal**: Build SAGE mission automation

**Tasks**:
1. Study SAGE mission mechanics
2. Build fleet movement automation
3. Create resource purchase/sell scheduler
4. Implement profit tracking
5. Test in dry-run mode

**Deliverable**: `sage_automator.py` + mission scheduler

**Success Criteria**: Simulate 1 full mission cycle

---

### **WEEK 3: Live Deployment** (Mar 1-7)

#### If NFT Janitor is Viable:
1. Deploy with $5 capital
2. Execute 1 NFT/day target
3. Track profit vs. estimates
4. Scale if >$0.30 profit/NFT achieved

#### If Star Atlas z.ink Launches:
1. Deploy arbitrage bot with $7 capital
2. Start with starbase price variance plays
3. Expand to mission cycle arbitrage
4. Monitor for 300% ROI trajectory

#### If Both Unviable:
1. Pivot to Gemini's Tier 2 targets:
   - Aurory (GraphQL arbitrage)
   - Honeyland (harvest automation)
   - Meteora DLMM (liquidity provision)

---

## 🔧 Technical Implementation Priorities

### Priority 1: Hadeswap Integration (2-4 hours)
**Why**: 0% fees could make NFT Janitor viable
**Blocker**: TypeScript SDK needs Python bridge
**Solution**: Node.js subprocess wrapper

**Code Skeleton**:
```python
# hadeswap_client.py
import subprocess
import json

class HadeswapClient:
    def query_pools(self, collection_id: str):
        result = subprocess.run(
            ['node', 'scripts/hadeswap_query.js', collection_id],
            capture_output=True, text=True
        )
        return json.loads(result.stdout)
```

---

### Priority 2: Magic Eden Tracker (3-4 hours)
**Why**: Unlock events are predictable profit
**Blocker**: No historical price API
**Solution**: Build custom tracking layer

**Code Skeleton**:
```python
# magic_eden_tracker.py
class PriceTracker:
    def __init__(self):
        self.db = DatabaseCore()
        self.client = MagicEdenClient()

    def track_collections(self, symbols: List[str]):
        while True:
            for symbol in symbols:
                stats = self.client.get_collection_stats(symbol)
                floor = stats['floorPrice'] / 1e9

                # Store historical data
                self.db.insert_floor_price(symbol, floor, time.time())

                # Check for 15%+ drops in last hour
                if self.detect_drop(symbol, threshold=0.15):
                    self.alert_opportunity(symbol, floor)

            time.sleep(300)  # 5 minute polling
```

---

### Priority 3: Star Atlas Client (8-10 hours)
**Why**: Highest ROI potential per Gemini
**Blocker**: z.ink not launched yet
**Solution**: Build on Solana, migrate to z.ink

**Code Skeleton**:
```python
# star_atlas_client.py
class StarAtlasClient:
    def __init__(self, network='mainnet'):
        self.api_url = "https://galaxy.staratlas.com/graphql"
        self.marketplace_program = "..."  # Galactic Marketplace program ID

    def get_resource_prices(self, starbase_id: str):
        # Query marketplace for R4 resource listings
        pass

    def find_arbitrage_opportunities(self):
        # Compare prices across starbases
        # Return profitable trades
        pass
```

---

## 💰 Capital Allocation Table

| Week | NFT Janitor | Star Atlas | Reserve | Notes |
|------|-------------|------------|---------|-------|
| 1 | $0 (testing) | $0 (research) | $14 | Hold until data validates |
| 2 | $0 | $2 (testnet) | $12 | Test Star Atlas on testnet |
| 3 | $5 (if viable) | $7 (if z.ink live) | $2 | Deploy validated strategies |
| 4+ | Scale up | Scale up | $2 min | Reinvest profits |

---

## 📈 Success Metrics

### NFT Janitor KPIs
- Opportunities found per day: >1
- Profit per NFT: >$0.30
- Success rate: >80%
- Capital turnover: 1x per day

### Star Atlas KPIs
- Arbitrage spread: >5%
- Trades per day: >2
- Win rate: >70%
- Daily profit: >$1.50

### Overall Target
- 30-day ROI: >100%
- Break-even: <7 days
- Profit target: $14+ (2x capital)

---

## ⚠️ Risk Management

### Stop-Loss Rules
1. **NFT Janitor**: If <$0.20 profit/NFT after 5 trades → STOP
2. **Star Atlas**: If 3 consecutive losses → REDUCE position 50%
3. **Overall**: If capital drops to $10 → PAUSE and reassess

### Contingency Plans
- **Plan A fails**: Pivot to Plan B immediately
- **Both fail**: Research Tier 2 targets (Aurory, Honeyland)
- **Capital loss >30%**: Stop all automation, manual analysis only

---

## 🎯 Next 24 Hours (IMMEDIATE ACTIONS)

### Today (Feb 14):
1. ✅ Research Hadeswap (DONE)
2. ✅ Research Star Atlas (DONE)
3. ✅ Research Magic Eden volatility (DONE)
4. 🔧 **START**: Build Hadeswap Node.js query script

### Tomorrow (Feb 15):
1. Complete Hadeswap Python bridge
2. Query 10 collections via Hadeswap
3. Compare with Magic Eden prices
4. Start Magic Eden price tracker development

### Day After (Feb 16):
1. Finish Magic Eden tracker
2. Monitor for first unlock event
3. Wait for Tensor API key
4. Begin Star Atlas client if time permits

---

## 📝 User Decision Required

**Which path should we prioritize?**

**Option A: Complete NFT Janitor (Conservative)**
- Finish Hadeswap integration
- Build price tracker
- Wait for Tensor key
- Validate with real data
- **Timeline**: 3-5 days to decision point

**Option B: Pivot to Star Atlas (Aggressive)**
- Skip Hadeswap complexity
- Focus on Star Atlas client
- Prepare for z.ink launch
- Higher ROI potential
- **Timeline**: 7-10 days to deployment

**Option C: Parallel Development (Maximum Optionality)**
- Build both simultaneously
- Deploy whichever launches first
- Most work but best coverage
- **Timeline**: 10-14 days to both ready

**My Recommendation**: **Option C** - Build both, but prioritize Star Atlas since z.ink timing aligns with Gemini's thesis and market data shows NFT Janitor margins are razor-thin.

---

## 📚 Key Resources

- **NFT Janitor**: `NFT_JANITOR_README.md`
- **Market Analysis**: `MARKETPLACE_API_ANALYSIS.md`
- **Multi-Market**: `MULTI_MARKET_ANALYSIS.md`
- **Magic Eden Results**: `MAGIC_EDEN_RESULTS.md`
- **Tensor Status**: `TENSOR_STATUS_UPDATE.md`

Ready to proceed with implementation?
