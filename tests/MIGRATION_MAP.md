# Test Migration Map

**Purpose**: Guide for migrating existing 33 root-level tests into the new 3-tier structure.

## Root Tests → New Location

| Current File | Target Location | Category | Priority |
|--------------|-----------------|----------|----------|
| `test_amm_math.py` | `unit/rust/` | Rust binding | P0 |
| `test_signal_scorer.py` | `unit/rust/` | Rust binding | P0 |
| `test_slab_decoder.py` | `unit/rust/` | Rust binding | P0 |
| `test_pda_rust.py` | `unit/rust/` | Rust binding | P0 |
| `test_wss_aggregator.py` | `unit/rust/` | Rust binding | P0 |
| `test_multi_hop.py` | `integration/layer_b/` | Arbitrage wiring | P1 |
| `test_scavenger.py` | `integration/layer_b/` | Agent wiring | P1 |
| `test_websocket_integration.py` | `integration/layer_a/` | Data feed | P1 |
| `test_discovery_simple.py` | `integration/layer_a/` | Token discovery | P2 |
| `test_silent_discovery.py` | `integration/layer_a/` | Token discovery | P2 |
| `test_scout_agent.py` | `integration/layer_b/` | Agent wiring | P2 |
| `test_whale_boost.py` | `integration/layer_b/` | Agent wiring | P2 |
| `test_feature_engineering.py` | `unit/layer_b_execution/` | ML features | P2 |
| `test_regime_simple.py` | `unit/layer_b_execution/` | Market regime | P2 |
| `test_simulation_simple.py` | `integration/layer_b/` | Paper trading | P2 |
| `test_raydium_bridge_rust.py` | `unit/rust/` | Rust binding | P1 |
| `test_raydium_clmm.py` | `integration/layer_b/` | DEX wiring | P2 |
| `test_instruction_builder.py` | `unit/rust/` | Rust binding | P1 |
| `test_tick_array_manager.py` | `unit/rust/` | Rust binding | P1 |
| `test_slot_consensus.py` | `unit/rust/` | Rust binding | P2 |
| `test_unification.py` | `integration/layer_b/` | System wiring | P1 |
| `test_bitquery_*.py` | **DELETE** | Deprecated API | - |
| `test_rpc_depth.py` | `integration/layer_a/` | RPC testing | P3 |
| `test_sauron.py` | **INVESTIGATE** | Unknown | - |
| `mainnet_swap_test.py` | `e2e/` | E2E swap | P2 |
| `token_audit_test.py` | `integration/layer_a/` | Validation | P2 |
| `verify_*.py` | **KEEP** | Health checks | - |

## Integration Tests → New Location

| Current File | Target Location | Notes |
|--------------|-----------------|-------|
| `integration/test_trade_executor.py` | `integration/layer_b/` | Critical |
| `integration/test_heartbeat_reporter.py` | `integration/layer_b/` | Keep |
| `integration/test_held_detection.py` | `integration/layer_b/` | Keep |
| `integration/test_pyth_adapter.py` | `integration/layer_a/` | Oracle |
| `integration/test_jupiter*.py` | `integration/layer_b/` | DEX |
| `integration/test_token_2022.py` | `integration/layer_a/` | Token standard |
| `integration/test_all_apis.py` | `integration/layer_c/` | API tests |

## Migration Commands

```powershell
# Phase 1: Rust tests
Move-Item tests/test_amm_math.py tests/unit/rust/
Move-Item tests/test_signal_scorer.py tests/unit/rust/
Move-Item tests/test_slab_decoder.py tests/unit/rust/
Move-Item tests/test_pda_rust.py tests/unit/rust/
Move-Item tests/test_wss_aggregator.py tests/unit/rust/
Move-Item tests/test_raydium_bridge_rust.py tests/unit/rust/
Move-Item tests/test_instruction_builder.py tests/unit/rust/
Move-Item tests/test_tick_array_manager.py tests/unit/rust/
Move-Item tests/test_slot_consensus.py tests/unit/rust/

# Phase 2: Layer A (Market)
Move-Item tests/test_websocket_integration.py tests/integration/layer_a/
Move-Item tests/test_discovery_simple.py tests/integration/layer_a/
Move-Item tests/test_silent_discovery.py tests/integration/layer_a/

# Phase 3: Layer B (Execution)
Move-Item tests/test_multi_hop.py tests/integration/layer_b/
Move-Item tests/test_scavenger.py tests/integration/layer_b/
Move-Item tests/test_unification.py tests/integration/layer_b/
```
