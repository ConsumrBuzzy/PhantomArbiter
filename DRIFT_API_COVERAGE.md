# Drift Protocol API Coverage

Complete API integration for Drift Protocol perpetual futures exchange.

## 🎯 Overview

The `DriftAdapter` now provides comprehensive coverage of Drift Protocol's DLOB (Decentralized Limit Order Book) API, enabling real-time market data, orderbook access, and user position tracking.

## 📊 Available Methods

### 1. Market Data

#### `get_all_perp_markets() -> List[Dict]`
Fetch data for all perpetual markets.

**Returns:**
- `marketIndex`: Market index number
- `symbol`: Market symbol (e.g., "SOL-PERP")
- `markPrice`: Current mark price
- `oraclePrice`: Oracle/index price
- `fundingRate`: Hourly funding rate
- `openInterest`: Total open interest
- `volume24h`: 24-hour trading volume
- `baseAssetAmountLong`: Long side OI
- `baseAssetAmountShort`: Short side OI

**Example:**
```python
markets = await drift.get_all_perp_markets()
for market in markets:
    print(f"{market['symbol']}: ${market['markPrice']:,.2f}")
```

---

#### `get_funding_rate(market: str) -> Dict`
Get current funding rate for a specific market.

**Args:**
- `market`: Market symbol (e.g., "SOL-PERP")

**Returns:**
- `rate_8h`: 8-hour funding rate as percentage
- `rate_annual`: Annualized funding rate
- `is_positive`: True if longs pay shorts
- `mark_price`: Current mark price

**Example:**
```python
funding = await drift.get_funding_rate("SOL-PERP")
print(f"8h Rate: {funding['rate_8h']:.4f}%")
print(f"APR: {funding['rate_annual']:.2f}%")
```

---

#### `get_market_stats(market: str) -> Dict`
Get comprehensive statistics for a market.

**Returns:**
- `markPrice`: Current mark price
- `indexPrice`: Oracle/index price
- `fundingRate`: Hourly funding rate
- `fundingRate8h`: 8-hour funding rate
- `nextFundingTime`: Seconds until next funding
- `openInterest`: Total OI in USD
- `volume24h`: 24h volume in USD
- `longOI`: Long side OI in USD
- `shortOI`: Short side OI in USD
- `longShortRatio`: Long/Short ratio

**Example:**
```python
stats = await drift.get_market_stats("SOL-PERP")
print(f"OI: ${stats['openInterest']:,.0f}")
print(f"Long/Short: {stats['longShortRatio']:.2f}")
```

---

#### `get_oracle_price(market: str) -> float`
Get oracle price for a market.

**Example:**
```python
oracle_price = await drift.get_oracle_price("BTC-PERP")
print(f"Oracle: ${oracle_price:,.2f}")
```

---

#### `get_mark_price(market: str) -> float`
Get mark price for a market.

**Example:**
```python
mark_price = await drift.get_mark_price("ETH-PERP")
print(f"Mark: ${mark_price:,.2f}")
```

---

### 2. Orderbook Data

#### `get_orderbook(market: str, depth: int = 10) -> Dict`
Get L2 orderbook for a market.

**Args:**
- `market`: Market symbol
- `depth`: Number of price levels (default 10)

**Returns:**
- `bids`: List of [price, size] tuples
- `asks`: List of [price, size] tuples
- `spread`: Bid-ask spread
- `midPrice`: Mid price
- `bestBid`: Best bid price
- `bestAsk`: Best ask price

**Example:**
```python
orderbook = await drift.get_orderbook("SOL-PERP", depth=5)
print(f"Best Bid: ${orderbook['bestBid']:,.2f}")
print(f"Best Ask: ${orderbook['bestAsk']:,.2f}")
print(f"Spread: ${orderbook['spread']:.2f}")

for price, size in orderbook['bids'][:3]:
    print(f"  Bid: ${price:,.2f} x {size:.4f}")
```

---

### 3. User Data

#### `get_user_positions(user_address: str) -> List[Dict]`
Get all positions for a user.

**Args:**
- `user_address`: User's wallet address

**Returns:**
- `market`: Market symbol
- `marketIndex`: Market index
- `side`: "long" or "short"
- `size`: Position size
- `entryPrice`: Average entry price
- `markPrice`: Current mark price
- `unrealizedPnl`: Unrealized PnL
- `leverage`: Position leverage

**Example:**
```python
positions = await drift.get_user_positions("YOUR_WALLET_ADDRESS")
for pos in positions:
    print(f"{pos['market']}: {pos['side']} {pos['size']:.4f}")
    print(f"  Entry: ${pos['entryPrice']:,.2f}")
    print(f"  PnL: ${pos['unrealizedPnl']:,.2f}")
```

---

### 4. Timing

#### `get_time_to_funding() -> int`
Get seconds until next funding payment.

Drift pays funding every hour on the hour.

**Example:**
```python
seconds = await drift.get_time_to_funding()
minutes = seconds // 60
print(f"Next funding in: {minutes}m {seconds % 60}s")
```

---

## 🚀 Usage Examples

### Example 1: Monitor Top Markets by Volume
```python
from src.engines.funding.drift_adapter import DriftAdapter

drift = DriftAdapter("mainnet")

# Get all markets
markets = await drift.get_all_perp_markets()

# Sort by 24h volume
top_markets = sorted(markets, key=lambda m: m['volume24h'], reverse=True)[:5]

print("Top 5 Markets by Volume:")
for i, market in enumerate(top_markets, 1):
    print(f"{i}. {market['symbol']}: ${market['volume24h']:,.0f}")
```

### Example 2: Find Best Funding Opportunities
```python
# Get all markets
markets = await drift.get_all_perp_markets()

# Filter for positive funding > 0.01% hourly
opportunities = []
for market in markets:
    funding_hourly = market['fundingRate']
    if funding_hourly > 0.0001:  # 0.01% hourly
        apr = funding_hourly * 24 * 365 * 100
        opportunities.append({
            'symbol': market['symbol'],
            'apr': apr,
            'oi': market['openInterest'] * market['markPrice']
        })

# Sort by APR
opportunities.sort(key=lambda x: x['apr'], reverse=True)

print("Best Funding Opportunities:")
for opp in opportunities[:5]:
    print(f"{opp['symbol']}: {opp['apr']:.2f}% APR (OI: ${opp['oi']:,.0f})")
```

### Example 3: Monitor Orderbook Liquidity
```python
# Check liquidity for a market
orderbook = await drift.get_orderbook("SOL-PERP", depth=10)

# Calculate total liquidity within 1% of mid price
mid = orderbook['midPrice']
threshold = mid * 0.01

bid_liquidity = sum(size for price, size in orderbook['bids'] if mid - price <= threshold)
ask_liquidity = sum(size for price, size in orderbook['asks'] if price - mid <= threshold)

print(f"Liquidity within 1% of mid:")
print(f"  Bids: {bid_liquidity:.2f} SOL")
print(f"  Asks: {ask_liquidity:.2f} SOL")
```

### Example 4: Track Your Positions
```python
# Get your positions
positions = await drift.get_user_positions("YOUR_WALLET_ADDRESS")

# Calculate total PnL
total_pnl = sum(pos['unrealizedPnl'] for pos in positions)

print(f"Total Unrealized PnL: ${total_pnl:,.2f}")
print("\nPositions:")
for pos in positions:
    pnl_pct = (pos['unrealizedPnl'] / (pos['size'] * pos['entryPrice'])) * 100
    print(f"  {pos['market']}: {pos['side']} {pos['size']:.4f}")
    print(f"    PnL: ${pos['unrealizedPnl']:,.2f} ({pnl_pct:+.2f}%)")
```

---

## 🧪 Testing

Run the comprehensive test suite:

```bash
python test_drift_api_extended.py
```

This will test all API methods and display:
- All available perpetual markets
- Funding rates and market stats
- Orderbook data
- Oracle vs mark price comparison
- Time to next funding

---

## 📡 Data Source

All data is fetched directly from the Drift Protocol on-chain program using the **driftpy SDK**:

- **On-Chain Data**: Market accounts, funding rates, oracle prices, open interest
- **Real-Time**: Data is fetched directly from Solana RPC nodes
- **No HTTP API**: Does not rely on deprecated DLOB HTTP endpoints

**Note**: The previous DLOB HTTP API (`https://dlob.drift.trade`) has been deprecated. This implementation uses the official Drift SDK to fetch data directly from on-chain accounts, which is more reliable and doesn't require external API availability.

---

## 🎯 Supported Markets

Currently supports 20+ perpetual markets including:

- **Major**: SOL-PERP, BTC-PERP, ETH-PERP
- **L1s**: SUI-PERP, APT-PERP, INJ-PERP, TIA-PERP
- **DeFi**: JUP-PERP, PYTH-PERP, JTO-PERP, ONDO-PERP
- **Memes**: WIF-PERP, 1MBONK-PERP, 1MPEPE-PERP, DOGE-PERP
- **Others**: ARB-PERP, OP-PERP, POL-PERP, BNB-PERP, RNDR-PERP, HNT-PERP

---

## 🔧 Integration with Funding Engine

The Funding Engine UI automatically uses these methods to display:

- ✅ Real-time funding rates
- ✅ Market statistics (OI, volume, APR)
- ✅ Long/Short ratios
- ✅ Oracle vs mark price basis

All data updates automatically when you navigate to the Funding Engine page.

---

## 📝 Notes

- All API calls fetch data **directly from on-chain Drift program accounts** using the driftpy SDK
- No external HTTP API dependencies (the DLOB HTTP API has been deprecated)
- Requires an active Solana RPC connection
- Prices are automatically converted from Drift's precision (1e6 for quotes, 1e9 for base)
- Funding rates are converted from hourly to 8-hour and annual rates
- Volume data (24h) is not available on-chain and returns 0 (would require historical indexing)

---

## 🚀 Next Steps

To use this in your trading strategies:

1. **Monitor funding opportunities**: Use `get_all_perp_markets()` to scan for high funding rates
2. **Check liquidity**: Use `get_orderbook()` to ensure sufficient liquidity before trading
3. **Track positions**: Use `get_user_positions()` to monitor your open positions
4. **Calculate basis**: Compare `get_oracle_price()` vs `get_mark_price()` for arbitrage opportunities

---

**Last Updated**: January 16, 2026  
**API Version**: Drift Protocol v2 DLOB API
