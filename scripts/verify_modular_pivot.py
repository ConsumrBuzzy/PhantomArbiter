"""
Verify Modular Pivot
====================
Checks if the Modular Architecture components are correctly wired.
1. StrategyFactory spawns correct pods
2. DashboardRegistry has registered fragments
3. ExecutionPod has GhostValidator initialized
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock

# Mock settings
sys.modules['config.settings'] = MagicMock()
from config.settings import Settings
Settings.HOP_ENGINE_ENABLED = True
Settings.SOL_MINT = "So11111111111111111111111111111111111111112"
Settings.HOP_MIN_LEGS = 3
Settings.HOP_MAX_LEGS = 4
Settings.HOP_MIN_LIQUIDITY_USD = 1000.0
Settings.HOP_MIN_PROFIT_PCT = 0.5
Settings.PRIVATE_KEY_BASE58 = "5M..." # Mock key

# Add src to path
sys.path.append(os.getcwd())

from src.engine.strategy_factory import StrategyFactory, StrategyMode
from src.engine.pod_manager import PodManager, PodType
from src.engine.execution_pod import ExecutionMode
from src.arbiter.ui.fragments.registry import registry
from src.arbiter.ui.pulsed_dashboard import PulsedDashboard

def test_strategy_factory():
    print("🏭 Testing StrategyFactory...")
    manager = PodManager()
    factory = StrategyFactory(manager)
    
    config = {'execution_mode': 'ghost'}
    pods = factory.spawn_pods(StrategyMode.NARROW_PATH, config)
    
    pod_types = [p.config.pod_type for p in pods]
    print(f"   Spawned {len(pods)} pods: {[p.id for p in pods]}")
    
    assert PodType.WHALE in pod_types, "BridgePod (WHALE) missing"
    assert PodType.CYCLE in pod_types, "CyclePod missing"
    assert PodType.HOP in pod_types, "HopPod missing"
    assert PodType.EXECUTION in pod_types, "ExecutionPod missing"
    
    # Check ExecutionPod mode
    # Find by type primarily, fall back to ID if needed
    exec_pod = next(p for p in pods if p.config.pod_type == PodType.EXECUTION)
    print(f"   ExecutionPod Mode: {exec_pod.mode}")
    assert exec_pod.mode == ExecutionMode.GHOST, f"Expected GHOST mode, got {exec_pod.mode}"
    
    print("✅ StrategyFactory passed")

def test_dashboard_registry():
    print("\n🧩 Testing DashboardRegistry...")
    # Initialize Dashboard (triggering registration)
    dash = PulsedDashboard()
    
    # Check registry
    shadow_frag = registry.get_fragment("scavenger") # Name is 'scavenger' for ScavengerFragment
    stats_frag = registry.get_fragment("flow")       # Name is 'flow' for FlowFragment
    
    print(f"   Shadow Slot Fragment: {shadow_frag.__class__.__name__ if shadow_frag else 'None'}")
    print(f"   Stats Slot Fragment: {stats_frag.__class__.__name__ if stats_frag else 'None'}")
    
    assert shadow_frag is not None, "ScavengerFragment not registered in Shadow slot"
    assert stats_frag is not None, "FlowFragment not registered in Stats slot"
    
    print("✅ DashboardRegistry passed")

if __name__ == "__main__":
    try:
        test_strategy_factory()
        test_dashboard_registry()
        print("\n🎉 ALL SYSTEMS GO")
    except AssertionError as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ RUNTIME ERROR: {e}")
        sys.exit(1)
