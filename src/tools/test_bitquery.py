
import os
import sys
import requests
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.curdir))

load_dotenv()

api_key = os.getenv("BITQUERY_API_KEY")
print(f"DEBUG: API Key present: {bool(api_key)}")

if not api_key:
    print("❌ BITQUERY_API_KEY missing in .env")
    sys.exit(1)

REST_URL = "https://streaming.bitquery.io/graphql"
QUERY = """
query {
  Solana {
    DEXTrades(limit: {count: 1}) {
      Trade {
        Buy {
          Account {
            Token {
              Owner
            }
          }
        }
      }
    }
  }
}
"""

headers = {
    "Content-Type": "application/json",
    "X-API-KEY": api_key
}

payload = {"query": QUERY}

try:
    resp = requests.post(REST_URL, json=payload, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
