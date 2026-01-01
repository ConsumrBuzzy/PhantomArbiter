# src/engine - Trading Engines

Core trading engines responsible for trade execution and decision making.

## Key Modules

| Module | Responsibility |
|--------|----------------|
| `trading_core.py` | Main trading loop, signal execution, position management |
| `decision_engine.py` | Signal resolution, conflict handling |
| `landlord_core.py` | Yield/hedge engine (Drift/dYdX integration) |
| `trade_executor.py` | Order execution, slippage handling |
| `heartbeat_reporter.py` | System health monitoring |

## Architecture

```
TacticalStrategy
    ├── DecisionEngine (signal resolution)
    ├── TradeExecutor (order execution)
    └── CapitalManager (risk/sizing)
```

## Usage

```python
from src.strategies.tactical import TacticalStrategy
from src.engine.decision_engine import DecisionEngine
```
