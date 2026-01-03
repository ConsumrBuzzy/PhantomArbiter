import grpc
import asyncio
import logging
from typing import Callable, Any
from apps.datafeed.src.datafeed import market_data_pb2_grpc, market_data_pb2

logger = logging.getLogger("DataFeedClient")

class DataFeedClient:
    """
    Client for the unified DataFeed gRPC Service.
    Consumes consolidated market stream (WSS + Scrapers).
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
        self.stub = market_data_pb2_grpc.MarketDataServiceStub(self.channel)
        logger.info("✅ Connected to DataFeed Service")

    async def stream_prices(self, callback: Callable[[Any], None]):
        """
        Subscribe to unified price stream.
        Callback format: async func(response)
        """
        if not self.stub:
            logger.error("Cannot stream: No stub connected.")
            return

        request = market_data_pb2.StreamRequest(client_id="core_broker")
        
        try:
            logger.info("🌊 Subscribing to unified price stream...")
            async for response in self.stub.StreamPrices(request):
                # Response is a MarketUpdate with a list of PricePoints
                if response.price_point:
                    await callback(response.price_point)
                    
        except asyncio.CancelledError:
            logger.info("Stream cancelled.")
        except grpc.RpcError as e:
            logger.error(f"gRPC Stream Error: {e}")
            # Simple reconnection logic could go here
            await asyncio.sleep(5)

    async def close(self):
        if self.channel:
            await self.channel.close()
