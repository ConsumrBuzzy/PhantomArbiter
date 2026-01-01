
import asyncio
import json
import websockets
import pytest
from src.interface.dashboard_server import DashboardServer
from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.shared.system.logging import Logger

@pytest.mark.asyncio
async def test_dashboard_connection():
    """Verify that the DashboardServer broadcasts signals to clients."""
    
    # 1. Start Server
    server = DashboardServer(port=8766) # Use test port
    server_task = asyncio.create_task(server.start())
    
    # Allow server to bind
    await asyncio.sleep(0.5)

    received_messages = []

    # 2. Client Connection
    async with websockets.connect("ws://127.0.0.1:8766") as ws:
        # Handshake
        await ws.send(json.dumps({"action": "REQUEST_SYNC"}))
        response = await ws.recv()
        data = json.loads(response)
        assert data["type"] == "PING"
        
        # 3. Emit Signal
        test_signal = Signal(
            type=SignalType.MARKET_UPDATE,
            source="TEST",
            data={
                "mint": "So11111111111111111111111111111111111111112",
                "symbol": "SOL",
                "price": 150.0
            }
        )
        signal_bus.emit(test_signal)
        
        # 4. Await Broadcast
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            payload = json.loads(msg)
            received_messages.append(payload)
        except asyncio.TimeoutError:
            pytest.fail("Timed out waiting for signal broadcast")

    # 5. Cleanup
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass

    # 6. Assertions
    assert len(received_messages) == 1
    event = received_messages[0]
    assert event["type"] == "ARCHETYPE_UPDATE"
    assert event["label"] == "SOL"
    assert event["archetype"] == "GLOBE" # Default for unknown source

if __name__ == "__main__":
    # Manual run if executed directly
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_dashboard_connection())
    print("[OK] Verification Passed")
