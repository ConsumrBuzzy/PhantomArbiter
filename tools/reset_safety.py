import json
import os
import sys

# Path to price_cache.json
CACHE_FILE = os.path.join("data", "price_cache.json")

def reset_safety():
    if not os.path.exists(CACHE_FILE):
        print("Cache file not found.")
        return

    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        
        # Clear safety data
        if "safety" in data:
            print(f"Found {len(data['safety'])} safety records. Clearing...")
            data["safety"] = {}
            
            with open(CACHE_FILE, 'w') as f:
                json.dump(data, f)
            print("✅ Safety cache cleared. Broker will re-validate on next loop.")
        else:
            print("No safety data found.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_safety()
