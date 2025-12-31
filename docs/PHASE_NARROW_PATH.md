# 🏛️ Phase Plan: Project "Narrow Path"

**Focus**: Long-Tail Multi-Hop Arbitrage (Token Hopping)  
**Status**: 🚧 Strategic Pivot In Progress  
**Created**: 2025-12-31  
**Owner**: PyPro / Architect

---

## 📋 Executive Summary

This document outlines the strategic "narrowing" of PhantomArbiter. We are pivoting from a **multi-strategy engine** to a specialized **Long-Tail Token Hopper**. By disabling the high-velocity Token Scalper and its associated heavy lifting (ML filters, sentiment analysis), we free up CPU cycles and memory for the computationally intensive task of **Multi-Hop Pathfinding**.

> [!IMPORTANT]
> This pivot represents a fundamental architectural shift. The Scalper relied on "First-to-See" latency—a losing battle on free RPCs. Token Hopping relies on **Complex Pathfinding**.

---

## 1. Strategy Logic: Why "Hopping"?

### The Edge

| Approach | Latency Dependency | Our Advantage |
|----------|-------------------|---------------|
| Token Scalper | HIGH (First-to-See) | ❌ Losing on free RPCs |
| Token Hopping | LOW (Complex Paths) | ✅ Rust core beats Python bots |

**The Goal**: Find `$SOL → Token A → Token B → SOL$` cycles that the "Giants" ignore due to:

1. **Low Liquidity** - Not worth their bandwidth
2. **Path Complexity** - 3+ hops require significant compute
3. **Tail Tokens** - Off the radar of major market makers

### Why This Works

1. **Computational Moat**: Your Rust core (`phantom_core`) can calculate paths across **5,000+ pools** faster than Python bots
2. **Reduced Competition**: Lower volume in tail pools means the "latency war" is less intense
3. **Atomic Execution**: Jito bundles ensure all legs execute or none do (no partial exposure)

---

## 2. Component Deactivation Plan ("The Slim-Down")

To focus 100% on hopping, we put the following "High-Noise" components into **Deep Sleep** state:

| Component | File | Status | Reasoning |
|-----------|------|--------|-----------|
| `WhaleWatcherAgent` | `src/scraper/agents/whale_watcher_agent.py` | 🔴 **DISABLED** | Scalper-centric. Whale sentiment irrelevant for atomic arb. |
| `ML_Filter` (XGBoost) | `src/ml/trainer_supervisor.py` | 🔴 **DISABLED** | Removes 50-100ms inference delay. Arb is math, not prediction. |
| `ScoutAgent` (Meme-Focus) | `src/scraper/agents/scout_agent.py` | 🔴 **DISABLED** | Stop hunting "New Launches", focus on "Stable Inefficiencies". |
| `SentimentEngine` | `src/services/*` | 🔴 **DISABLED** | Social signals irrelevant for instantaneous price gaps. |
| `TradingCore` (Scalper Mode) | `src/engine/trading_core.py` | 🔴 **DISABLED** | MerchantEnsemble no longer needed for probabilistic trades. |

### Settings Changes

```python
# config/settings.py - Narrow Path Configuration
SCALPER_ENABLED = False          # Disable Token Scalper
ENABLE_SCALPER = False           # Legacy flag
WHALE_FOLLOW_THRESHOLD = 999.0   # Effectively disable whale following
ML_AUTO_RETRAIN = False          # No ML model training
PAPER_AGGRESSIVE_MODE = False    # Conservative mode for arb testing
```

---

## 3. Structural Modifications

### A. The Core Logic Shift

We move primary decision-making from:

- ❌ `DecisionEngine` (Probabilistic)
- ✅ `HopGraphEngine` (Deterministic)

#### Affected Files

| File | Modification |
|------|-------------|
| [director.py](file:///c:/Github/PhantomArbiter/src/engine/director.py) | Set `lite_mode = True`, skip ML/Whale loading |
| [trading_core.py](file:///c:/Github/PhantomArbiter/src/engine/trading_core.py) | Remove ML model initialization |
| [arbiter.py](file:///c:/Github/PhantomArbiter/src/arbiter/arbiter.py) | Integrate `HopGraphEngine` as primary scanner |

### B. Tethering the "Hopper"

The Hop Arbiter needs direct connection to `RpcConnectionManager` for **Parallel Polling**:

```
┌─────────────────┐     ┌─────────────────┐
│  Helius RPC     │     │  Alchemy RPC    │
│  (Raydium)      │     │  (Orca)         │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
           ┌─────────────────────┐
           │   HopGraphEngine    │
           │   (Rust Core)       │
           └─────────────────────┘
```

**Action**: Instead of one RPC for everything, the Hopper uses:

- **Helius** for Raydium prices
- **Alchemy** for Orca prices
- **Parallel fetch** to detect gaps faster

---

## 4. New "Hopping" Infrastructure

### Rust Core Additions (`src_rust/src/`)

#### A. `graph.rs` - The Pool Matrix

A directed graph containing **every active pool**. Every price update from `WssAggregator` updates an edge.

```rust
// src_rust/src/graph.rs (NEW)
use pyo3::prelude::*;
use std::collections::HashMap;

/// Edge weight = -log(exchange_rate) for Bellman-Ford
#[pyclass]
pub struct PoolEdge {
    pub source_mint: String,      // Token A
    pub target_mint: String,      // Token B  
    pub pool_address: String,
    pub exchange_rate: f64,       // A/B rate
    pub weight: f64,              // -ln(rate) for cycle detection
    pub fee_bps: u16,
    pub liquidity: u64,
    pub last_update_slot: u64,
}

#[pyclass]
pub struct HopGraph {
    edges: HashMap<String, Vec<PoolEdge>>,  // Adjacency list
    node_count: usize,
    edge_count: usize,
}

#[pymethods]
impl HopGraph {
    #[new]
    pub fn new() -> Self { /* ... */ }
    
    /// Update edge from WSS price feed
    pub fn update_edge(&mut self, edge: PoolEdge) { /* ... */ }
    
    /// Get all edges from a source token
    pub fn get_outbound(&self, mint: &str) -> Vec<&PoolEdge> { /* ... */ }
    
    /// Total pool count
    pub fn pool_count(&self) -> usize { self.edge_count }
}
```

#### B. `cycle_finder.rs` - The Hunter

Uses modified **Bellman-Ford** or **Johnson's algorithm** to find negative cycles (profit opportunities).

```rust
// src_rust/src/cycle_finder.rs (NEW)
use pyo3::prelude::*;
use crate::graph::HopGraph;

#[pyclass]
#[derive(Clone)]
pub struct HopCycle {
    pub path: Vec<String>,        // [SOL, TokenA, TokenB, SOL]
    pub pool_addresses: Vec<String>,
    pub theoretical_profit_pct: f64,
    pub min_liquidity: u64,
    pub total_fee_bps: u16,
}

#[pyclass]
pub struct CycleFinder {
    max_hops: usize,              // 3, 4, or 5
    min_profit_threshold: f64,    // e.g., 0.002 = 0.2%
}

#[pymethods]
impl CycleFinder {
    #[new]
    #[pyo3(signature = (max_hops=4, min_profit_threshold=0.002))]
    pub fn new(max_hops: usize, min_profit_threshold: f64) -> Self {
        Self { max_hops, min_profit_threshold }
    }
    
    /// Find all profitable cycles starting from SOL
    pub fn find_cycles(&self, graph: &HopGraph, start_mint: &str) -> Vec<HopCycle> {
        // Bellman-Ford with negative cycle detection
        // For each node, track: (distance, predecessor)
        // Negative cycle = sum of edge weights < 0 = profit
        /* ... */
    }
    
    /// Fast path: Check if a specific path is profitable NOW
    pub fn validate_path(&self, graph: &HopGraph, path: &[String]) -> Option<HopCycle> {
        /* ... */
    }
}
```

### Python Integration

#### `src/arbiter/core/hop_engine.py` (NEW)

```python
from phantom_core import HopGraph, CycleFinder, HopCycle
from src.arbiter.core.atomic_executor import AtomicExecutor

class HopGraphEngine:
    """
    Deterministic Multi-Hop Arbitrage Engine.
    Replaces probabilistic DecisionEngine for Narrow Path strategy.
    """
    
    def __init__(self, max_hops: int = 4, min_profit_pct: float = 0.20):
        self.graph = HopGraph()
        self.finder = CycleFinder(max_hops, min_profit_pct / 100)
        self.executor = AtomicExecutor()
        
    def update_pool(self, pool_data: dict):
        """Ingest real-time pool update from WSS."""
        edge = self._to_edge(pool_data)
        self.graph.update_edge(edge)
        
    def scan(self) -> list[HopCycle]:
        """Scan for profitable cycles."""
        sol_mint = "So11111111111111111111111111111111111111112"
        return self.finder.find_cycles(self.graph, sol_mint)
        
    def execute(self, cycle: HopCycle, amount_sol: float) -> dict:
        """Execute via Jito bundle."""
        return self.executor.execute_multi_hop(cycle, amount_sol)
```

---

## 5. Atomic Executor Upgrade

The `AtomicExecutor` must handle **3+ swaps in a single Jito bundle**:

### Current State

- Supports 2-leg swaps (Spatial Arb)
- Uses [router.rs](file:///c:/Github/PhantomArbiter/src_rust/src/router.rs) for execution

### Required Changes

```rust
// src_rust/src/router.rs - Add multi-hop support
impl UnifiedTradeRouter {
    /// Execute N-leg arbitrage as atomic bundle
    pub fn route_multi_hop(
        &self,
        swap_instructions: Vec<Vec<u8>>,  // Serialized instructions
        tip_lamports: u64,
    ) -> PyResult<String> {
        // 1. Deserialize all instructions
        // 2. Add Jito tip as final instruction
        // 3. Submit as single bundle
        // 4. All-or-nothing execution
        /* ... */
    }
}
```

---

## 6. Dashboard Redesign

The Rich Dashboard will be simplified to focus on **Path Efficiency**:

### New Metrics Panel

| Metric | Description |
|--------|-------------|
| **ACTIVE PATHS** | Number of 3-leg cycles being monitored |
| **BEST SPREAD** | Highest current theoretical arb (e.g., +0.42%) |
| **JITO STATUS** | Success rate of multi-instruction bundles |
| **POOL COUNT** | Total pools in graph |
| **SCAN LATENCY** | Time to complete full graph scan |

### Removed Panels

- ❌ Whale Activity Feed
- ❌ ML Confidence Score
- ❌ Scout Discovery Queue
- ❌ Sentiment Indicators

---

## 7. Integration TODO List

### Phase 1: Cleanup (Slim-Down)

- [ ] Comment out `WhaleWatcher` initialization in [director.py](file:///c:/Github/PhantomArbiter/src/engine/director.py#L66-L67)
- [ ] Comment out `ScoutAgent` initialization in [director.py](file:///c:/Github/PhantomArbiter/src/engine/director.py#L71-L72)
- [ ] Set `SCALPER_ENABLED = False` in [settings.py](file:///c:/Github/PhantomArbiter/config/settings.py)
- [ ] Disable ML model loading in [trading_core.py](file:///c:/Github/PhantomArbiter/src/engine/trading_core.py)

### Phase 2: New Infrastructure

- [ ] Create `src_rust/src/graph.rs` (Pool Graph)
- [ ] Create `src_rust/src/cycle_finder.rs` (Bellman-Ford)
- [ ] Export new modules in [lib.rs](file:///c:/Github/PhantomArbiter/src_rust/src/lib.rs)
- [ ] Create `src/arbiter/core/hop_engine.py` (Python wrapper)

### Phase 3: Integration

- [ ] Upgrade `AtomicExecutor` for 4-leg bundles
- [ ] Wire `HopGraphEngine` into `PhantomArbiter.run()` loop
- [ ] Update dashboard for new metrics

### Phase 4: Testing

- [ ] Unit tests for cycle detection
- [ ] Paper trade 3-leg cycles
- [ ] Benchmark graph updates (target: <1ms per update)

---

## 8. Critical Trade-offs

### FFI Overhead vs. Execution Speed

| Consideration | Impact |
|---------------|--------|
| **Rust ↔ Python boundary** | ~10-50μs per call |
| **Graph scan in Rust** | ~100μs for 5000 pools |
| **Python-only equivalent** | ~50ms for same scan |

**Decision**: Keep graph operations in Rust. The 500x speedup justifies the FFI overhead.

### Memory Trade-off

| Component | Memory Impact |
|-----------|---------------|
| **Removed**: ML Models | -150MB (XGBoost + features) |
| **Removed**: Whale Cache | -20MB |
| **Added**: Pool Graph | +50MB (10K pools estimate) |
| **Net Change** | **-120MB freed** |

---

## 9. Scalability Notes

### Increased Load (More Pools)

The graph structure scales **O(V + E)** where:

- V = unique tokens (~2000)
- E = pools (~10000)

For 50K pools: ~100ms scan time (acceptable for 2s scan interval)

### Cross-Platform (Windows/Linux/Mac)

Rust core via PyO3/Maturin compiles natively on all platforms. No platform-specific changes required.

### Multi-RPC Scaling

Parallel polling architecture supports adding more RPC endpoints without code changes—just configuration.

---

## 10. Next Steps

With the Scalper out of the way, your bot's "Sauron Eye" can focus 100% on pool price gaps.

### Recommended Execution Order

1. **Draft `graph.rs`** - Core data structure
2. **Draft `cycle_finder.rs`** - Detection algorithm
3. **Modify `director.py`** - Sunset Scalper agents
4. **Create `hop_engine.py`** - Python integration
5. **Update `AtomicExecutor`** - 4-leg bundle support

---

## Related Documents

- [TRADING_STRATEGIES.md](file:///c:/Github/PhantomArbiter/docs/TRADING_STRATEGIES.md) - Current strategy overview
- [EXECUTION.md](file:///c:/Github/PhantomArbiter/docs/EXECUTION.md) - Jito bundle details
- [ARCHITECTURE.md](file:///c:/Github/PhantomArbiter/ARCHITECTURE.md) - System overview
- [TODO.md](file:///c:/Github/PhantomArbiter/docs/TODO.md) - Master task list
