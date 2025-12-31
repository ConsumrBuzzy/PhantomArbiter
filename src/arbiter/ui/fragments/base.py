"""
Base Fragment Definition
========================
Phase 17: Modular Industrialization

Abstract base class for all UI fragments in the modular dashboard.
Each fragment is responsible for rendering a specific part of the UI
based on the application state.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseFragment(ABC):
    """
    Abstract base class for Dashboard UI Fragments.
    """

    def __init__(self, name: str, priority: int = 10):
        self.name = name
        self.priority = priority  # Lower is higher visual priority? Or Higher is higher? Let's say Higher = Higher up.

    @abstractmethod
    def render(self, state: Any) -> Any:
        """
        Render the fragment content based on the current app state.

        Args:
            state: The global application state object (PulsedApp).

        Returns:
            A Rich Renderable (Panel, Table, Layout, etc.)
        """
        pass

    def get_layout_name(self) -> str:
        """Return the target slot name in the grid (e.g., 'header', 'left', 'right')."""
        return "main"
