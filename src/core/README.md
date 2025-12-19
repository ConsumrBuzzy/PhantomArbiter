# src/core - Infrastructure Layer

Core infrastructure components for data acquisition, caching, and capital management.

## Key Modules

| Module | Responsibility |
|--------|----------------|
| `data_broker.py` | Main broker loop, price fetching, WebSocket management |
| `capital_manager.py` | Risk management, paper wallet simulation, capital allocation |
| `data.py` | DataFeed class, RSI/ATR calculations, price history |
| `shared_cache.py` | Inter-process price cache (JSON-based) |
| `validator.py` | Token safety validation (rug check) |
| `market_aggregator.py` | Unified market status for Telegram |

## Usage

```python
from src.core.data_broker import DataBroker
from src.core.capital_manager import get_capital_manager

broker = DataBroker()
cap_man = get_capital_manager()
```
