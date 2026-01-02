"""
Galaxy State Manager - Maintains current Galaxy state.

Allows new browser clients to immediately see the current state
without waiting for new events from Core.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Optional
from galaxy.models import VisualObject


class GalaxyState:
    """
    Stateful mirror of the Galaxy.
    Maintains current visual objects for state recovery.
    """
    
    # Maximum number of objects to retain
    MAX_OBJECTS = 5000
    
    def __init__(self) -> None:
        self._objects: Dict[str, VisualObject] = {}
        self._lock = asyncio.Lock()
    
    async def update(self, obj: VisualObject) -> None:
        """Update or add a visual object."""
        async with self._lock:
            self._objects[obj.id] = obj
            
            # Prune if over limit (remove oldest)
            if len(self._objects) > self.MAX_OBJECTS:
                # Keep most recent half
                keys = list(self._objects.keys())
                for key in keys[:len(keys) // 2]:
                    del self._objects[key]
    
    async def update_batch(self, objects: list[VisualObject]) -> int:
        """Update multiple objects at once."""
        async with self._lock:
            for obj in objects:
                self._objects[obj.id] = obj
            return len(objects)
    
    async def get_all(self) -> list[VisualObject]:
        """Get all current visual objects."""
        async with self._lock:
            return list(self._objects.values())
    
    async def get(self, object_id: str) -> Optional[VisualObject]:
        """Get a specific visual object by ID."""
        async with self._lock:
            return self._objects.get(object_id)
    
    async def remove(self, object_id: str) -> bool:
        """Remove an object from state."""
        async with self._lock:
            if object_id in self._objects:
                del self._objects[object_id]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all state."""
        async with self._lock:
            self._objects.clear()
    
    @property
    def count(self) -> int:
        """Number of objects in state."""
        return len(self._objects)


# Global instance
galaxy_state = GalaxyState()
