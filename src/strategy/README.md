# src/strategy - Trading Strategies

Trading strategy implementations and portfolio management.

## Available Strategies

| Strategy | File | Description |
|----------|------|-------------|
| Base | `base_strategy.py` | Abstract base class |
| Keltner | `keltner_logic.py` | Keltner channel breakouts |
| VWAP | `vwap_logic.py` | VWAP mean reversion |
| Longtail | `longtail_logic.py` | Scout/discovery trades |
| Ensemble | `ensemble.py` | Multi-strategy voting |
| Landlord | `landlord_strategy.py` | Yield farming strategy |

## Supporting Modules

| Module | Responsibility |
|--------|----------------|
| `portfolio.py` | Position sizing, portfolio state |
| `risk.py` | Risk calculations |
| `signals.py` | Signal generation |
| `watcher.py` | Per-asset price monitoring |
| `metrics.py` | Strategy performance metrics |

## Usage

```python
from src.strategy.keltner_logic import KeltnerLogic
from src.strategy.ensemble import EnsembleStrategy
```
