# Phantom Data Feed Engine

Front-of-line market data ingestion for PhantomArbiter.

## Quick Start

```powershell
cd apps/datafeed
uv sync
uv run datafeed
```

Server starts on `localhost:9000` (gRPC).

## Architecture

Data Feed is the **first engine** in the pipeline. It:
1. Connects to WSS (Helius, Raydium, etc.)
2. Fetches prices from Jupiter/DexScreener
3. Streams market data to subscribers via gRPC

```
[WSS/RPC Sources] → [Data Feed :9000] → [Director/Execution]
```

## gRPC API

| Method | Description |
|--------|-------------|
| `StreamPrices` | Real-time price stream |
| `GetSnapshot` | Current market state |
| `Subscribe` | Topic-based subscription |

## Development

```powershell
# Generate Python from proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. market_data.proto

# Run server
uv run python -m datafeed.server
```
