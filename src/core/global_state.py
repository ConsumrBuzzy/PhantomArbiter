"""
V15.0: Global State Manager
===========================
Handles synchronization of global settings (Mode, Size, Budget)
across multiple processes using a shared JSON file.

Source of Truth: config/global_state.json
Concurrency: Uses atomic file writes (os.replace) and retry logic.
"""

import os
import time
import json
import logging
from typing import Dict, Any

class GlobalState:
    
    # Path resolved relative to this file
    _CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config"))
    _STATE_FILE = os.path.join(_CONFIG_DIR, "global_state.json")
    
    # Defaults
    DEFAULTS = {
        "MODE": "MONITOR",          # "MONITOR" or "LIVE"
        "BASE_SIZE_USD": 50.0,      # Base trade size
        "MAX_EXPOSURE_USD": 1000.0, # Total risk budget
        "ENGINES_HALTED": False,    # V18.0: Global emergency stop (all engines)
        "ENGINE_STATUS": {          # V39.3: Per-engine status tracking
            "SCALPER": "RUNNING",
            "KELTNER": "RUNNING",
            "VWAP": "RUNNING",
            "DATA": "RUNNING"
        },
        "LIVE_ENGINE_TARGET": None,  # V39.9: Which engine should trade live (None = all in monitor)
        "last_update": 0
    }

    @staticmethod
    def _read_raw() -> Dict[str, Any]:
        """Read the JSON file directly. (Optimized with mtime check)"""
        # Static cache for mtime/content
        if not hasattr(GlobalState, '_cache_mtime'):
             GlobalState._cache_mtime = 0
             GlobalState._cache_content = GlobalState.DEFAULTS.copy()

        if not os.path.exists(GlobalState._STATE_FILE):
            return GlobalState.DEFAULTS.copy()
            
        try:
            current_mtime = os.path.getmtime(GlobalState._STATE_FILE)
            if current_mtime == GlobalState._cache_mtime:
                # No change, return cached
                return GlobalState._cache_content
                
            # Changed! Read file
            with open(GlobalState._STATE_FILE, 'r') as f:
                content = json.load(f)
                GlobalState._cache_content = content
                GlobalState._cache_mtime = current_mtime
                return content
        except Exception:
            # If read fails (race condition), return last known good cache
            return getattr(GlobalState, '_cache_content', GlobalState.DEFAULTS.copy())

    @staticmethod
    def _write_raw(state: Dict[str, Any]):
        """Atomic write with retry logic."""
        temp_file = GlobalState._STATE_FILE + ".tmp"
        
        # Ensure timestamp is updated
        state["last_update"] = time.time()
        
        max_retries = 5
        for i in range(max_retries):
            try:
                with open(temp_file, 'w') as f:
                    json.dump(state, f, indent=4)
                
                # Atomic swap
                os.replace(temp_file, GlobalState._STATE_FILE)
                return
            except PermissionError:
                if i == max_retries - 1:
                    logging.error("❌ GLOBAL STATE LOCK ERROR: Could not write state.")
                time.sleep(0.05)
            except Exception as e:
                logging.error(f"❌ GLOBAL STATE WRITE ERROR: {e}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return

    @staticmethod
    def read_state() -> Dict[str, Any]:
        """Public API to get current global state."""
        state = GlobalState._read_raw()
        # Ensure all keys exist (migration safety)
        for k, v in GlobalState.DEFAULTS.items():
            if k not in state:
                state[k] = v
        return state

    @staticmethod
    def update_state(updates: Dict[str, Any]):
        """Public API to update specific keys atomically."""
        # 1. Read current valid state
        current = GlobalState._read_raw()
        
        # 2. Apply updates
        changed = False
        for k, v in updates.items():
            if k in GlobalState.DEFAULTS and current.get(k) != v:
                current[k] = v
                changed = True
        
        # 3. Write back if changed
        if changed:
            GlobalState._write_raw(current)
            logging.info(f"🔄 GLOBAL STATE UPDATED: {updates}")
