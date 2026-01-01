import asyncio
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.arbiter.visual_transformer import VisualTransformer
from src.shared.state.app_state import state

# --- Pydantic Models ---
class VisualParams(BaseModel):
    radius: float
    roughness: float
    emissive_intensity: float
    hex_color: str
    velocity_factor: Optional[float] = None
    metalness: Optional[float] = 0.2

class VisualObject(BaseModel):
    type: str # "ARCHETYPE_UPDATE"
    id: str
    label: str
    archetype: str # "GLOBE", "PULSAR", "COMET", etc.
    params: VisualParams

# --- Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    Logger.info("   🛸 [API] Mission Control Online")
    yield
    Logger.info("   🛸 [API] Mission Control Shutting Down")

# --- App Definition ---
app = FastAPI(
    title="PhantomArbiter API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Dead connection, ignore (will be removed on disconnect)
                pass

manager = ConnectionManager()

# --- Signal Bridge ---
# Bridge SignalBus -> WebSocket Manager
def signal_handler(signal: Signal):
    # Transform Signal -> VisualObject
    payload = VisualTransformer.transform(signal)
    if payload:
        # We need to broadcast this to all websocket clients.
        # Since this callback might be synchronous or async depending on emitting source,
        # and broadcast is async, we need to ensure we are in a loop context.
        # SignalBus executes async callbacks with create_task, so we can define this as async.
        pass

async def async_signal_handler(signal: Signal):
    payload = VisualTransformer.transform(signal)
    if payload:
        await manager.broadcast(payload)

# Subscribe to relevant signals
signal_bus.subscribe(SignalType.MARKET_UPDATE, async_signal_handler)
signal_bus.subscribe(SignalType.NEW_TOKEN, async_signal_handler)
# Add other types as needed by VisualTransformer

# --- Endpoints ---

@app.get("/api/v1/galaxy", response_model=List[VisualObject])
async def get_initial_galaxy():
    """
    Returns the initial state of the galaxy (all known active tokens).
    """
    # 1. Fetch from AppState/Inventory
    objects = []
    
    # Example: Add Portfolio items as Globes
    for item in state.inventory:
        # Create a mock signal to use existing transformer
        sig = Signal(
            type=SignalType.METADATA, 
            source="INVENTORY",
            data={
                "mint": item.symbol, # inventory uses symbol as key usually
                "symbol": item.symbol,
                "label": item.symbol,
                "token": item.symbol 
            }
        )
        payload = VisualTransformer.transform(sig)
        if payload:
            objects.append(payload)
            
    # We could also fetch from TokenRegistry if available
    # For now, let's return what we have in state + maybe top cached pulses?
    for symbol, pulse in state.market_pulse.items():
         sig = Signal(
            type=SignalType.MARKET_UPDATE,
            source="PULSE_INIT",
            data={
                "mint": symbol, # fallback
                "symbol": symbol,
                "token": symbol,
                "price": pulse.get("price", 0)
            }
        )
         payload = VisualTransformer.transform(sig)
         if payload:
             objects.append(payload)

    return objects

@app.websocket("/ws/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive / receive control messages
            data = await websocket.receive_text()
            # Optional: Client can send filter requests here
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        Logger.error(f"   ❌ [API] WebSocket Error: {e}")
        manager.disconnect(websocket)

# --- Static Files ---
# Mount frontend directory to serve dashboard.html
# Access at http://localhost:8000/dashboard.html by default if in root of frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
