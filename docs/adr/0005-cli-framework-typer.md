# ADR-0005: CLI Framework Migration (Argparse → Typer)

**Status**: Proposed  
**Date**: 2026-01-14  
**Context**: "Main.py Complexity & CLI Framework Modernization"

---

## Context

PhantomArbiter's `main.py` has grown to **907 lines** with **13 subcommands**, all managed via Python's built-in `argparse`. As the CLI complexity increases, several pain points have emerged:

### Current State (Argparse)

**main.py Structure**:
```python
# 907 lines total
# ~266 lines: Argument parser definitions
# ~641 lines: Command handler functions
# 13 subcommands: arbiter, scan, discover, watch, scout, monitor, clean,
#                 web, galaxy, dashboard, live, pulse, graduation
```

**Issues**:
1. **Boilerplate Overhead**: Each subcommand requires ~15-20 lines of setup
2. **No Type Safety**: Arguments parsed as strings, manual conversion needed
3. **Manual Help Generation**: Docstrings not used for `--help` text
4. **Poor Developer Experience**: Repetitive code for similar patterns
5. **Hard to Test**: Argparse namespace objects difficult to mock

### Project Context

**PhantomArbiter already uses Rich extensively**:
- 36+ files import `from rich` (logging, TUI, panels, tables)
- PyPro protocol mandates Rich for CLI output
- `src/core/logger.py` uses `RichHandler`

**PyPro Standards Compliance**:
- ✅ Type hints required (PEP 484)
- ✅ Rich for CLI output
- ✅ Loguru for logging
- ⚠️ Argparse not idiomatic with type hints

---

## Problem Statement

**As main.py grows, we face**:
1. **Maintainability**: 266 lines just for arg parsing is unwieldy
2. **Onboarding**: New contributors must learn argparse quirks
3. **Type Safety**: No automatic validation of argument types
4. **Documentation Drift**: Help text separate from function docs
5. **Testing Complexity**: Mocking argparse.Namespace is verbose

**Example of Current Pain**:

```python
# Current (Argparse) - 15 lines for simple command
web_parser = subparsers.add_parser(
    "web", help="Component-Based Web UI (Modern Dashboard - Recommended)"
)
web_parser.add_argument(
    "--live", action="store_true", help="Enable LIVE trading"
)
web_parser.add_argument(
    "--no-browser", action="store_true", help="Don't auto-open browser"
)
web_parser.add_argument(
    "--port", type=int, default=8000, help="Frontend port (default: 8000)"
)

# Handler must manually extract args
async def cmd_web(args: argparse.Namespace) -> None:
    live_mode = args.live  # No type checking
    port = args.port       # Could be wrong type
```

---

## Decision

**Migrate main.py from Argparse to Typer + Rich.**

### Why Typer?

**1. Perfect Fit for PhantomArbiter**:
- ✅ **Already using Rich**: Typer integrates seamlessly
- ✅ **Type hints enforced**: PyPro compliance automatic
- ✅ **Async support**: Built-in via `typer.Typer(async=True)` or manual wrapping
- ✅ **Modern Python**: Leverages Python 3.12 features

**2. Developer Experience**:
```python
# Future (Typer) - 5 lines for same command
@app.command()
def web(
    live: bool = False,
    no_browser: bool = False,
    port: int = 8000,
) -> None:
    """Component-Based Web UI (Modern Dashboard - Recommended)."""
    # Automatic type validation, help generation
```

**3. Feature Comparison**:

| Feature | Argparse | Click | Typer |
|---------|----------|-------|-------|
| **Type Hints** | ❌ Manual | ❌ Decorators | ✅ **Native** |
| **Auto Help** | Partial | Yes | ✅ **From docstrings** |
| **Rich Integration** | Manual | Plugin | ✅ **Built-in** |
| **Async Support** | Manual | Manual | ✅ **Via wrapper** |
| **Code Reduction** | Baseline | 30% less | **60% less** |
| **Type Safety** | ❌ None | ⚠️ Runtime | ✅ **Static analysis** |

---

## Alternatives Considered

### Alternative 1: Keep Argparse

**Pros**:
- No migration cost
- Standard library (no dependency)
- Team already familiar

**Cons**:
- ❌ Doesn't scale (907 lines → 1200+ as commands grow)
- ❌ No type safety
- ❌ Violates PyPro idioms (not using type hints effectively)
- ❌ Poor DX (developer experience)

**Verdict**: **Rejected** - Technical debt will compound

---

### Alternative 2: Click

**Pros**:
- Mature, battle-tested (Flask, etc.)
- Highly composable
- Large ecosystem

**Cons**:
- ❌ Decorator-based (less Pythonic than type hints)
- ❌ Doesn't leverage PEP 484
- ❌ Requires `click-rich` plugin for Rich integration
- ❌ More boilerplate than Typer

**Verdict**: **Not Recommended** - Typer is Click + type hints

---

### Alternative 3: Python Fire

**Pros**:
- Zero boilerplate
- Auto-generates CLI from any object

**Cons**:
- ❌ Too "magical" (poor control)
- ❌ Help text quality poor
- ❌ Not suitable for production CLIs
- ❌ Hard to customize

**Verdict**: **Rejected** - Great for internal scripts, not production

---

## Implementation Strategy

### Phase 3A: Proof of Concept (Week 4)

**Estimated Time**: 2 hours

**Goal**: Migrate 2-3 simple commands to validate approach

**Commands to Port**:
1. `scan` (simplest - one-shot scan)
2. `web` (delegates to run_dashboard.py)
3. `clean` (panic button)

**Setup**:
```python
# cli/main.py (new file)
import typer
from rich.console import Console

app = typer.Typer(
    name="phantom",
    help="PhantomArbiter - Solana DeFi Arbitrage & Trading Engine",
    rich_markup_mode="rich",
)
console = Console()

# Subcommands
@app.command()
def web(
    live: bool = typer.Option(False, "--live", help="Enable LIVE trading"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
    port: int = typer.Option(8000, "--port", help="Frontend port"),
):
    """Component-Based Web UI (Modern Dashboard - Recommended)."""
    # Delegate to existing handler
    import asyncio
    from handlers.web import run_web
    asyncio.run(run_web(live, no_browser, port))
```

---

### Phase 3B: Full Migration (Week 5)

**Estimated Time**: 6 hours

**Structure**:
```
cli/
├── __init__.py
├── main.py              # Typer app + routing
├── handlers/
│   ├── arbiter.py       # cmd_arbiter logic
│   ├── web.py           # cmd_web logic
│   ├── galaxy.py        # cmd_galaxy logic
│   └── ...
└── shared/
    ├── validators.py    # Custom Typer validators
    └── formatters.py    # Rich output helpers
```

**Migration Plan**:

| Command | Complexity | Time | Priority |
|---------|------------|------|----------|
| `web` | Low | 15 min | High |
| `galaxy` | Low | 15 min | High |
| `scan` | Low | 15 min | High |
| `clean` | Low | 15 min | Medium |
| `discover` | Medium | 30 min | Medium |
| `scout` | Medium | 30 min | Medium |
| `watch` | Medium | 30 min | Low |
| `arbiter` | High | 60 min | High |
| `monitor` | Medium | 30 min | Low |
| `pulse` | Low (redirect) | 10 min | Low |
| `graduation` | Medium | 30 min | Low |
| `dashboard` | Low (redirect) | 10 min | High |
| `live` | Low (shortcut) | 10 min | High |

**Total**: ~6 hours

---

### Phase 3C: Testing & Validation (Week 6)

**Estimated Time**: 2 hours

**Tests**:
```python
# tests/cli/test_web_command.py
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()

def test_web_command():
    result = runner.invoke(app, ["web", "--no-browser"])
    assert result.exit_code == 0
    assert "Launching Component-Based Web UI" in result.output

def test_web_live_mode():
    result = runner.invoke(app, ["web", "--live"])
    # Should prompt for confirmation
    assert "I UNDERSTAND" in result.output
```

---

## Code Examples

### Before (Argparse - 24 lines)

```python
# main.py (current)
web_parser = subparsers.add_parser(
    "web", help="Component-Based Web UI (Modern Dashboard - Recommended)"
)
web_parser.add_argument(
    "--live", action="store_true", help="Enable LIVE trading"
)
web_parser.add_argument(
    "--no-browser", action="store_true", help="Don't auto-open browser"
)
web_parser.add_argument(
    "--port", type=int, default=8000, help="Frontend port (default: 8000)"
)

async def cmd_web(args: argparse.Namespace) -> None:
    import sys
    print("🌐 Launching Component-Based Web UI...")
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_dashboard", "run_dashboard.py")
    if spec and spec.loader:
        dashboard_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dashboard_module)
        await dashboard_module.main()
```

### After (Typer - 11 lines)

```python
# cli/main.py (future)
@app.command()
def web(
    live: bool = typer.Option(False, help="Enable LIVE trading"),
    no_browser: bool = typer.Option(False, help="Don't open browser"),
    port: int = typer.Option(8000, help="Frontend port"),
):
    """Component-Based Web UI (Modern Dashboard - Recommended)."""
    console.print("🌐 Launching Component-Based Web UI...")
    asyncio.run(run_web_handler(live, no_browser, port))
```

**Code Reduction**: 24 lines → 11 lines (**54% less**)

---

## Consequences

### Positive

#### 1. Code Quality
- **60% less boilerplate**: 907 lines → ~400 lines
- **Type safety**: MyPy can validate CLI arguments
- **DRY principle**: Docstrings = help text (single source of truth)

#### 2. Developer Experience
- **Faster iteration**: Add new command in ~5 lines
- **Better autocomplete**: IDEs understand type hints
- **Easier testing**: `CliRunner` simpler than mocking Namespace

#### 3. User Experience
- **Better help text**: Auto-generated from docstrings
- **Rich formatting**: Colors, tables in `--help` output
- **Shell completion**: Typer can generate bash/zsh completions

#### 4. Maintainability
- **Clear structure**: Commands in `cli/handlers/`
- **Isolated logic**: Each handler is a clean function
- **Easy refactoring**: Change signatures, help text updates auto

### Negative

#### 1. New Dependency
- **Typer package required** (`pip install typer[all]`)
- **Deployment impact**: Adds ~2MB to package size
- **Risk**: Dependency on external package

**Mitigation**:
- Typer is mature, actively maintained (same author as FastAPI)
- Already dependent on Rich (Typer uses Rich internally)
- Package size negligible for our use case

#### 2. Migration Effort
- **10 hours total** (PoC + migration + testing)
- **Testing burden**: Ensure all commands work identically
- **Documentation updates**: Update README, guides

**Mitigation**:
- Can be done incrementally (command by command)
- Keep old `main.py` as `main_legacy.py` during transition
- Parallel testing ensures no regressions

#### 3. Learning Curve
- **Team must learn Typer** (new framework)
- **Different patterns** than argparse

**Mitigation**:
- Typer is simpler than argparse (less to learn)
- Create migration guide with examples
- Typer docs are excellent

---

## Migration Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Breaking existing scripts** | Medium | High | Keep `main.py` redirect for 1 release |
| **Async compatibility issues** | Low | Medium | Typer supports async via wrapper |
| **Help text regression** | Low | Low | Side-by-side comparison during migration |
| **Performance degradation** | Very Low | Low | Typer is fast (built on Click) |
| **Team resistance** | Low | Medium | Show PoC benefits clearly |

---

## Success Criteria

**Migration is successful when**:
1. ✅ All 13 commands work identically (behavioral parity)
2. ✅ Help text quality equal or better
3. ✅ Code reduced by >50% (907 → <450 lines)
4. ✅ Type hints cover 100% of CLI arguments
5. ✅ Tests pass for all commands
6. ✅ No user-facing breaking changes

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **3A: PoC** | Week 4 (2 hours) | web, scan, clean commands migrated |
| **3B: Full Migration** | Week 5 (6 hours) | All commands in Typer |
| **3C: Testing** | Week 6 (2 hours) | Test suite, validation |
| **3D: Documentation** | Week 6 (1 hour) | Updated README, migration guide |

**Total**: 11 hours over 3 weeks

---

## Rollback Plan

If Typer migration fails:

1. **Keep `main_legacy.py`** (rename current main.py)
2. **Symlink**: Point `main.py` back to `main_legacy.py`
3. **Zero user impact**: Old CLI still works

---

## Recommendation

**✅ PROCEED with Typer migration** for the following reasons:

1. **Perfect Fit**: Already using Rich, type hints (PyPro standard)
2. **Significant ROI**: 60% code reduction, better DX
3. **Low Risk**: Can be done incrementally, easy rollback
4. **Future-Proof**: Aligns with modern Python best practices
5. **Team Velocity**: Faster to add new commands going forward

**Timeline**: Start PoC in Week 4 (alongside Phase 2 modernization)

---

## Decision

**Status**: Awaiting user approval

**If approved, next steps**:
1. Install Typer: `pip install "typer[all]"`
2. Create `cli/` directory structure
3. Migrate `web`, `scan`, `clean` as PoC (Week 4, 2 hours)
4. Review PoC with user
5. Proceed with full migration if PoC successful

---

## References

- **Typer Documentation**: https://typer.tiangolo.com/
- **PyPro Protocol**: `docs/DEVELOPMENT.md` (type hints requirement)
- **ADR-0004**: Main.py Modernization
- **Current main.py**: 907 lines, 13 subcommands

---

**Proposed**: 2026-01-14  
**Decision**: Pending user review
