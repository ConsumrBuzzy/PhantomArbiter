"""
Dashboard Fragment Registry
===========================
Phase 17: Modular Industrialization

Managing the lifecycle and layout of UI fragments.
Allows dynamic toggling of panels based on Active Strategy.
"""

from typing import Dict, List, Any
from src.arbiter.ui.fragments.base import BaseFragment


class DashboardRegistry:
    """
    Central registry for managing UI fragments.

    Responsibilities:
    1. Register/Unregister fragments
    2. Group fragments by slot (left, right, header)
    3. Build the final Rich Layout
    """

    def __init__(self):
        self._fragments: Dict[str, BaseFragment] = {}
        # Layouts mapping: slot_name -> list of fragments
        self._slots: Dict[str, List[BaseFragment]] = {
            "header": [],
            "left": [],
            "right": [],
            "footer": [],
        }

    def register(self, slot: str, fragment: BaseFragment):
        """Register a fragment to a specific UI slot."""
        if slot not in self._slots:
            self._slots[slot] = []

        # Avoid duplicates
        if any(f.name == fragment.name for f in self._slots[slot]):
            return

        self._slots[slot].append(fragment)
        self._fragments[fragment.name] = fragment

        # Sort by priority (descending)
        self._slots[slot].sort(key=lambda x: x.priority, reverse=True)

    def clear_slot(self, slot: str):
        """Remove all fragments from a slot."""
        if slot in self._slots:
            # Also remove from main map
            for f in self._slots[slot]:
                if f.name in self._fragments:
                    del self._fragments[f.name]
            self._slots[slot] = []

    def get_fragment(self, name: str) -> BaseFragment:
        return self._fragments.get(name)

    def render_slot(self, slot: str, state: Any) -> Any:
        """
        Render all fragments in a slot.
        For simplicity, returns the first active one, or a split layout if possible.
        Actually, let's just return the top priority Renderable for now,
        or we can return a Layout splitting them.
        """
        fragments = self._slots.get(slot, [])
        if not fragments:
            return None

        # Simple strategy: First fragment takes the slot (for now)
        # TODO: Implement multi-fragment split view in Phase 17.5
        return fragments[0].render(state)


# Global Registry Instance
registry = DashboardRegistry()
