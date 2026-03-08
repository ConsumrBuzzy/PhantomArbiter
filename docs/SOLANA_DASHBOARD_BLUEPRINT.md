# SOLANA DASHBOARD BLUEPRINT (Phase 20)

This blueprint maps the technical integration of PhantomArbiter's portable scripts into the RFD IT Services web ecosystem.

## 📡 Data Interfaces (JSON Schema)

### Ticker Snapshot (`ticker.json`)
The `live_ticker_mvp.py` script outputs this file to the root.
```json
{
    "symbol": "SOL/USD",
    "price": 84.42,
    "change_24h": -2.15,
    "sources": {
        "jupiter": 84.41,
        "coinbase": 84.43
    },
    "status": "linked",
    "timestamp": "2026-03-08T...Z",
    "vitals": {
        "volume_24h": 3750000000.0,
        "market_cap": 47250000000.0
    }
}
```

## 🎨 Brand Identity (CSS Mappings)

To maintain the "Headless Systems Architect" aesthetic, use these variables from the RFD IT repo:

| Token | CSS Variable | Usage |
|-------|--------------|-------|
| **Stability** | `--neon-blue` | Header Text, Linked Status |
| **Volatility** | `--neon-red` | Downwards Trends, Error States |
| **Growth** | `--neon-green` | Upwards Trends, Success States |
| **Warning** | `--neon-gold` | Arb Opportunities, Syncing |
| **Secondary** | `--text-dim` | Timestamps, Labels |

## 🧩 Component Mapping (Cards)

### Card 1: Exchange Matrix (CEX)
- **Logic**: Reads `sources.coinbase` from `ticker.json`.
- **UI**: Shows side-by-side comparison with Binance (Mockable) and Jupiter.

### Card 2: DEX Spreads (On-Chain)
- **Logic**: Derived from `market_feeds_standalone.py` output.
- **UI**: High-speed list of Raydium vs Orca prices with spread percentage.

### Card 3: 24h Network Vitals
- **Logic**: Reads `vitals` object from `ticker.json`.
- **UI**: Horizontal bar showing Volume and Market Cap intensity.

## 🚀 Porting Implementation (Next Steps)
1. **Hugo Partial**: Create `layouts/partials/components/solana-ticker.html`.
2. **Fetch Hook**: Implement `static/js/ticker-fetch.js` to poll `ticker.json` every 1000ms.
3. **Reactive Style**: Use JS to swap `--neon-green` and `--neon-red` based on the `change_24h` value.
