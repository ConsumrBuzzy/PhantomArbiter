import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from src.engine.pump_monitor import PumpFunMonitor
    import phantom_core
    
    print("✅ Successfully imported PumpFunMonitor and phantom_core")
    
    monitor = PumpFunMonitor()
    print("✅ Monitor instantiated")
    
    # We can't actually start it without a valid WSS URL (which settings has) 
    # but we can check if the underlying Rust class accepts the filter arg
    # by inspecting the signature or just trying it.
    
    # Mock settings / aggregator behavior check
    # In a real environment we would need the build to match the code.
    
    print("Test Complete: Import successful. (Run 'python main.py --monitor' to integrate)")
    
except Exception as e:
    print(f"❌ Verification Failed: {e}")
    sys.exit(1)
