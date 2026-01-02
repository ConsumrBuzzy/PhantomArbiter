import sys
import os

# quick hack to add src
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.normpath(os.path.join(current_dir, "../"))
sys.path.insert(0, root_dir)

try:
    from src.arbiter.core.arbiter_engine import ArbiterEngine
    print("✅ Successfully imported ArbiterEngine")
except ImportError as e:
    print(f"❌ Import Error: {e}")
except NameError as e:
    print(f"❌ Name Error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
