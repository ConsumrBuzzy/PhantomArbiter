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
from src.arbiter.coordinate_transformer import CoordinateTransformer
from src.arbiter.coordinate_transformer import CoordinateTransformer
from src.shared.state.app_state import state
from src.shared.infrastructure.token_registry import TokenRegistry  # V34: Core Taxonomy

# --- Pydantic Models ---
class VisualParams(BaseModel):
    radius: float
    roughness: float
    emissive_intensity: float
    hex_color: str
    velocity_factor: Optional[float] = None
    metalness: Optional[float] = 0.2
    x: Optional[float] = 0.0
    y: Optional[float] = 0.0
    z: Optional[float] = 0.0

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
                # Debug: Check for NaN
                import json
                try:
                   json.dumps(message, allow_nan=False)
                except ValueError:
                   Logger.error(f"❌ [API] JSON NaN detected in payload: {message}")
                   continue

                await connection.send_json(message)
            except Exception as e:
                # Dead connection, ignore (will be removed on disconnect)
                # Logger.warning(f"[API] Broadcast failed: {e}")
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
    # V34: Inject Taxonomy Category
    data = signal.data
    mint = data.get("mint") or data.get("token")
    if mint:
        try:
            # Quick lookup from singleton
            category = TokenRegistry().get_category(mint)
            if category:
                data["category"] = category
        except Exception:
            pass

    payload = VisualTransformer.transform(signal)
    if payload:
        await manager.broadcast(payload)

# Arbitrage opportunity -> Hop Path visualization
async def async_arb_handler(signal: Signal):
    """Convert ARB_OPP signals to HOP_PATH visualization."""
    data = signal.data
    path = data.get("path") or data.get("cycle") or []
    profit = data.get("profit") or data.get("expected_profit") or 0.01
    
    if path and len(path) >= 2:
        hop_payload = {
            "type": "HOP_PATH",
            "path": path,
            "profit": profit,
            "source": signal.source
        }
        await manager.broadcast(hop_payload)

# Phase 12: MARKET_INTEL -> Galaxy Map Heat/Pressure overlay
async def async_market_intel_handler(signal: Signal):
    """Broadcast market intelligence to Galaxy Map."""
    data = signal.data
    intel_payload = {
        "type": "MARKET_INTEL",
        "mint": data.get("mint", ""),
        "heat": data.get("heat", 0.0),
        "regime": data.get("regime", "UNKNOWN"),
        "pressure": data.get("pressure", {}),
        "whiff_count": data.get("whiff_count", 0),
    }
    await manager.broadcast(intel_payload)

# Phase 12: WHIFF_DETECTED -> Galaxy Map flash/alert + Pulse
async def async_whiff_handler(signal: Signal):
    """
    Broadcast whiff alerts to Galaxy Map.
    Triggers expanding shockwaves for large transactions.
    """
    data = signal.data
    source = signal.source or "WHALE"
    mint = data.get("mint", "")
    
    # Get spatial context
    x, y, z = CoordinateTransformer.get_xyz(data)
    
    whiff_payload = {
        "type": "WHALE_PULSE",
        "mint": mint,
        "x": x,
        "y": y,
        "z": z,
        "intensity": data.get("confidence", 0.5) * 10.0,
        "color": "#ffd700" if source == "WHALE" else "#00ffff" # Gold for whale, cyan for others
    }
    await manager.broadcast(whiff_payload)
    
    # Also send basic alert
    alert_payload = {
        "type": "WHIFF_ALERT",
        "whiff_type": data.get("type", "UNKNOWN"),
        "mint": mint,
        "direction": data.get("direction", "VOLATILE"),
        "confidence": data.get("confidence", 0.5),
    }
    await manager.broadcast(alert_payload)

# Phase 5: SYSTEM_STATS -> Real-time HUD
async def async_stats_handler(signal: Signal):
    """Broadcast system performance metrics."""
    await manager.broadcast({
        "type": "SYSTEM_STATS",
        "data": signal.data
    })

# Phase 5: LOG_UPDATE -> Real-time Log Stream
async def async_log_handler(signal: Signal):
    """Broadcast log entries for the virtualized log stream."""
    await manager.broadcast({
        "type": "LOG_ENTRY",
        "level": signal.data.get("level", "INFO"),
        "message": signal.data.get("message", ""),
        "timestamp": signal.timestamp
    })

# Phase 5: SCAN_UPDATE -> Top Spreads Table
async def async_scan_handler(signal: Signal):
    """Broadcast top arbitrage spreads for the interactive table."""
    await manager.broadcast({
        "type": "SCAN_UPDATE",
        "opportunities": signal.data.get("opportunities", [])
    })

# Subscribe to relevant signals AFTER defining handlers
signal_bus.subscribe(SignalType.MARKET_UPDATE, async_signal_handler)
signal_bus.subscribe(SignalType.NEW_TOKEN, async_signal_handler)
signal_bus.subscribe(SignalType.MARKET_INTEL, async_market_intel_handler)
signal_bus.subscribe(SignalType.WHIFF_DETECTED, async_whiff_handler)
signal_bus.subscribe(SignalType.ARB_OPP, async_arb_handler)
signal_bus.subscribe(SignalType.SYSTEM_STATS, async_stats_handler)
signal_bus.subscribe(SignalType.LOG_UPDATE, async_log_handler)
signal_bus.subscribe(SignalType.SCAN_UPDATE, async_scan_handler)

# --- Endpoints ---

@app.get("/api/v1/galaxy", response_model=List[VisualObject])
async def get_initial_galaxy():
    """
    Returns the initial state of the galaxy (all known active tokens).
    """
    Logger.info(f"   🛸 🔍 [API] Fetching Galaxy State...")
    # 1. Fetch from AppState/Inventory
    objects = []
    
    # Example: Add Portfolio items as Globes
    for item in state.inventory:
        # Create a mock signal to use existing transformer
        sig = Signal(
            type=SignalType.METADATA, 
            source="INVENTORY",
            data={
                "mint": item.symbol,
                "symbol": item.symbol,
                "label": item.symbol,
                "token": item.symbol 
            }
        )
        payload = VisualTransformer.transform(sig)
        if payload:
            objects.append(payload)
    
    # V38: Add all tokens from TokenRegistry as planets
    try:
        # Run blocking registry/cache operations in a thread preventing loop freeze
        def fetch_galaxy_nodes():
            from src.shared.infrastructure.token_registry import TokenRegistry
            from src.core.shared_cache import SharedPriceCache
            
            nodes = []
            registry = TokenRegistry()
            
            # Get cached prices and market data
            cached_prices = SharedPriceCache.get_all_prices(max_age=3600)  # 1 hour
            cached_market = SharedPriceCache.get_all_market_data(max_age=3600)
            
            if registry._initialized:
                all_tokens = {**registry._static, **registry._dynamic}
                for mint, symbol in all_tokens.items():
                    price = 0
                    rsi = 50
                    liquidity = 1000.0
                    volume = 0
                    
                    if symbol in cached_prices:
                        price = cached_prices[symbol].get("price", 0)
                    
                    # V140: Rich market data (Liquidity/RSI)
                    mkt = cached_market.get(mint) or cached_market.get(symbol)
                    if mkt:
                        liquidity = mkt.get("liquidity_usd", 1000.0)
                        volume = mkt.get("volume_24h_usd", 0)
                        # Estimate RSI from 1h change if needed, or use cached RSI if available
                        rsi = mkt.get("rsi", 50)
                    
                    # Try getting RSI from history if missing
                    if rsi == 50:
                        hist = SharedPriceCache.get_price_history(symbol)
                        if len(hist) > 14:
                            # Simple RSI estimation logic could go here
                            pass

                    sig = Signal(
                        type=SignalType.MARKET_UPDATE,
                        source="PYTH",  # PLANET archetype
                        data={
                            "mint": mint,
                            "symbol": symbol,
                            "label": symbol,
                            "price": price,
                            "rsi": rsi,
                            "liquidity": liquidity,
                            "rsi": rsi,
                            "liquidity": liquidity,
                            "volume_24h": volume,
                            "category": registry.get_category(mint)  # V34: Inject Category
                        }
                    )
                    payload = VisualTransformer.transform(sig)
                    if payload:
                        nodes.append(payload)
            print(f"[API] Loaded {len(all_tokens)} tokens from Registry (with {len(cached_prices)} cached prices)")
            return nodes

        # Await the thread result
        registry_nodes = await asyncio.to_thread(fetch_galaxy_nodes)
        objects.extend(registry_nodes)
            
    except Exception as e:
        print(f"[API] TokenRegistry init warning: {e}")
            
    # Add market pulse data
    for symbol, pulse in state.market_pulse.items():
         sig = Signal(
            type=SignalType.MARKET_UPDATE,
            source="PULSE_INIT",
            data={
                "mint": symbol,
                "symbol": symbol,
                "token": symbol,
                "price": pulse.get("price", 0)
            }
        )
         payload = VisualTransformer.transform(sig)
         if payload:
             objects.append(payload)

    Logger.info(f"   🛸 ✅ [API] Returning Galaxy: {len(objects)} nodes")
    return objects


class EventPayload(BaseModel):
    type: str
    source: str
    data: Dict[str, Any]

@app.post("/api/v1/events")
async def receive_event(event: EventPayload):
    """
    HTTP Bridge: Allows external services (EventBridge) to push signals to Galaxy.
    """
    # 1. Reconstruct Signal
    sig = Signal(
        type=SignalType(event.type) if event.type in SignalType.__members__ else SignalType.MARKET_UPDATE,
        source=event.source,
        data=event.data
    )
    
    # 2. Inject Category if needed (for external events)
    await async_signal_handler(sig)
    
    return {"status": "ok", "broadcast": True}

@app.websocket("/ws/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    Logger.info(f"   🛸 🔌 [API] WebSocket Client Connected: {websocket.client.host}:{websocket.client.port}")
    try:
        while True:
            # Keep alive / receive control messages
            data = await websocket.receive_text()
            # Optional: Client can send filter requests here
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except asyncio.CancelledError:
        # Normal shutdown
        manager.disconnect(websocket)
    except Exception as e:
        Logger.error(f"   ❌ [API] WebSocket Error: {e}")
        manager.disconnect(websocket)

# --- Static Files ---
import os
# Robust path resolution: Get project root relative to this file (src/interface/api_service.py)
# src/interface/api_service.py -> src/interface -> src -> root
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

Logger.info(f"   📂 [API] Serving Frontend from: {FRONTEND_DIR}")

# Mount frontend directory to serve dashboard.html
# Access at http://localhost:8000/dashboard.html by default if in root of frontend
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
