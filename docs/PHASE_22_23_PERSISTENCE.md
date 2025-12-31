# Phase 22 & 23: Metadata & Pool Persistence

**Goal**: Establish a permanent "Memory" for the bot. It should "know" the Solana ecosystem (Tokens and Pools) immediately upon startup without costly RPC re-fetching.

---

## 🏗️ Architecture: The "Dual-Plex" Registry

We separate the **Structure** (Immutable Identity) from the **State** (Mutable Prices/Liquidity).

### 1. Token Persistence (Phase 22)

**Objective**: Persist Token Metadata (Mint, Symbol, Decimals) to `archives/tokens_registry.json`.

* **Component**: `TokenRegistry`
* **Logic**:
  * **Rehydrate**: Load `tokens_registry.json` -> SQLite `tokens` table.
  * **Dehydrate**: Dump SQLite `tokens` table -> `tokens_registry.json` (Append-only).
  * **Filter**: Only save tokens that were involved in a trade or valid cycle.

### 2. Market/Pool Persistence (Phase 23)

**Objective**: Persist Pool Graph (Edges) to `archives/pools_registry.json`.

* **Component**: `MarketManager`
* **Logic**:
  * **Rehydrate**: Load `pools_registry.json` -> SQLite `pools` table.
  * **Dehydrate**: Dump SQLite `pools` table -> `pools_registry.json`.
  * **Filter (Smart Pruning)**:
    * Must have > $500 Liquidity (at some point).
    * Must have active recent volume.
    * "Dead" pools (0 liq for >3 missions) are pruned.

---

## 🛠️ Implementation Plan

### 1. New Repositories (`src/shared/persistence/`)

* `token_registry.py`: Handles Token JSON <-> SQL sync.
* `market_manager.py`: Handles Pool JSON <-> SQL sync.

### 2. Database Updates (`DatabaseCore`)

* Ensure `tokens` table exists: `(mint_address TEXT PRIMARY KEY, symbol TEXT, decimals INTEGER, ...)`
* Ensure `pools` table exists: `(address TEXT PRIMARY KEY, token_a TEXT, token_b TEXT, dex_type TEXT, ...)`

### 3. Hydration Integration (`HydrationManager`)

* Update `rehydrate()` to call `TokenRegistry.rehydrate()` and `MarketManager.rehydrate()` *before* restoring mission data.
* Update `dehydrate()` to call `TokenRegistry.dehydrate()` and `MarketManager.dehydrate()`.

### 4. Smart Filtering

* Implement simple filters to prevent "Registry Bloat" (thousands of trash meme coins).

---

## ✅ Verification

* **Script**: `scripts/verify_registries.py`
  * Populate Mock DB with Tokens/Pools.
  * Dehydrate.
  * Nuke DB.
  * Rehydrate.
  * Verify Tokens/Pools exist and "Trash" was filtered.

---

## 📂 File Structure

```text
src/
  shared/
    persistence/
      __init__.py
      token_registry.py
      market_manager.py
archives/
  tokens_registry.json
  pools_registry.json
  mission_<timestamp>.json
```
