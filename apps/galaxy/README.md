# Phantom Galaxy

Standalone 3D Galaxy Visualization Dashboard for PhantomArbiter.

## Quick Start

```powershell
cd apps/galaxy
uv sync
uv run galaxy
```

Open http://localhost:8001/dashboard.html

## Architecture

Galaxy runs as an independent service that receives events from the Core Engine via HTTP/WebSocket.

```
Core Engine :8000          Galaxy App :8001
    │                           │
    │  POST /api/v1/events      │
    │ ─────────────────────────►│
    │                           │
    │                     ┌─────┴─────┐
    │                     │ Transform │
    │                     │ Broadcast │
    │                     └─────┬─────┘
    │                           │
    │                    ┌──────┴──────┐
    │                    │   Browsers  │
    │                    │  (Three.js) │
    │                    └─────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/events` | POST | Receive event batch from Core |
| `/api/v1/state` | GET | Get current Galaxy state |
| `/api/v1/health` | GET | Health check |
| `/ws/v1/stream` | WS | Real-time event stream to browsers |

## Development

```powershell
uv run uvicorn galaxy.server:app --reload --port 8001
```
