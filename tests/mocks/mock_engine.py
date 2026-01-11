"""
Mock Trading Engine
===================
Testable BaseEngine subclass for lifecycle testing.
"""

from typing import Dict, Any, Optional
import asyncio


class MockTradingEngine:
    """
    Mock engine implementing BaseEngine interface for testing.
    
    Provides controllable tick behavior and state inspection.
    
    Usage:
        engine = MockTradingEngine("test")
        await engine.start()
        assert engine.running
        await engine.stop()
    """
    
    def __init__(self, name: str = "mock_engine", live_mode: bool = False):
        self.name = name
        self.live_mode = live_mode
        self.mode = "live" if live_mode else "paper"
        self.running = False
        self.tick_count = 0
        self.tick_results: list = []
        self.config: Dict[str, Any] = {}
        self._task: Optional[asyncio.Task] = None
        self._callback = None
        
        # State tracking for testing
        self.started_at: Optional[float] = None
        self.stopped_at: Optional[float] = None
        self.on_stop_called = False
        self.errors: list = []
        
        # Configurable behavior
        self.tick_delay = 0.1
        self.should_error_on_tick = False
        self.error_on_tick_number: Optional[int] = None
        
        # Paper wallet (mocked)
        self.paper_wallet = None
        if not live_mode:
            try:
                from src.shared.state.paper_wallet import get_engine_wallet
                self.paper_wallet = get_engine_wallet(name)
            except ImportError:
                pass
                
    def set_callback(self, callback):
        """Set broadcast callback."""
        self._callback = callback
        
    async def start(self, config: Optional[Dict[str, Any]] = None):
        """Start the engine loop."""
        if self.running:
            return
            
        if config:
            self.config.update(config)
            
        self.running = True
        self.started_at = asyncio.get_event_loop().time()
        
        self._task = asyncio.create_task(self._monitor_loop())
        
    async def stop(self):
        """Stop the engine loop."""
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        self.stopped_at = asyncio.get_event_loop().time()
        self.on_stop()
        
    def on_stop(self):
        """Called when engine stops."""
        self.on_stop_called = True
        
    async def _monitor_loop(self):
        """Internal tick loop."""
        while self.running:
            try:
                await self.tick()
                self.tick_count += 1
            except Exception as e:
                self.errors.append(str(e))
            await asyncio.sleep(self.tick_delay)
            
    async def tick(self):
        """Single execution step."""
        # Check if we should error
        if self.should_error_on_tick:
            raise RuntimeError("Configured tick error")
            
        if self.error_on_tick_number == self.tick_count:
            raise RuntimeError(f"Error on tick {self.tick_count}")
            
        # Store result
        result = {
            "tick": self.tick_count,
            "mode": self.mode,
            "config": self.config,
        }
        self.tick_results.append(result)
        
        # Broadcast if callback set
        if self._callback:
            self._callback(result)
            
    def get_interval(self) -> float:
        """Tick interval in seconds."""
        return self.tick_delay
        
    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "name": self.name,
            "status": "running" if self.running else "stopped",
            "mode": self.mode,
            "tick_count": self.tick_count,
            "config": self.config,
            "errors": self.errors,
        }
        
    def export_state(self) -> Dict[str, Any]:
        """Export current state for dashboard."""
        return {
            "name": self.name,
            "ticks": self.tick_count,
            "last_result": self.tick_results[-1] if self.tick_results else None,
        }
        
    def broadcast(self, data: Dict[str, Any]):
        """Broadcast data via callback."""
        if self._callback:
            self._callback(data)
