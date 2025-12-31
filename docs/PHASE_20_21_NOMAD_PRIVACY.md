# Phase 20 & 21: Nomad Persistence & Privacy Shield

**Goal**: Achieve "Stateless Execution" (Nomad Mode) and "Zero-Storage Wallets" (Privacy Shield). The bot should be fully portable between machines without transferring sensitive keys or massive database files.

---

## 🏗️ Architecture: The "Nomad" Engine

The system uses a "Bellows" model:

1. **Exhale (Dehydrate)**: On exit, the hot SQLite database is compressed into a portable JSON archive.
2. **Inhale (Rehydrate)**: On startup, the system detects if the local DB is missing/stale and rebuilds it from the latest JSON archive.
3. **Ghost Authority**: The Private Key is **never** written to disk. It is injected into RAM via `getpass` at runtime and wiped on exit.

---

## ✅ Phase 20: The "Stateless Nomad" (Persistence)

**Objective**: Automate the Hydration/Dehydration loop in `main.py` so the user never has to manually manage save files.

### 1. The Phoenix Bootloader (`main.py`)

- **Action**: Add `hydration.ensure_ready()` to the startup sequence.
- **Logic**:
  - If `data/trading_journal.db` is missing but `archives/` exist: **Auto-Rehydrate**.
  - If `data/trading_journal.db` exists: Use as is (Hot Cache).

### 2. The Preservation Snap (`main.py`)

- **Action**: Wrap the main execution loop in a `try...finally` block (or `atexit`).
- **Logic**:
  - On `SIGINT` (Ctrl+C) or Error: Trigger `hydration.dehydrate()`.
  - Save mission delta to `archives/mission_<timestamp>.json`.
  - **Crucial**: Ensure NO wallet data is in the context passed to the archive.

### 3. Smart "Delta" Archiving

- **Mission Files**: `archives/mission_2025_12_31.json` (Granular logs).
- **Summary File**: `archives/ledger_summary.json` (Life-to-date PnL).

---

## 🛡️ Phase 21: The "Privacy Shield" (Zero-Storage)

**Objective**: Decouple "Identity" (Keys) from "State" (DB/Archives).

### 1. Ephemeral Key Injection (`config_manager.py`)

- **Action**: Remove any file-based key loading (e.g., from `.env` or `secrets.json` if they exist).
- **Logic**:
  - In `LIVE` mode, use `getpass.getpass("🔑 Inject Private Key: ")`.
  - Store key in `SessionContext` (RAM only).
  - Never log the key.

### 2. The Archive Scrubber (`hydration_manager.py`)

- **Action**: Sanitize data before JSON serialization.
- **Logic**:
  - `context.pop('wallet_key', None)` before dumping to JSON.
  - Ensure no `signatures` are logged that could link to an identity (optional, but good hygiene).

### 3. Memory Zeroing (`main.py`)

- **Action**: Explicitly `del session_context.wallet_key` on shutdown.

---

## 📋 Implementation Checklist

### Phase 20: Nomad Persistence

- [ ] **Startup**: `HydrationManager.ensure_ready()` in `main.py`
- [ ] **Shutdown**: Auto-Dehydrate on `Ctrl+C` via `atexit` or `finally`
- [ ] **Git**: Update `.gitignore` to ignore `.db` but track `archives/*.json`

### Phase 21: Privacy Shield

- [ ] **Config**: Implement `getpass` key injection in `ConfigManager`
- [ ] **Scrub**: Ensure `HydrationManager.dehydrate` strips sensitive keys
- [ ] **Verify**: `scripts/verify_privacy.py` (Mock a run, check generated JSON for keys)
