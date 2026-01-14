# ADR-0002: Rust Acceleration Layer

**Status**: Accepted  
**Date**: 2025-12-15  
**Context**: "Performance Bottlenecks in Pure Python"

---

## Context

PhantomArbiter operates in a latency-sensitive environment where microseconds matter:

1. **Signal Processing**: Receiving WebSocket price updates from multiple RPCs requires sub-millisecond deduplication
2. **Graph Algorithms**: Bellman-Ford cycle detection for arbitrage runs on every price update
3. **GIL Contention**: Python's Global Interpreter Lock limits true parallelism for CPU-bound tasks
4. **Memory Safety**: Incorrect pointer arithmetic or buffer overflows in critical paths could corrupt trading state

### Measured Bottlenecks (Python Baseline)

| Operation | Python Time | Target |
|-----------|-------------|--------|
| WSS deduplication (1000 msgs) | ~15ms | <1ms |
| Bellman-Ford (100 nodes) | ~45ms | <5ms |
| Signal scoring (per tick) | ~2ms | <0.5ms |
| Multi-hop path search | ~80ms | <10ms |

---

## Decision

We adopt **Rust via PyO3** for performance-critical hot paths:

### What Goes to Rust

1. **WSS Aggregator** (`wss_aggregator.rs`): Multi-RPC message deduplication
2. **CycleFinder** (`cycle_finder.rs`): Bellman-Ford negative cycle detection
3. **SignalScorer** (`scorer.rs`): Go/No-Go decision logic
4. **Multiverse** (`multiverse.rs`): Multi-hop path enumeration
5. **AMM Math** (`amm_math.rs`): Constant product/CLMM calculations
6. **Instruction Builder** (`instruction_builder.rs`): Solana transaction construction

### What Stays in Python

1. **Business Logic**: Strategy orchestration, risk management
2. **I/O Coordination**: RPC failover, WebSocket lifecycle
3. **Database**: SQLite interactions, trade journaling
4. **UI**: Rich TUI and Galaxy dashboard communication

### Build Tooling

- **PyO3**: Zero-copy FFI between Python and Rust
- **Maturin**: Cross-platform wheel builder
- **Release Profile**: `opt-level = 3`, `lto = "fat"` for maximum performance

---

## Consequences

### Positive

#### 1. Performance Gains
- **WSS Aggregator**: 15ms → 0.8ms (18.75x faster)
- **CycleFinder**: 45ms → 3ms (15x faster)
- **Memory Safety**: Rust's ownership model prevents race conditions

#### 2. GIL-Free Execution
```rust
#[pyfunction]
fn find_cycles(py: Python, graph: Vec<Edge>) -> PyResult<Vec<Cycle>> {
    py.allow_threads(|| {
        // Runs without holding GIL
        bellman_ford_native(graph)
    })
}
```

Python async code can continue while Rust crunches numbers.

#### 3. Type Safety
Rust's compile-time checks prevent entire classes of bugs:
- No null pointer dereferences
- No buffer overflows
- No data races (enforced by borrow checker)

### Negative

#### 1. Build Complexity
- Requires Rust toolchain installation
- Cross-compilation for Windows/Linux/macOS is non-trivial
- CI/CD must build wheels for multiple platforms

#### 2. Debugging Overhead
- Stack traces cross FFI boundary
- Python debuggers can't step into Rust code
- Need separate Rust debugging tools (`rust-lldb`, `gdb`)

#### 3. Contributor Barrier
- New contributors must learn Rust
- Code review requires bilingual expertise
- Smaller pool of potential maintainers

#### 4. Unsafe Blocks
Some FFI requires `unsafe` Rust:
```rust
unsafe fn extract_pubkey(py_bytes: &PyBytes) -> Pubkey {
    let slice = py_bytes.as_bytes();
    Pubkey::new_from_array(*array_ref![slice, 0, 32])
}
```
Careful auditing required.

---

## Trade-Off Analysis

### Why Not Alternatives?

| Alternative | Reason Rejected |
|-------------|-----------------|
| **Cython** | Still bound by GIL, marginal gains |
| **Numba** | JIT overhead, limited to NumPy operations |
| **C Extensions** | Manual memory management, less safe than Rust |
| **PyPy** | Incompatible with many Solana libraries |

### Performance vs. Maintainability

We accept **higher initial complexity** for:
- 10-20x speed improvements in hot paths
- Memory safety guarantees
- Future-proofing for institutional deployment

---

## Implementation Plan

### Phase 1: Core Primitives (Complete ✅)
- [x] `wss_aggregator.rs` - RPC deduplication
- [x] `cycle_finder.rs` - Arbitrage detection
- [x] `scorer.rs` - Signal validation

### Phase 2: Expansion (In Progress 🚧)
- [ ] `technical.rs` - RSI/EMA indicators
- [ ] `pda.rs` - O(1) Program Derived Address lookup
- [ ] `fee_engine.rs` - Congestion-aware gas estimation

### Phase 3: Advanced (Planned 📋)
- [ ] `jit_compiler.rs` - Runtime strategy compilation
- [ ] `network_submitter.rs` - Native JITO bundle dispatch

---

## Validation

### Benchmarks

Run comparative benchmarks:
```powershell
python benchmark_rust.py
```

Example output:
```
Python Baseline: 45.2ms
Rust FFI:        3.1ms
Speedup:         14.6x
```

### Memory Profiling

```powershell
# Python memory usage
python -m memory_profiler main.py

# Rust allocations
cd src_rust
cargo build --release
valgrind --tool=massif target/release/phantom_core
```

---

## References

- [PyO3 User Guide](https://pyo3.rs/)
- [Maturin Documentation](https://www.maturin.rs/)
- [Rust Performance Book](https://nnethercote.github.io/perf-book/)
- ADR-0001: Hybrid Architecture (TypeScript bridges)
