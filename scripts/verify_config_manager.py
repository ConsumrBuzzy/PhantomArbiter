"""
Verify Config Manager
=====================
Tests the ConfigManager's ability to load session context from JSON.
"""

import os
import json
import sys
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.append(os.getcwd())

from src.shared.system.config_manager import ConfigManager, SessionContext

def test_json_loading():
    print("📂 Testing ConfigManager JSON Loading...")
    
    # Create valid config
    config = {
        "strategy_mode": "NARROW_PATH",
        "execution_mode": "GHOST",
        "budget_sol": 50.0,
        "params": {"test": "val"}
    }
    
    with open("session_config.json", "w") as f:
        json.dump(config, f)
        
    try:
        context = ConfigManager.get_session_context()
        
        print(f"   Context Loaded: {context}")
        
        assert context.strategy_mode == "NARROW_PATH"
        assert context.execution_mode == "GHOST"
        assert context.budget_sol == 50.0
        assert context.params.get("test") == "val"
        
        print("✅ JSON Loading passed")
        
    except Exception as e:
        print(f"❌ JSON Loading failed: {e}")
        raise e
    finally:
        if os.path.exists("session_config.json"):
            os.remove("session_config.json")

def test_headless_main_integration():
    print("\n🚀 Testing Main Entrypoint Integration (Headless)...")
    
    # Mock ConfigManager to return a known context with Risk Profile
    mock_ctx = SessionContext(
        strategy_mode="NARROW_PATH",
        execution_mode="GHOST",
        budget_sol=10.0,
        params={"risk_profile": "AGGRESSIVE"}
    )
    
    # Mock subprocess for latency check
    with patch('subprocess.run') as mock_run_cmd:
        with patch('src.shared.system.config_manager.ConfigManager.get_session_context', return_value=mock_ctx):
            with patch('src.main.run_arbiter_session') as mock_run_session:
                
                from src.main import main
                
                # Simulate --headless
                with patch('sys.argv', ['main.py', '--headless']):
                    main()
                    
                mock_run_session.assert_called_once()
                # Verify context passed has risk profile
                args, _ = mock_run_session.call_args
                assert args[0].params["risk_profile"] == "AGGRESSIVE"
                
                print("✅ Main integration (Risk Profile) passed")

if __name__ == "__main__":
    try:
        test_json_loading()
        test_headless_main_integration()
        print("\n🎉 ConfigManager Verified")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
