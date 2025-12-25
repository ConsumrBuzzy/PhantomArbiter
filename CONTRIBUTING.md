# Contributing to PhantomArbiter

Thank you for your interest in contributing to PhantomArbiter! This document provides guidelines and information for contributors.

## 📋 Code of Conduct

Please be respectful and constructive in all interactions. We're building something cool together.

## 🚀 Getting Started

1. **Fork the repository** and clone your fork
2. **Create a branch** for your feature or fix: `git checkout -b feature/your-feature-name`
3. **Install dependencies**: `pip install -r requirements.txt`
4. **Make your changes** following our coding standards
5. **Test your changes** thoroughly
6. **Submit a pull request**

## 📁 Project Structure

```
src/
├── core/           # Core utilities - careful modifications only
├── shared/         # Shared modules - most contributions go here
│   ├── execution/  # Trade execution logic
│   ├── feeds/      # Price feed integrations
│   └── system/     # System infrastructure
├── scraper/        # Token discovery
└── liquidity/      # LP management
```

## 🎨 Coding Standards

### Python (PEP 8 + Type Hints)

```python
from typing import Optional
from pydantic import BaseModel

class TradeSignal(BaseModel):
    """Represents a trading signal with full type annotations."""
    
    symbol: str
    action: str  # "BUY" | "SELL" | "HOLD"
    confidence: float
    timestamp: Optional[float] = None
    
    def is_actionable(self) -> bool:
        """Check if signal meets minimum confidence threshold."""
        return self.confidence >= 0.65 and self.action != "HOLD"
```

### Key Principles
- **Type hints** on all function signatures
- **Docstrings** for public functions and classes
- **Async-first** for I/O operations
- **SOLID principles** - single responsibility, dependency injection

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/unit/test_trading_logic.py

# Run with coverage
pytest --cov=src tests/
```

## 🔒 Security

- **Never commit secrets** - use `.env` files
- **Review `.gitignore`** before committing
- **Sanitize logs** - no private keys or sensitive data

## 📝 Pull Request Process

1. Update documentation if needed
2. Add tests for new functionality
3. Ensure all tests pass
4. Update the changelog if applicable
5. Request review from maintainers

## 💡 Feature Requests & Bug Reports

Please use GitHub Issues with appropriate labels:
- `bug` - Something isn't working
- `enhancement` - New feature request
- `documentation` - Documentation improvements
- `question` - Questions about usage

---

Thank you for contributing! 🙏
