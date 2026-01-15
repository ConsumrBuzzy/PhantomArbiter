# Project Direction & Status

**Project**: PhantomArbiter  
**Version**: 0.1.0  
**Status**: Active Development (Hybrid Architecture)  
**Last Updated**: 2026-01-14

---

## 🎯 Core Mission

**PhantomArbiter** is an autonomous Solana DeFi arbitrage and multi-strategy trading engine designed for institutional-grade performance with educational transparency.

### Primary Objectives

1. **Arbitrage Detection**: Identify and execute cross-DEX price discrepancies (Fast Lane)
2. **Multi-Strategy Trading**: RSI scalping, trend-following, and tactical execution (Mid Lane)
3. **Smart Money Tracking**: Shadow high-alpha wallets and detect early opportunities (Slow Lane)
4. **Performance Excellence**: Sub-millisecond hot paths via Rust acceleration
5. **Safety First**: Paper trading, audit trails, and risk management by default

---

## 📍 Current Status (Milestone 2)

### What's Working ✅

| Feature | Status | Notes |
|---------|--------|-------|
| **Hybrid Architecture** | ✅ Active | Python + Rust + TypeScript integrated |
| **Rust Extension** | ✅ Built | 21 modules compiled via Maturin |
| **TypeScript Bridges** | ✅ Active | Orca, Raydium, Meteora daemons operational |
| **Galaxy Dashboard** | ✅ Active | Three.js 3D visualization at `apps/galaxy/` |
| **Paper Trading** | ✅ Active | Realistic slippage simulation |
| **ExecutionBackend** | ✅ Active | Unified Paper/Live interface |
| **Capital Manager** | ✅ Active | Centralized PnL tracking |
| **SignalBus** | ✅ Active | Event-driven pub/sub |
| **Rich TUI** | ✅ Active | Terminal dashboard decoupled from core |

### What's Incubating 🚧

| Feature | Status | Blocker |
|---------|--------|---------|
| **gRPC DataFeed Service** | 🚧 Planned | `apps/datafeed/` defined but not wired |
| **gRPC Execution Service** | 🚧 Planned | `apps/execution/` defined but not wired |
| **Rust TA Engine** | 🚧 Phase 18 | RSI/EMA port to Rust pending |
| **PDA Cache** | 🚧 Phase 18 | O(1) lookup optimization pending |
| **Scraper Integration** | 🚧 Broken | Import errors in `src/scraper/` |

### Known Technical Debt ⚠️

1. **Legacy Code Confusion**: `src/legacy/` contains 74 files; unclear what's deprecated
2. **Phase Numbering Chaos**: Phases 4, 5, 6, 17, 18, 19 referenced without clear timeline
3. **Stale Paths**: Some documentation references non-existent file paths
4. **Test Coverage**: Integration tests exist but coverage metrics unknown

---

## 🗺️ Strategic Direction

### Short-Term Focus (Next 3 Months)

#### Priority 1: Stabilization
- [ ] **Fix Scraper Imports**: Resolve broken `src/scraper/` dependencies
- [ ] **Audit Legacy Code**: Clearly mark deprecated vs. archived files
- [ ] **Test Suite Health**: Run full test suite, document coverage
- [ ] **Documentation Freeze**: No new features until docs match reality

#### Priority 2: Performance Validation
- [ ] **Benchmark Rust FFI**: Measure actual speedups vs. Python baseline
- [ ] **Latency Profiling**: End-to-end signal-to-execution timing
- [ ] **Ghost Execution Test**: Validate JITO bundle construction
- [ ] **Soak Test**: 24h paper trading run with >99% uptime

#### Phase 2: Main.py Modernization (ADR-0004)
- [ ] **Add Deprecation Warnings**: Mark legacy code (`src/arbiter/`, `src/strategies/`)
- [ ] **Port cmd_scan**: Migrate to ArbEngine (1 hour)
- [ ] **Port cmd_arbiter**: Migrate to ArbEngine with callbacks (2 hours)
- [ ] **Port cmd_dashboard**: Align with LocalDashboardServer pattern (2 hours)
- [ ] **Archive Legacy**: Move deprecated code to `archive/deprecated/` (30 min)

**Timeline**: Weeks 2-6 (8 hours total, spread over 5 weeks)  
**Reference**: [ADR-0004](./docs/adr/0004-main-py-modernization.md), [Migration Guide](./docs/MIGRATION_GUIDE.md)

### Mid-Term Goals (3-6 Months)

#### Milestone 3: Rust Turbo
- [ ] Port Technical Analysis (RSI/EMA) to Rust (`src_rust/src/technical.rs`)
- [ ] Implement PDA cache for O(1) account lookups
- [ ] Port fee estimation logic to Rust
- [ ] Achieve <15ms total latency for hot path

#### UX Improvements
- [ ] Galaxy: Add real-time arbitrage cycle visualization
- [ ] TUI: Display Rust FFI performance metrics
- [ ] Telegram Bot: Implement remote paper trading controls

### Long-Term Vision (6-12 Months)

#### Milestone 4: Service Mesh
- [ ] Extract `apps/datafeed` as standalone gRPC service
- [ ] Extract `apps/execution` as standalone gRPC service
- [ ] Independent nonce manager for parallel transaction submission
- [ ] Kubernetes deployment manifests

#### Advanced Strategies
- [ ] ML-based signal classification (DeepScout expansion)
- [ ] Dynamic LP provisioning
- [ ] Cross-chain arbitrage (Wormhole integration)

---

## 🔀 Decision Points

### Question 1: Primary Strategy Focus?

**Options**:
- **A) Arbitrage-First**: Focus on Fast Lane (PhantomArbiter), optimize for <5ms cycles
- **B) Multi-Strategy**: Balance Arbitrage + Scalping (TacticalStrategy) equally
- **C) Adaptive**: Let profitability data guide strategy allocation

**Recommendation**: **B) Multi-Strategy** (current design supports both well)

### Question 2: UI Direction?

**Options**:
- **A) Galaxy Primary**: Invest in Three.js dashboard, deprecate Rich TUI
- **B) TUI Primary**: Terminal-first for VPS deployments, Galaxy optional
- **C) Dual Track**: Maintain both equally

**Recommendation**: **C) Dual Track** with clear separation (ADR-0003 already enforces this)

### Question 3: Legacy Code Cleanup?

**Options**:
- **A) Archive Immediately**: Move `src/legacy/` to `archive/` folder
- **B) Incremental Migration**: Port 1 module per week to current architecture
- **C) Keep As-Is**: Leave for historical reference

**Recommendation**: **B) Incremental Migration** with clear deprecation markers

### Question 4: Rust Expansion Pace?

**Options**:
- **A) Aggressive**: Port all hot paths to Rust (Phase 18 NOW)
- **B) Measured**: Port only proven bottlenecks after profiling
- **C) Pause**: Stabilize Python layer first

**Recommendation**: **B) Measured** (profile-guided optimization prevents premature abstraction)

---

## 📊 Success Metrics

### Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Signal Processing | ~5ms | <1ms |
| Arbitrage Cycle Detection | ~15ms | <5ms |
| End-to-End Execution | ~50ms | <20ms |
| Uptime (Paper Mode) | Unknown | >99.5% |

### Code Quality Targets

| Metric | Current | Target |
|--------|---------|--------|
| Test Coverage | Unknown | >80% |
| MyPy Compliance | Partial | >90% |
| Rust Clippy Warnings | Unknown | 0 |
| Documentation-Code Drift | High | <5% |

---

## 🧭 Development Principles

### PyPro Standards (Enforced)

1. **Type Hints**: PEP 484 on all public functions
2. **Logging**: Loguru only (no `print()`)
3. **CLI Output**: Rich library for human-readable displays
4. **SOLID**: Composition over inheritance, SRP compliance
5. **Rust for Speed**: Port only profiled bottlenecks

### Contribution Guidelines

- All PRs must update CHANGELOG.md
- New features require tests (>70% coverage)
- Architecture changes require ADR (Architecture Decision Record)
- Security-sensitive code requires review from 2+ maintainers

---

## 🚦 Next Immediate Actions

### For Maintainers

1. ✅ **[DONE]** Documentation overhaul (this commit)
2. **[NEXT]** Run full test suite: `pytest tests/ -v --cov=src`
3. **[NEXT]** Fix scraper imports: `python -m src.scraper.main` (debug)
4. **[NEXT]** Archive or migrate `src/legacy/arbiter/` (see ADR needed)
5. **[WEEK 2]** Execute ghost run: `python scripts/ghost_execute.py`

### For New Contributors

1. Read [DEVELOPMENT.md](./docs/DEVELOPMENT.md) - Setup guide
2. Review [ARCHITECTURE.md](./docs/ARCHITECTURE.md) - System design
3. Pick an issue tagged `good-first-issue`
4. Join discussion in [GitHub Discussions] (if enabled)

---

## 🔗 Reference Links

- **Documentation Hub**: [`docs/README.md`](./docs/README.md)
- **Architecture Deep-Dive**: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- **Roadmap**: [`docs/ROADMAP.md`](./docs/ROADMAP.md)
- **Component Inventory**: [`docs/COMPONENT_INVENTORY.md`](./docs/COMPONENT_INVENTORY.md)
- **Security Policy**: [`SECURITY.md`](./SECURITY.md)
- **Changelog**: [`CHANGELOG.md`](./CHANGELOG.md)

---

## 📝 Versioning Strategy

- **Major.Minor.Patch** (Semantic Versioning)
- **Current**: 0.1.0 (Pre-production)
- **0.x.x**: Breaking changes allowed, API unstable
- **1.0.0**: Production-ready milestone (requires external audit)

---

**Last Review**: 2026-01-14  
**Next Review**: 2026-02-14 (Monthly cadence)
