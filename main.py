
import asyncio
import signal
import sys
from src.system.startup_manager import StartupManager
from src.utils.boot_utils import BootTimer

# V87.0: SRP Refactored Main Orchestrator
# Logic moved to src/system/startup_manager.py and src/services/

async def main():
    # 0. Start Timer (V86.1)
    BootTimer.start()
    
    print("\n   🚀 STARTING PHANTOM TRADER (V87.0 Refactored)")
    print("   ═══════════════════════════════════════════════")
    
    # 1. Initialize Manager
    startup = StartupManager()
    
    # 2. Register Signals
    # Windows doesn't support adding handlers for SIGINT to loop easily in some versions,
    # but StartupManager handles signal.signal() for threads.
    signal.signal(signal.SIGINT, startup.signal_handler)
    signal.signal(signal.SIGTERM, startup.signal_handler)
    
    # 3. Init Core
    await startup.initialize_core()
    
    # 4. Launch Services
    await startup.launch_services()
    
    # 5. Wait for Shutdown
    await startup.wait_for_shutdown()

if __name__ == "__main__":
    try:
        # Use asyncio.run for cleaner entry/exit
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Critical Error: {e}")
        import traceback
        traceback.print_exc()
