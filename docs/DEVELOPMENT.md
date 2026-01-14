# Development Guide

> **PyPro-compliant development standards for PhantomArbiter contributors**

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.13+ | Core application |
| **Node.js** | 18+ | TypeScript bridges |
| **Rust** | 1.75+ | Rust extension (`phantom_core`) |
| **uv** | Latest | Deterministic dependency management |
| **Maturin** | 1.0+ | PyO3 binding builder |

---

## Environment Setup

### 1. Python Environment (using `uv`)

```powershell
# Install uv (if not already installed)
pip install uv

# Create virtual environment
uv venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install Python dependencies
uv pip install -r requirements.txt
```

### 2. Rust Extension Build

```powershell
# Install Rust toolchain
# https://rustup.rs/

# Build the Rust extension
cd src_rust
maturin develop --release
cd ..
```

This compiles `phantom_core` module and installs it into your Python environment.

### 3. TypeScript Bridges

```powershell
cd bridges
npm install
# Optionally build TypeScript files
npm run build  # If defined in package.json
cd ..
```

---

## Code Standards

### Python: PyPro Protocol

#### Type Hints (PEP 484)
All functions **must** include type annotations:

```python
from typing import Optional
from decimal import Decimal

def calculate_slippage(
    expected_price: Decimal,
    filled_price: Decimal,
    direction: str
) -> Decimal:
    """Calculate slippage percentage.
    
    Args:
        expected_price: Price quote from API
        filled_price: Actual execution price
        direction: "buy" or "sell"
        
    Returns:
        Slippage as decimal (0.02 = 2%)
    """
    ...
```

#### Logging: Loguru Only

**Never use `print()` for debugging.**

```python
from loguru import logger

logger.info("Price update received: {token}", token=token_symbol)
logger.warning("High slippage detected: {pct}%", pct=slippage * 100)
logger.error("RPC connection failed", exc_info=True)
```

Configure sinks in a `LoggingConfig` class:

```python
from loguru import logger
import sys

class LoggingConfig:
    @staticmethod
    def setup():
        logger.remove()  # Remove default handler
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"
        )
        logger.add(
            "logs/trading_{time}.log",
            rotation="1 day",
            retention="30 days",
            level="DEBUG"
        )
```

#### CLI Output: Rich

For human-readable terminal output (not logs):

```python
from rich.console import Console
from rich.table import Table

console = Console()

table = Table(title="Active Positions")
table.add_column("Token", style="cyan")
table.add_column("Size", style="magenta")
table.add_column("PnL", style="green")

console.print(table)
```

#### SOLID Principles

**Single Responsibility**:
```python
# ❌ BAD: God class doing everything
class TradingBot:
    def fetch_prices(self): ...
    def execute_trade(self): ...
    def send_telegram(self): ...

# ✅ GOOD: Separated concerns
class PriceFeedManager: ...
class TradeExecutor: ...
class TelegramNotifier: ...
```

**Composition over Inheritance**:
```python
# ✅ Use dependency injection
class TacticalStrategy:
    def __init__(
        self,
        executor: ExecutionBackend,
        capital_mgr: CapitalManager,
        logger: Logger
    ):
        self._executor = executor
        self._capital = capital_mgr
        self._log = logger
```

---

## Rust: Performance-Critical Paths

### When to Use Rust

Port to Rust when:
- Function is called **>1000 times/second**
- GIL contention is measurable
- Pure computation (no I/O)

Example hot paths:
- `cycle_finder.rs`: Bellman-Ford loop detection
- `scorer.rs`: Signal scoring logic
- `amm_math.rs`: Swap calculations

### PyO3 Integration

Expose Rust functions via PyO3:

```rust
use pyo3::prelude::*;

#[pyfunction]
fn find_arbitrage_cycles(
    graph: Vec<(String, String, f64)>,
    threshold: f64
) -> PyResult<Vec<Vec<String>>> {
    // Rust implementation
    Ok(cycles)
}

#[pymodule]
fn phantom_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_arbitrage_cycles, m)?)?;
    Ok(())
}
```

Call from Python:

```python
import phantom_core

cycles = phantom_core.find_arbitrage_cycles(graph_data, 0.005)
```

### GIL Release Pattern

For long-running Rust functions, release the GIL:

```rust
use pyo3::prelude::*;

#[pyfunction]
fn heavy_computation(data: Vec<f64>) -> PyResult<f64> {
    Python::with_gil(|py| {
        py.allow_threads(|| {
            // Expensive computation here (GIL released)
            expensive_rust_function(data)
        })
    })
}
```

---

## Testing

### Unit Tests (Pytest)

Run tests:
```powershell
pytest tests/unit/ -v
```

Example test structure:
```python
import pytest
from src.shared.system.capital_manager import CapitalManager

@pytest.fixture
def capital_manager():
    return CapitalManager(initial_balance=1000.0)

def test_deduct_balance(capital_manager):
    capital_manager.deduct(100.0, "Test spend")
    assert capital_manager.get_balance() == 900.0
```

### Integration Tests

Mock external dependencies:
```python
from unittest.mock import Mock, patch

@patch("src.shared.execution.swapper.JupiterSwapper.execute_swap")
def test_trade_executor(mock_swap):
    mock_swap.return_value = {"signature": "abc123"}
    # Test logic
```

### Rust Tests

```powershell
cd src_rust
cargo test
```

---

## Debugging

### Python
Use Loguru with DEBUG level:
```python
logger.add("debug.log", level="DEBUG")
```

### Rust
Add `dbg!()` macros:
```rust
let result = calculate_profit(&path);
dbg!(&result);
```

Check Rust logs:
```powershell
$env:RUST_LOG="debug"
python main.py pulse
```

---

## Build & Release

### Local Development Build

```powershell
# Rust extension (debug mode, faster compilation)
cd src_rust
maturin develop
cd ..

# Run application
python main.py pulse
```

### Production Build

```powershell
# Rust extension (optimized)
cd src_rust
maturin build --release
pip install target/wheels/phantom_core-*.whl
cd ..
```

### Cross-Platform Wheels (Maturin)

```powershell
# Build for multiple platforms
maturin build --release --target x86_64-pc-windows-msvc
maturin build --release --target x86_64-unknown-linux-gnu
```

---

## Performance Profiling

### Python (cProfile)
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()
# Code to profile
profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats('cumtime').print_stats(20)
```

### Rust (flamegraph)
```powershell
cargo install flamegraph
cargo flamegraph --bin phantom_core
```

---

## Contributing Checklist

Before submitting PRs:

- [ ] Type hints on all public functions
- [ ] Loguru for logging (no `print()`)
- [ ] Rich for CLI output
- [ ] Unit tests for new features (>80% coverage preferred)
- [ ] Docstrings (Google style)
- [ ] Rust code passes `cargo clippy`
- [ ] Python passes MyPy checks (if enabled)
- [ ] Updated CHANGELOG.md

---

## Resources

- [Loguru Documentation](https://loguru.readthedocs.io/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [PyO3 Guide](https://pyo3.rs/)
- [Maturin](https://www.maturin.rs/)
- [uv Package Manager](https://github.com/astral-sh/uv)
