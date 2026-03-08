# WASM MIGRATION GUIDE: High-Performance Web Node

This document outlines the roadmap for compiling PhantomArbiter's Rust core into WebAssembly (WASM) to power the "Thin Client" dashboard.

## 🏗 Build Environment

We use `wasm-pack` to compile to a target that is ready for Web Workers.

### Prerequisites
```powershell
cargo install wasm-pack
```

### Build Command
Run this from `src_rust/` to generate the WASM package:
```powershell
wasm-pack build --target web --out-dir ../frontend/wasm
```

## 🔌 Feature Flags (Critical)

To run `solana-sdk` and other dependencies in the browser, you must enable `js` feature flags in `Cargo.toml`.

```toml
[dependencies]
solana-sdk = { version = "1.18", features = ["js"] }
wasm-bindgen = "0.2"
getrandom = { version = "0.2", features = ["js"] }
```

## 🧠 Architecture: The Web Worker Pattern

To prevent blocking the browser's UI thread (60FPS integrity), the WASM module MUST run in a background worker.

### Phase 1: Web Math Worker
The `web_math.rs` module provides bit-perfect parity for arbitrage calculations.

```javascript
// Example: worker.js
import init, { calculate_net_profit } from './wasm/phantom_core.js';

async function run() {
    await init();
    self.onmessage = (e) => {
        const { spread, size, tip, friction } = e.data;
        const profit = calculate_net_profit(spread, size, tip, friction);
        self.postMessage({ profit });
    };
}
run();
```

## ⚠️ Known Constraints
- **Networking**: `reqwest` and `tokio` are not natively WASM-compatible for direct RPC calls. Use `web-sys` or `js-sys` fetch wrappers.
- **Signing**: Ed25519 signing works in WASM but requires `getrandom` with `js` enabled.
- **Multithreading**: Rust `rayon` requires `SharedArrayBuffer`, which needs specific COOP/COEP headers on your server (Hugo/GitHub Pages needs configuration).

## 🛡️ The "Safety Gate" Pattern (Defensive UI)

The `validate_execution_gate` should be used in the browser to prevent users from executing "Toxic Orders" before they hit the chain.

```javascript
// Example: trader-ui.js
import { validate_execution_gate } from './wasm/phantom_core.js';

function checkTradeSafety(spread, liquidity, vol) {
    const isSafe = validate_execution_gate(spread, liquidity, vol);
    
    if (!isSafe) {
        document.getElementById('execute-btn').disabled = true;
        document.getElementById('safety-warning').innerText = "⚠️ TOXIC MARKET CONDITIONS";
    }
}
```

## 🚀 Next Steps
1.  Verify Parity: `python scripts/verify_rust_parity.py`
2.  Enable `wasm-pack` CI/CD pipeline.
3.  Port `WSS aggregator` logic for browser-native price discovery.
