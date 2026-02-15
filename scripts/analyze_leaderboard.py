import requests
import json
import statistics

# Endpoint for z.ink Leaderboard (from User Intel)
# The user mentioned: https://api.z.ink/v1/profiles/leaderboard?limit=100&orderBy=xp&order=desc
# But diagnostic showed 404 for that specific path.
# We will try the base and inferred paths, but if they fail, we will use mock data for the analysis logic 
# to demonstrate the "Leaderboard Analysis" capability as requested.

API_URL = "https://api.z.ink/v1/profiles"

def fetch_leaderboard():
    print(f"Fetching Leaderboard from {API_URL}...")
    try:
        # Try likely endpoint structures based on standard REST patterns
        endpoints = [
            f"{API_URL}",
            f"{API_URL}/leaderboard",
            f"{API_URL}?sort=xp&limit=1000"
        ]
        
        data = []
        for url in endpoints:
            try:
                print(f"   Probing {url}...")
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    json_data = resp.json()
                    if isinstance(json_data, list):
                        data = json_data
                        print(f"   ✅ SUCCESS: Found {len(data)} profiles.")
                        break
                    elif isinstance(json_data, dict) and 'profiles' in json_data:
                        data = json_data['profiles']
                        print(f"   ✅ SUCCESS: Found {len(data)} profiles.")
                        break
            except:
                continue
        
        if not data:
            print("   ⚠️  Live Leaderboard Unreachable (404/403). Using MOCK DATA for analysis demonstration.")
            return generate_mock_leaderboard()
            
        return data

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return generate_mock_leaderboard()

def generate_mock_leaderboard():
    """Generate realistic mock data based on 'Origin Season' metrics."""
    import random
    profiles = []
    # whales
    for i in range(10): 
        profiles.append({"rank": i+1, "xp": random.randint(500000, 1000000), "address": f"Whale_{i}"})
    # dolphins
    for i in range(11, 100):
        profiles.append({"rank": i+1, "xp": random.randint(100000, 499999), "address": f"Dolphin_{i}"})
    # minnows (target)
    for i in range(101, 1000):
        profiles.append({"rank": i+1, "xp": random.randint(10000, 99999), "address": f"User_{i}"})
    
    return profiles

def analyze_data(profiles):
    print("\n=== 📊 LEADERBOARD ANALYSIS (Origin Season) ===")
    
    if not profiles:
        print("No data to analyze.")
        return

    # Sort by XP desc just in case
    sorted_profiles = sorted(profiles, key=lambda x: x.get('xp', 0), reverse=True)
    
    xp_values = [p.get('xp', 0) for p in sorted_profiles]
    
    top_10_avg = statistics.mean(xp_values[:10])
    top_100_threshold = xp_values[99] if len(xp_values) >= 100 else 0
    top_1000_threshold = xp_values[999] if len(xp_values) >= 1000 else 0
    
    print(f"🏆 Top 10 Average XP: {top_10_avg:,.0f}")
    print(f"🥈 Top 100 Entry XP:  {top_100_threshold:,.0f}")
    print(f"🥉 Top 1000 Entry XP: {top_1000_threshold:,.0f}")
    
    print("-" * 40)
    print("🎯 STRATEGY TARGETS:")
    
    # Calculate daily targets (assuming 30 days left)
    days_remaining = 30
    daily_xp_needed = top_1000_threshold / days_remaining
    
    print(f"   To Breaching Top 1000: {top_1000_threshold:,.0f} XP")
    print(f"   Daily Run Rate Needed: {daily_xp_needed:,.0f} XP/day")
    
    # Volume estimation (1.5x Multiplier)
    # XP = (Vol * 150) * 1.5
    # Vol = XP / (150 * 1.5)
    
    vol_needed = daily_xp_needed / (150 * 1.5)
    print(f"   Est. Daily Volume:     {vol_needed:,.2f} SOL (approx)")

if __name__ == "__main__":
    profiles = fetch_leaderboard()
    analyze_data(profiles)
