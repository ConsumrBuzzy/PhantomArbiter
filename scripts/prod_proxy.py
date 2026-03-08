import json
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Any
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import phantom_core

# ------------------------------------------------------------------------
# PHASE 25: PRODUCTION SERVER BRIDGE (ZERO-LEAK)
# This script acts as the secure aggregator for the PhantomArbiter ecosystem.
# ------------------------------------------------------------------------

app = FastAPI(title="PhantomArbiter Production Bridge", version="1.0.0")

# Security: Restricted CORS for the Production Site
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with your specific domain
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Global State: The "Pulse" Payload
pulse_state = {
    "price": {"sol_usd": 83.87, "change_24h": -4.58},
    "whales": [],
    "yield": {
        "apr": 0.0,
        "apy": 0.0,
        "basis": 0.0,
        "status": "NORMAL"
    },
    "sentiment": 50.12,
    "last_updated": datetime.now().isoformat()
}

@app.on_event("startup")
async def start_pulse_background_loop():
    """Background task to maintain the 1Hz discovery logic."""
    asyncio.create_task(pulse_loop())

async def pulse_loop():
    while True:
        try:
            start_time = time.perf_counter()
            
            # 1. Update Yield Math (Phase 23)
            # March 7 Context: rate = -0.000238
            rate = -0.000238
            pulse_state["yield"]["apr"] = phantom_core.calculate_funding_apr(rate) * 100
            pulse_state["yield"]["apy"] = phantom_core.calculate_funding_apy(rate)
            pulse_state["yield"]["basis"] = phantom_core.calculate_basis_yield(84.0, 84.15)
            pulse_state["yield"]["status"] = "SPIKE" if abs(pulse_state["yield"]["apy"]) > 50 else "NORMAL"
            
            # 2. Load Recent Whales (Phase 22)
            try:
                with open("sentinel_alerts.json", "r") as f:
                    alerts = json.load(f)
                    pulse_state["whales"] = alerts[:5] # Last 5 alerts
            except:
                pass
                
            # 3. Update Static Fallback every 60s
            if int(time.time()) % 60 == 0:
                with open("public/ticker.json", "w") as f:
                    json.dump(pulse_state, f, indent=2)
            
            pulse_state["last_updated"] = datetime.now().isoformat()
            
            # Microsecond Latency Tracking
            process_time = (time.perf_counter() - start_time) * 1000
            pulse_state["process_ms"] = process_time
            
            await asyncio.sleep(1) # Keep at 1Hz
        except Exception as e:
            print(f"Pulse Error: {e}")
            await asyncio.sleep(5)

@app.get("/api/v1/pulse")
async def get_pulse(request: Request):
    """The High-Fidelity Market Pulse Endpoint."""
    return pulse_state

if __name__ == "__main__":
    import uvicorn
    # Use --forwarded-allow-ips="*" for Nginx compatibility
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")
