"""
Galaxy Server - Standalone FastAPI application.

Receives events from Core Engine and broadcasts to browser clients.
Serves the Three.js dashboard frontend.
"""

from __future__ import annotations

import os
import sys
import asyncio
from typing import List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from galaxy.models import EventPayload, VisualObject, EventType
from galaxy.visual_transformer import VisualTransformer
from galaxy.connection_manager import connection_manager
from galaxy.state import galaxy_state
from galaxy.cache_bridge import cache_bridge


# --- Configuration ---
GALAXY_PORT = int(os.getenv("GALAXY_PORT", "8001"))
GALAXY_HOST = os.getenv("GALAXY_HOST", "0.0.0.0")


# --- Pydantic Request Models ---
class EventBatch(BaseModel):
    """Batch of events from Core Engine."""
    events: List[EventPayload]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    clients: int = 0
    objects: int = 0


# --- Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    print(f"🌌 [Galaxy] Server starting on http://{GALAXY_HOST}:{GALAXY_PORT}")
    print(f"🎙️  [Galaxy] WebSocket stream: ws://{GALAXY_HOST}:{GALAXY_PORT}/ws/v1/stream")
    
    # Start FlashCache Bridge
    bridge_task = asyncio.create_task(cache_bridge.start())
    
    yield
    
    # Shutdown
    print("🌌 [Galaxy] Server shutting down")
    cache_bridge.stop()
    await bridge_task


# --- App Definition ---
app = FastAPI(
    title="Phantom Galaxy",
    description="3D Visualization Dashboard for PhantomArbiter",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# CORS - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Endpoints ---

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        clients=connection_manager.client_count,
        objects=galaxy_state.count,
    )


@app.get("/api/v1/state")
async def get_state():
    """Get current Galaxy state for new clients."""
    objects = await galaxy_state.get_all()
    return [obj.model_dump() for obj in objects]


@app.post("/api/v1/events")
async def receive_events(batch: EventBatch):
    """
    Receive event batch from Core Engine.
    
    Transforms events and broadcasts to all connected browsers.
    """
    visual_objects: List[VisualObject] = []
    
    for event in batch.events:
        try:
            obj = VisualTransformer.transform(event)
            if obj:
                visual_objects.append(obj)
        except Exception as e:
            print(f"⚠️ [Galaxy] Transform error: {e}")
            continue
    
    if not visual_objects:
        return {"status": "empty", "processed": 0}
    
    # Update state
    await galaxy_state.update_batch(visual_objects)
    
    # Broadcast to browsers
    payloads = [obj.model_dump() for obj in visual_objects]
    sent = await connection_manager.broadcast_batch(payloads)
    
    return {
        "status": "processed",
        "received": len(batch.events),
        "transformed": len(visual_objects),
        "broadcast_to": sent,
    }


@app.post("/api/v1/event")
async def receive_single_event(event: EventPayload):
    """
    Receive a single event from Core Engine.
    
    Convenience endpoint for low-volume events.
    """
    obj = VisualTransformer.transform(event)
    if not obj:
        return {"status": "skipped"}
    
    await galaxy_state.update(obj)
    sent = await connection_manager.broadcast(obj.model_dump())
    
    return {"status": "processed", "broadcast_to": sent}


# --- WebSocket Endpoints ---

@app.websocket("/ws/v1/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Real-time event stream for browser clients.
    
    On connect, sends current Galaxy state.
    Then streams updates as they arrive.
    """
    await connection_manager.connect(websocket)
    client_info = f"{websocket.client.host}:{websocket.client.port}"
    print(f"🔌 [Galaxy] Client connected: {client_info}")
    
    try:
        # Send current state on connect
        objects = await galaxy_state.get_all()
        if objects:
            snapshot = {
                "type": "STATE_SNAPSHOT",
                "data": [obj.model_dump() for obj in objects],
            }
            await websocket.send_json(snapshot)
        
        # Keep alive and handle control messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # Ping every 30s
                )
                # Handle control messages if needed
                if data == "PING":
                    await websocket.send_json({"type": "PONG"})
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "PING"})
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"⚠️ [Galaxy] WebSocket error: {e}")
    finally:
        await connection_manager.disconnect(websocket)
        print(f"🔌 [Galaxy] Client disconnected: {client_info}")


# --- Static Files ---
# Resolve frontend directory relative to this file
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# apps/galaxy/src/galaxy/server.py -> apps/galaxy/frontend
FRONTEND_DIR = os.path.normpath(os.path.join(CURRENT_DIR, "..", "..", "frontend"))

if os.path.isdir(FRONTEND_DIR):
    print(f"📂 [Galaxy] Serving frontend from: {FRONTEND_DIR}")
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    print(f"⚠️ [Galaxy] Frontend directory not found: {FRONTEND_DIR}")


# --- Main Entry Point ---
def main():
    """Run the Galaxy server."""
    import uvicorn
    
    uvicorn.run(
        "galaxy.server:app",
        host=GALAXY_HOST,
        port=GALAXY_PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
