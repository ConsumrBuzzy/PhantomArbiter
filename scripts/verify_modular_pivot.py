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
    print(f"   Settings.HOP_ENGINE_ENABLED: {getattr(Settings, 'HOP_ENGINE_ENABLED', 'UNKNOWN')}")
    
    # Initialize Dashboard (triggering registration)
    dash = PulsedDashboard()
    
    print(f"   Registry Slots: {registry._slots.keys()}")
    
    # Check registry
    shadow_frag = registry.get_fragment("shadow")    # ScavengerFragment
    stats_frag = registry.get_fragment("stats")      # JitoBundleFragment (Narrow Path)
    scalper_frag = registry.get_fragment("scalper")  # MultiverseFragment
    inv_frag = registry.get_fragment("inventory")    # GraphStatsFragment
    
    print(f"   Shadow Fragment: {shadow_frag.__class__.__name__ if shadow_frag else 'None'}")
    print(f"   Stats Fragment: {stats_frag.__class__.__name__ if stats_frag else 'None'}")
    print(f"   Scalper Fragment: {scalper_frag.__class__.__name__ if scalper_frag else 'None'}")
    
    assert shadow_frag is not None, "ScavengerFragment not registered"
    assert "Jito" in stats_frag.__class__.__name__, f"Expected JitoBundleFragment, got {stats_frag.__class__.__name__}"
    assert "Multiverse" in scalper_frag.__class__.__name__, "MultiverseFragment not registered"
    
    print("✅ DashboardRegistry passed")

def test_fragment_rendering():
    print("\n🎨 Testing Fragment Rendering (Soak Simulation)...")
    # Mock State
    class MockState:
        def __init__(self):
            self.hop_cycles = {
                'best': {'path_display': 'SOL -> USDC -> BONK -> SOL', 'profit_pct': 0.75},
                'cycles_by_hops': {3: 15, 4: 5}
            }
            self.graph_stats = {'nodes': 1000, 'edges': 5000, 'last_update': 'Few seconds ago'}
            self.pod_stats = {
                'pods': [
                    {'pod_type': 'execution', 'recent_history': [
                        {'expected_profit_pct': 1.2, 'tip_lamports': 50000, 'mode': 'GHOST', 'signature': 'ghost_sig_123'}
                    ]}
                ]
            }
            self.shadow_stats = {}
            self.stats = {}
            
    state = MockState()
    
    # Test Hop Fragments
    from src.arbiter.ui.fragments.narrow_path import MultiverseFragment, GraphStatsFragment, JitoBundleFragment
    
    frags = [MultiverseFragment(), GraphStatsFragment(), JitoBundleFragment()]
    for f in frags:
        try:
            renderable = f.render(state)
            print(f"   Rendered {f.name}: OK")
        except Exception as e:
            print(f"   ❌ Failed to render {f.name}: {e}")
            raise e
            
    print("✅ UI Rendering Stability passed")

if __name__ == "__main__":
    try:
        test_strategy_factory()
        test_dashboard_registry()
        test_fragment_rendering()
        print("\n🎉 ALL SYSTEMS GO")
    except AssertionError as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ RUNTIME ERROR: {e}")
        sys.exit(1)
