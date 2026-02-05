import json
import random
import os

def generate_leads():
    leads = []
    base_address = "AddressMockWhalePriority"
    
    print("generating 1000 leads...")
    for i in range(1000):
        leads.append({
            "address": f"{base_address}{i:04d}",
            "category": "Meme-Whale-2024",
            "notes": "High volume BONK trader, dormant > 90 days",
            "last_active": "2024-12-01T00:00:00Z"
        })
        
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "data", "leads_priority_1.json")
    
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2)
        
    print(f"Generated {len(leads)} leads at {output_path}")

if __name__ == "__main__":
    generate_leads()
