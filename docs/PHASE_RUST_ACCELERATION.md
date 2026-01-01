# 🦀 Phase 18: Rust Acceleration (The Forge)

**Status**: 📋 Planning  
**Target**: Q1 2025  
**Goal**: Migrate remaining CPU-intensive Python components to Rust for 10-100x performance gains.

> **Cross-Reference**: See [TODO.md](./TODO.md) for sprint tracking

---

## 📊 Current Rust Infrastructure

The `phantom_core` crate (`src_rust/`) already contains:

| Module | Function | Status |
|--------|----------|--------|
| `log_parser.rs` | Flash swap log decoding | ✅ Active |
| `cycle_finder.rs` | Bellman-Ford cycle detection | ✅ Active |
| `graph.rs` | Pool matrix & edge management | ✅ Active |
| `multiverse.rs` | 2-5 hop scanner | ✅ Active |
| `scorer.rs` | Signal scoring | ✅ Active |
| `amm_math.rs` | AMM calculations | ✅ Active |
| `slab_decoder.rs` | Serum/OpenBook slab parsing | ✅ Active |
| `tick_array_manager.rs` | CLMM tick management | ✅ Active |

---

## 🎯 Phase 18 Targets

### Tier 1: High-Impact (🔥🔥🔥)

#### 1. Technical Analysis Engine
```
Current: src/strategy/signals.py
Target: src_rust/src/technical.rs
Impact: RSI/EMA/Bollinger calculated on every price update
Gain: ~50x faster, enables real-time multi-token scanning
```

**Implementation**:
- [ ] Port `TechnicalAnalysis` class to Rust
- [ ] Expose `calculate_rsi()`, `calculate_ema()`, `calculate_bollinger()` via PyO3
- [ ] Integrate with `Watcher.inject_price()` for real-time RSI

#### 2. PDA Derivation Cache
```
Current: src/liquidity/orca_adapter.py (derive_whirlpool_address)
Target: src_rust/src/pda.rs
Impact: SHA256 + Ed25519 curve ops on every pool lookup
Gain: ~100x faster, pre-compute all pool PDAs at startup
```

**Implementation**:
- [ ] Port Solana PDA derivation to Rust (using `solana-program`)
- [ ] Batch derive all known token pairs at startup
- [ ] Cache results in HashMap for O(1) lookup

#### 3. Fee Estimation Engine
```
Current: src/arbiter/core/fee_estimator.py
Target: src_rust/src/fees.rs
Impact: Priority fee + MEV calculation on every trade
Gain: ~20x faster, real-time congestion modeling
```

**Implementation**:
- [ ] Port `FeeEstimator` to Rust
- [ ] Integrate with priority fee APIs (Helius, Triton)
- [ ] Add congestion-based dynamic adjustment

---

### Tier 2: Medium-Impact (🔥🔥)

#### 4. Base58 Codec
```
Current: Python base58 library
Target: src_rust/src/base58.rs
Impact: Every signature/address encoding/decoding
Gain: ~30x faster
```

#### 5. Transaction Signature Parser
```
Current: src/shared/infrastructure/websocket_listener.py
Target: src_rust/src/tx_parser.rs
Impact: Parse token mints from transaction logs
Gain: Enables linking swaps to specific tokens
```

#### 6. Token Balance Scanner
```
Current: Various wallet scanning code
Target: src_rust/src/balance_scanner.rs
Impact: SPL token account deserialization
Gain: ~20x faster wallet state checks
```

---

### Tier 3: Future (🔥)

| Component | Current Location | Potential Gain |
|-----------|------------------|----------------|
| Order Book Aggregation | Various | 15x |
| Merkle Proof Verification | Not implemented | Required for MEV |
| Quote Compression | Not implemented | Reduces memory |

---

## 🏗️ Architecture

```
phantom_core/
├── Cargo.toml
└── src/
    ├── lib.rs              # PyO3 module exports
    ├── log_parser.rs       ✅ Existing
    ├── cycle_finder.rs     ✅ Existing
    ├── graph.rs            ✅ Existing
    ├── multiverse.rs       ✅ Existing
    ├── scorer.rs           ✅ Existing
    ├── amm_math.rs         ✅ Existing
    ├── technical.rs        🆕 Phase 18.1
    ├── pda.rs              🆕 Phase 18.2
    ├── fees.rs             🆕 Phase 18.3
    ├── base58.rs           🆕 Phase 18.4
    ├── tx_parser.rs        🆕 Phase 18.5
    └── balance_scanner.rs  🆕 Phase 18.6
```

---

## 📋 Sprint Breakdown

### Sprint 18.1: Technical Analysis (1 week)
- [ ] Create `technical.rs` with RSI/EMA functions
- [ ] Add PyO3 bindings to `lib.rs`
- [ ] Update `Watcher` to use Rust RSI
- [ ] Benchmark: Target <1ms for 500 data points

### Sprint 18.2: PDA Cache (1 week)
- [ ] Create `pda.rs` with Solana crate integration
- [ ] Build startup cache for top 500 token pairs
- [ ] Replace Python PDA calls in `orca_adapter.py`
- [ ] Benchmark: Target <10μs per lookup

### Sprint 18.3: Fee Engine (1 week)
- [ ] Port `FeeEstimator` logic to `fees.rs`
- [ ] Add real-time congestion scoring
- [ ] Integrate with `spread_detector.py`
- [ ] Benchmark: Target <100μs per estimation

### Sprint 18.4: Transaction Parser (2 weeks)
- [ ] Create `tx_parser.rs` for log parsing
- [ ] Extract token mints from Raydium/Orca logs
- [ ] Enable linking DEX swaps to specific tokens
- [ ] This fixes "Raydium values not floating with tokens"

---

## 🎯 Success Metrics

| Metric | Before | Target | Measurement |
|--------|--------|--------|-------------|
| RSI Calculation | ~5ms | <0.1ms | Per token |
| PDA Derivation | ~50ms | <0.01ms | Per lookup |
| Fee Estimation | ~10ms | <0.5ms | Per trade |
| Spread Scan Cycle | ~26s | <5s | Full portfolio |

---

## 🔗 Related Documents

- [TODO.md](./TODO.md) - Sprint tracking
- [PHASE_NARROW_PATH.md](./PHASE_NARROW_PATH.md) - Existing Rust integration
- [DATA_PIPELINE.md](./DATA_PIPELINE.md) - Data flow architecture

---

*Last Updated: 2025-12-31*
