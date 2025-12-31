"""
Base Console UI
===============
Core primitives for ASCII dashboards:
- ANSI Color Codes
- Box Drawing Characters
- Screen Control (Clear, Cursor)
- Text Formatting (Center, Pad)
"""

import os


class BaseConsoleUI:
    """
    Base class for rich console user interfaces.
    """

    # ANSI Colors
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Foreground colors
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Status colors mapping
    STATUS_COLORS = {
        "READY": GREEN,
        "MONITOR": BLUE,
        "WAIT": GRAY,
        "EXECUTING": YELLOW,
        "PROFIT": GREEN,
        "LOSS": RED,
        "LIQ": RED,
        "SLIP": MAGENTA,
    }

    # Box drawing characters (Double Line / Single Line styles)
    BOX = {
        "tl": "╔",
        "tr": "╗",
        "bl": "╚",
        "br": "╝",
        "h": "═",
        "v": "║",
        "lm": "╠",
        "rm": "╣",
        "tm": "╦",
        "bm": "╩",
        "x": "╬",
        "hl": "─",
        "vl": "│",
        "t_down": "qa",  # TODO: Fix mapping if needed
    }

    def __init__(self):
        pass

    def clear_screen(self):
        """Clear terminal screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def center_text(self, text: str, width: int) -> str:
        """Center text within width, ignoring ANSI codes for length."""
        text_len = self._visible_length(text)
        padding = max(0, (width - text_len) // 2)
        return " " * padding + text

    def pad_text(self, text: str, width: int, align: str = "<") -> str:
        """
        Pad text to width, accounting for ANSI codes.
        Align: '<' (left), '>' (right), '^' (center)
        """
        visible_len = self._visible_length(text)
        padding = max(0, width - visible_len)

        if align == "<":
            return text + " " * padding
        elif align == ">":
            return " " * padding + text
        elif align == "^":
            left = padding // 2
            right = padding - left
            return " " * left + text + " " * right
        return text

    def make_box_line(self, left: str, fill: str, right: str, width: int) -> str:
        """Create a box line (e.g. ╔══════╗)."""
        return left + fill * (width - 2) + right

    def _visible_length(self, text: str) -> int:
        """Calculate length of text excluding ANSI codes."""
        # Simple strip of common codes
        clean = text
        for code in [
            self.RESET,
            self.BOLD,
            self.DIM,
            self.UNDERLINE,
            self.RED,
            self.GREEN,
            self.YELLOW,
            self.BLUE,
            self.MAGENTA,
            self.CYAN,
            self.WHITE,
            self.GRAY,
        ]:
            clean = clean.replace(code, "")
        return len(clean)

    def color_status(self, status: str) -> str:
        """Apply color to a status string based on keywords."""
        for key, color in self.STATUS_COLORS.items():
            if key in status.upper():
                return f"{color}{status}{self.RESET}"
        return f"{self.WHITE}{status}{self.RESET}"
