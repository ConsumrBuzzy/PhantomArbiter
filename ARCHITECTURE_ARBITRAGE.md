# Arbiter Architecture & Goals

## 🎯 Current State (Hybrid V3.0)

PhantomArbiter is currently in a **Transitioning Hybrid State**, moving from a monolithic Python engine to a Layered Micro-Services architecture.

### Active Core
- **Director (`src/director.py`)**: The central brain coordinating all components.
- **Data Broker (`src/core/data_broker.py`)**: centralized data nervous system.
- **Arbiter Engine (`src/arbiter/`)**: High-performance triangular/spatial arbitrage.
- **Node.js Bridges (`bridges/`)**: Sub-process IO layer for Meteora/Raydium/Orca protocol interaction.

### Active Services
- **Galaxy (`apps/galaxy/`)**: Standalone FastAPI/Three.js visualization service running as a subprocess.

### Incubating (Future)
- **DataFeed Service (`apps/datafeed/`)**: gRPC-based market data ingress (In Development).
- **Execution Service (`apps/execution/`)**: Dedicated trade execution container (In Development).

---

## 🚀 Roadmap

### Phase 1: Separation (Current)
- [x] Extract visualization to `apps/galaxy`.
- [x] Implement Bridges (Python <-> Node.js) for reliability.
- [ ] Move Data Ingestion to `apps/datafeed`.

### Phase 2: Independence
- [ ] `apps/execution` handles all on-chain transactions.
- [ ] Core Director becomes a lightweight decision engine only.
- [ ] gRPC replaces internal function calls between layers.

### Phase 3: Scale
- [ ] Deploy services to separate containers.
- [ ] Horizontal scaling of scanners.

---

## 📁 High-Level Structure

```
.
├── apps/               # Standalone Micro-Services
│   ├── galaxy/         # [ACTIVE] Visualization & Dashboard
│   ├── datafeed/       # [INCUBATING] Market Data Ingestion
│   └── execution/      # [INCUBATING] Trade Execution
├── bridges/            # [ACTIVE] Node.js Protocol Connectors
├── config/             # Global Settings
├── docs/               # Architecture & Guides
├── src/                # [ACTIVE] Core Monolithic Engine
│   ├── arbiter/        # Trading Logic
│   ├── core/           # System Kernels (Broker, Monitor)
│   ├── shared/         # Common Utilities & Types
│   ├── director.py     # Main Entry Point
│   └── main.py         # CLI Wrapper
└── transactions/       # Transaction Logs
```

See [docs/architecture_overview.md](docs/architecture_overview.md) for the detailed technical breakdown.
