# Solana NFT Marketplace API Analysis - February 2026

## Executive Summary

Based on Gemini's "Master Manifest" and current market research, here are the viable alternatives to Tensor for NFT listing price data on Solana:

## I. Primary NFT Marketplaces (Ranked by API Access)

### 1. Magic Eden ✅ RECOMMENDED
**Status**: FREE API with attribution requirement
**Type**: REST API (not GraphQL)
**Endpoint**: `api-mainnet.magiceden.dev/v2`

**Advantages**:
- ✅ Free API access (no payment required)
- ✅ Comprehensive listing data
- ✅ Real-time floor prices
- ✅ Collection statistics
- ✅ 120 QPM rate limit (2 QPS)
- ✅ Multi-chain support (Solana, Ethereum, Polygon, Bitcoin)
- ✅ 1.5% marketplace fee (vs Tensor's 2%)

**API Endpoints for Janitor**:
```
GET /collections/{symbol}/listings
GET /collections/{symbol}/stats
GET /tokens/{mint_address}/listings
```

**Documentation**:
- [Magic Eden Solana API Overview](https://docs.magiceden.io/reference/solana-overview)
- [API Keys & Rate Limits](https://help.magiceden.io/en/articles/6533403-how-to-use-the-magic-eden-api-access-keys-rate-limits-docs)
- [SimpleHash Magic Eden API](https://simplehash.com/marketplaces/magiceden)

**Integration Effort**: 2-3 hours (REST API similar to existing patterns)

---

### 2. Hadeswap ⚠️ SPECIALIZED
**Status**: AMM-focused, commission-free trading
**Type**: On-chain AMM pools + Marketplace (with Tensor collaboration)
**Fee**: 0% commission (!)

**Advantages**:
- ✅ 0% marketplace fees (best for profitability)
- ✅ AMM pools for instant trading
- ✅ Professional trading interface
- ⚠️ Less documentation on public API

**Use Case**: Best for **live purchase execution** (0% fees maximize profit margin)

**Integration Effort**: Unknown (needs research into AMM pool structure)

---

### 3. Tensor (Current Implementation) ⏳
**Status**: Awaiting API key (24-48 hrs)
**Type**: GraphQL API
**Fee**: 2% marketplace fee

**Advantages**:
- ✅ GraphQL schema (already implemented)
- ✅ Professional HFT features
- ✅ Clean data structure
- ⚠️ Requires payment for API access
- ⚠️ Higher fees than alternatives

---

### 4. Coral Cube ❌ DEPRECATED
**Status**: Acquired by Magic Eden, now CLOSED
**Note**: No longer operational as of 2026

---

## II. Gaming Asset Marketplaces (Gemini's "Rider" Targets)

### 5. Star Atlas (SAGE) - z.ink Chain 🎮
**Status**: Migrating to z.ink SVM L1 (Q1/Q2 2026)
**Type**: Gaming marketplace on dedicated blockchain
**Assets**: R4 Resources (Fuel, Food, Ore), Ships, SDUs
**Currency**: $ATLAS, USDCz

**Advantages**:
- ✅ Fully on-chain IDL (every action = instruction)
- ✅ 99% lower fees than Solana mainnet
- ✅ No congestion (dedicated chain)
- ✅ GraphQL synergy potential
- 🎯 High automation edge for "Rider" strategies

**Marketplace**: https://play.staratlas.com/market/
**Data Source**: StarStat.org Market Data

**Integration Priority**: HIGH (Gemini's #1 recommendation for $14 capital)

---

### 6. Aurory (Nefties) 🎮
**Status**: Active on Solana Mainnet + SyncSpace
**Type**: Gaming NFT marketplace
**Assets**: Nefties (Amikos), Eggs, Consumables
**Currency**: $AURY

**Advantages**:
- ✅ GraphQL API available
- ✅ "Mispriced Rarity" arbitrage potential
- ✅ Standard asset pricing inconsistencies
- 🎯 Good for small capital automation

**Integration Priority**: MEDIUM

---

### 7. Honeyland 🎮
**Status**: Active on Solana Mainnet
**Type**: Idle game marketplace
**Assets**: Bees, Queens, Honey ($HXD), Shards
**Currency**: $HXD

**Advantages**:
- ✅ Passive mission automation
- ✅ Harvest/Hunt cycle optimization
- ✅ Predictable yield mechanics
- 🎯 Cron-job friendly

**Integration Priority**: MEDIUM

---

### 8. Nyan Heroes 🎮
**Status**: Active on Solana Mainnet
**Type**: Mech shooter game marketplace
**Assets**: Mechs, Nyans
**Currency**: $NYAN

**Advantages**:
- ✅ High volatility (8%+ daily swings)
- ✅ "Unlock event" floor sweeping opportunities
- ✅ Predictable price patterns
- 🎯 Good for volatility sniping

**Integration Priority**: LOW (higher capital required)

---

## III. Recommended Multi-Marketplace Strategy

### Phase 1: Magic Eden Integration (IMMEDIATE)
**Why**: Free API, no waiting, lower fees than Tensor

1. **Build Magic Eden Client** (`magic_eden_client.py`)
   - REST API wrapper
   - Collection listing endpoint
   - Floor price tracking
   - Legacy NFT filtering

2. **Update Scanner** to use Magic Eden as primary source
   - Parallel queries to both Tensor (when key arrives) and Magic Eden
   - Price arbitrage detection between marketplaces
   - Choose cheaper marketplace for purchases

3. **Timeline**: 2-3 hours implementation

---

### Phase 2: Hadeswap Integration (COST OPTIMIZATION)
**Why**: 0% fees = maximum profit per NFT

1. **Research Hadeswap AMM structure**
   - Understand pool mechanics
   - Direct on-chain trading vs marketplace

2. **Build purchase executor** using Hadeswap
   - Bypass marketplace fees entirely
   - Increase profit margin from 0.0049 SOL to 0.0051+ SOL

3. **Timeline**: 4-6 hours research + implementation

---

### Phase 3: Star Atlas Integration (EXPANSION)
**Why**: Gemini's #1 ROI recommendation for small capital

1. **Wait for z.ink mainnet launch** (Q1/Q2 2026)
2. **Build z.ink RPC connection** (similar to Solana)
3. **Implement SAGE "Rider" automation**
   - R4 resource arbitrage
   - Fleet automation
   - Mission optimization

4. **Timeline**: Post-mainnet launch

---

## IV. Immediate Action Plan

### Option A: Continue with Tensor (WAIT)
✅ Code complete
⏳ Wait 24-48 hours for API key
🎯 GraphQL implementation already done

### Option B: Pivot to Magic Eden (ACT NOW)
✅ FREE API access
✅ Lower fees (1.5% vs 2%)
✅ No payment required
🎯 Can start testing TODAY

### Option C: Dual Implementation (BEST)
✅ Use Magic Eden while waiting for Tensor key
✅ Implement price arbitrage between marketplaces
✅ Choose best execution venue per NFT
🎯 Maximum flexibility and profitability

---

## V. Code Implementation Priority

### Tier 1 (Immediate ROI - $14 Capital Compatible)
1. ✅ **Tensor GraphQL** - COMPLETE (waiting on key)
2. 🔧 **Magic Eden REST API** - 2-3 hours to implement
3. 🔧 **Hadeswap AMM** - Research + implement for 0% fees

### Tier 2 (Expansion - Gaming Markets)
4. 🎮 **Star Atlas (z.ink)** - Wait for mainnet, highest ROI potential
5. 🎮 **Aurory GraphQL** - Medium priority, good for automation
6. 🎮 **Honeyland** - Passive income optimization

### Tier 3 (Advanced - Higher Capital)
7. 🎮 **Nyan Heroes** - Volatility trading (needs monitoring)

---

## VI. Magic Eden vs Tensor Comparison

| Feature | Magic Eden | Tensor |
|---------|-----------|--------|
| **API Access** | FREE (attribution) | PAID (19,873 lamports) |
| **API Type** | REST | GraphQL |
| **Rate Limit** | 120 QPM (2 QPS) | Unknown (pending key) |
| **Marketplace Fee** | 1.5% | 2% |
| **Legacy NFT Support** | ✅ Yes | ✅ Yes |
| **Real-time Data** | ✅ Yes | ✅ Yes |
| **Documentation** | Excellent | Good |
| **Multi-chain** | ✅ Yes | ❌ Solana only |
| **Implementation Time** | 2-3 hours | ✅ COMPLETE |

**Verdict**: Magic Eden offers better economics and immediate access. Use both for arbitrage.

---

## VII. Sources & References

### NFT Marketplaces
- [Top 5+1 Solana NFT Marketplaces 2026](https://smithii.io/en/solana-nft-marketplace/)
- [14 Best Solana NFT Marketplaces](https://www.alchemy.com/overviews/solana-nft-marketplaces)
- [Top 5 NFT Marketplaces on Solana 2026](https://www.quicknode.com/builders-guide/best/top-5-nft-marketplaces-on-solana)
- [NFT Marketplaces Comparison (Dune Analytics)](https://dune.com/lily212/nft-marketplaces-in-solana)

### Magic Eden
- [Magic Eden Solana API Documentation](https://docs.magiceden.io/reference/solana-overview)
- [API Keys & Rate Limits Guide](https://help.magiceden.io/en/articles/6533403-how-to-use-the-magic-eden-api-access-keys-rate-limits-docs)
- [SimpleHash Magic Eden Integration](https://simplehash.com/marketplaces/magiceden)

### Star Atlas & z.ink
- [z.ink L1 Blockchain Overview](https://aephia.com/star-atlas/z-ink-everything-you-should-know/)
- [Star Atlas z.ink Launch News](https://blockworks.co/news/svm-layer-1-star-atlas-launch)
- [z.ink Airdrop Season Guide](https://aephia.com/star-atlas/z-ink-test-airdrop-season-the-guide/)
- [Star Atlas Market Data (StarStat)](https://www.starstat.org/market/daily)

---

## VIII. Recommendation

**IMMEDIATE ACTION**: Implement Magic Eden API integration

**Why**:
1. FREE API (no payment, no waiting)
2. Lower fees (1.5% vs 2%)
3. Can start testing NFT Janitor TODAY
4. When Tensor key arrives, use both for price arbitrage

**Next 48 Hours**:
- Build `magic_eden_client.py` REST API wrapper
- Update scanner to query Magic Eden listings
- Test with real NFT discovery
- Compare prices between Magic Eden and Tensor (when key arrives)

**Long Term** (per Gemini's manifest):
- Integrate Star Atlas (z.ink) for gaming asset arbitrage
- Expand to Aurory and Honeyland automation
- Build multi-marketplace arbitrage system
