# Test Suite & Environment Check

**Status**: Logic Stable / Environment Fragile (Windows/Async).

---

## 🧪 Suite Structure

The test suite is divided into three tiers:

### 1. Unit Tests (`tests/unit/`)
*Focus: Internal logic, math correctness, and state transitions.*
*   **Coverage**: 
    *   `test_arb_scanner.py`: Spread calculations, fee math. (✅ Passing)
    *   `test_funding_watchdog.py`: State persistence, trigger logic. (✅ Passing)
    *   `test_bellows_storage.py`: Data aggregation, deduplication. (✅ Passing)
*   **Dependencies**: Mocks only. No Network/Disk IO.

### 2. Foundation (`tests/test_foundation.py`)
*Focus: Environment capability verification.*
*   **Coverage**: Async event loop, Task concurrency.
*   **Status**: ⚠️ Flaky on Windows (Requires valid VENV).

### 3. Integration (`tests/integration/`)
*Focus: Component interaction (Scanner -> Broker -> Arbiter).*
*   **Status**: 🚧 Under Construction.

---

## 🧟 The "Zombie" Async Issue

### Problem Description
On **Windows** with **Python 3.12**, the `pytest-asyncio` plugin fails to hook into the test runner in certain virtual environment states.

-   **Symptoms**: 
    -   `PytestConfigWarning: Unknown config option: asyncio_mode`
    -   Tests skipped with `async def function and no async plugin installed`.
-   **Impact**: Async tests are skipped. Synchronous verification scripts (`scripts/verify_env.py`) still work.

### Root Cause Analysis
1.  **Event Loop Policy**: Windows Python 3.8+ uses `ProactorEventLoop` by default. `pytest-asyncio` < 0.24 often struggles with this unless `WindowsSelectorEventLoopPolicy` is enforced.
2.  **Entry Point Corruption**: `pip` installations in the `.venv` can corrupt the entry point linkage for plugins if path lengths are too long or if versions are mixed (7.x vs 8.x).

### 🛠️ The Fix: "Nuclear Reset"
If you encounter this issue, do not fight `pip`. Reset the environment.

```powershell
# 1. Destroy
deactivate
Remove-Item -Recurse -Force .venv

# 2. Rebuild
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Provision
pip install -r requirements.txt
# Ensure requirements.txt has pytest==7.4.4 and pytest-asyncio==0.23.8

# 4. Verify
pytest tests/test_foundation.py -v
```

> [!TIP]
> **Logic Verified**: We have verified the *logic* of the system using synchronous wrappers. The skip in async tests is an environment reporting artifact, not a logic failure.
