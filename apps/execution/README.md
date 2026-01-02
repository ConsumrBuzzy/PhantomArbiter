# Phantom Execution Engine

Second-layer trade execution for PhantomArbiter.

## Quick Start

```powershell
cd apps/execution
uv sync
uv run execution
```

Server starts on `localhost:9001` (gRPC).

## Architecture

Execution Engine is the **second layer** in the pipeline. It:
1. Receives trade signals from Director
2. Validates against position limits
3. Executes via Paper or Live backend

```
[Director SignalBus] → [Execution :9001] → [Jupiter/JITO]
```

## gRPC API

| Method | Description |
|--------|-------------|
| `SubmitSignal` | Submit trade signal |
| `GetPositions` | Current positions |
| `StreamExecutions` | Execution confirmations |

## Backends

### Paper Trading
```powershell
EXECUTION_MODE=paper uv run execution
```

### Live Trading
```powershell
EXECUTION_MODE=live uv run execution
```

## Development

```powershell
# Generate Python from proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. orders.proto

# Run server
uv run python -m execution.server
```
