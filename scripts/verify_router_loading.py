import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.shared.system.smart_router import SmartRouter
from src.shared.system.logging import Logger

def verify_router():
    print("🌐 Verifying SmartRouter Endpoint Loading...")
    
    # Force re-init if singleton already exists (though here it's fresh process)
    if SmartRouter._instance:
        SmartRouter._instance = None
        
    router = SmartRouter()
    
    count = len(router.endpoints)
    print(f"✅ Loaded {count} endpoints.")
    
    if count == 0:
        print("❌ FAILED: endpoints is empty!")
        sys.exit(1)
        
    # Check if Jito Execution URL is resolvable
    jito_url = router.get_jito_execution_url()
    print(f"✅ Jito Execution URL: {jito_url}")
    
    if not jito_url:
        print("⚠️ WARNING: Jito URL not found (might affect private txs)")

if __name__ == "__main__":
    verify_router()
