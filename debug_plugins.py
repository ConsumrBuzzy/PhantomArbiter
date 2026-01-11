
import sys
try:
    from importlib.metadata import entry_points
    eps = entry_points()
    # Python 3.10+ returns a SelectableGroups object, older returns dict
    if hasattr(eps, 'select'):
        params = eps.select(group='pytest11')
    else:
        params = eps.get('pytest11', [])
    
    print(f"Python executable: {sys.executable}")
    print(f"Path: {sys.path[:3]}...")
    print("\n[pytest11] Entry Points:")
    for ep in params:
        print(f"  {ep.name} -> {ep.value}")
        
except ImportError:
    print("Could not import importlib.metadata")
