import grpc
import asyncio
import logging
from typing import Callable, Any
import time

# Since we don't have the compiled protobufs yet, we'll use a dynamic/generic approach 
# or just assume simple JSON-over-Stream if we were lazy, but let's try to be clean.
# Actually, for this phase, we implemented a simplified queues-based server in server.py
# that mimics gRPC behavior but we might need to rely on the server's actual implementation.

# Wait, in the server.py I defined a class `MarketDataServicer` but I did NOT compile the protos.
# So real gRPC calls will fail without the stubs.
# Strategy Shift: Since I cannot easily run `protoc` in this environment on the user's behalf 
# without risking path hell, I will implement a "Direct Import" Client for now if they are in the same process,
# OR purely rely on the fact that I *can* use the `grpc_asyncio` if I had the stubs.

# SOLUTION: I will generate the Stubs using `grpc_tools.protoc` via `run_command` first.
# That ensures we assume a proper microservice architecture.

logger = logging.getLogger("DataFeedClient")

class DataFeedClient:
    """
    Client for the DataFeed gRPC Service.
    """
    def __init__(self, host="localhost", port=9000):
        self.target = f"{host}:{port}"
        self.channel = None
        self.stub = None
        self._running = False

    async def connect(self):
        """Establish gRPC channel."""
        logger.info(f"Connecting to DataFeed at {self.target}...")
        self.channel = grpc.aio.insecure_channel(self.target)
        # We need the stubs to be generated first.
        # Check if modules exist, if not, warn.
        try:
            from apps.datafeed.src.datafeed import market_data_pb2_grpc, market_data_pb2
            self.stub = market_data_pb2_grpc.MarketDataServiceStub(self.channel)
            logger.info("✅ Connected to DataFeed Service")
        except ImportError:
            logger.error("❌ Protobuf stubs not found! Run build_proto.py")
            self.stub = None

    async def stream_prices(self, callback: Callable[[Any], None]):
        """Subscribe to price stream."""
        if not self.stub:
            logger.error("Cannot stream: No stub connected.")
            return

        from apps.datafeed.src.datafeed import market_data_pb2
        request = market_data_pb2.StreamRequest(client_id="core_broker")
        
        try:
            async for response in self.stub.StreamPrices(request):
                await callback(response)
        except asyncio.CancelledError:
            pass
        except grpc.RpcError as e:
            logger.error(f"gRPC Stream Error: {e}")

    async def close(self):
        if self.channel:
            await self.channel.close()
