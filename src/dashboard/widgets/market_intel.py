"""
Market Intel Widget - Visual Layer Integration
===============================================
Displays real-time market intelligence from SignalBus.

Subscribes to MARKET_INTEL signals and renders:
- Pressure gauge (bullish/bearish/volatile)
- Heat indicator
- Regime badge
- Whiff count
"""

from typing import Optional, Dict
from textual.widgets import Static
from textual.reactive import reactive

from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.shared.system.logging import Logger


class MarketIntelWidget(Static):
    """
    TUI widget displaying market intelligence.
    
    Subscribes to MARKET_INTEL signals from MarketSignalHub.
    """
    
    # Reactive attributes for auto-refresh
    heat: reactive[float] = reactive(0.0)
    regime: reactive[str] = reactive("UNKNOWN")
    whiff_count: reactive[int] = reactive(0)
    
    def __init__(self, mint: str = "SOL", **kwargs):
        super().__init__(**kwargs)
        self.mint = mint
        self._pressure = {"bullish": 0.0, "bearish": 0.0, "volatile": 0.0}
        
    def on_mount(self) -> None:
        """Subscribe to signals when widget mounts."""
        signal_bus.subscribe(SignalType.MARKET_INTEL, self._on_market_intel)
        Logger.debug(f"📊 MarketIntelWidget subscribed for {self.mint}")
        
        # Start refresh timer
        self.set_interval(2.0, self._refresh_display)
    
    def _on_market_intel(self, signal: Signal) -> None:
        """Handle incoming MARKET_INTEL signal."""
        if signal.data.get("mint") == self.mint or self.mint == "*":
            self._pressure = signal.data.get("pressure", self._pressure)
            self.heat = signal.data.get("heat", 0.0)
            self.regime = signal.data.get("regime", "UNKNOWN")
            self.whiff_count = signal.data.get("whiff_count", 0)
    
    def _refresh_display(self) -> None:
        """Refresh the display."""
        self.refresh()
    
    def render(self) -> str:
        """Render the widget content."""
        # Heat bar
        heat_bar = self._render_heat_bar()
        
        # Pressure indicators
        bull = self._pressure.get("bullish", 0.0)
        bear = self._pressure.get("bearish", 0.0)
        vol = self._pressure.get("volatile", 0.0)
        
        # Regime emoji
        regime_emoji = {
            "BULL": "🟢",
            "BEAR": "🔴", 
            "CHOP": "🟡",
            "UNKNOWN": "⚪",
        }.get(self.regime, "⚪")
        
        return f"""[bold]📡 MARKET INTEL[/bold]
{regime_emoji} Regime: {self.regime}
🔥 Heat: {heat_bar} {self.heat:.0%}
📈 Bull: {self._bar(bull)} {bull:.0%}
📉 Bear: {self._bar(bear)} {bear:.0%}
⚡ Vol:  {self._bar(vol)} {vol:.0%}
👃 Whiffs: {self.whiff_count}"""
    
    def _render_heat_bar(self) -> str:
        """Render heat as a progress bar."""
        filled = int(self.heat * 10)
        empty = 10 - filled
        return f"[{'█' * filled}{'░' * empty}]"
    
    def _bar(self, value: float) -> str:
        """Render a mini progress bar."""
        filled = int(value * 5)
        return "▓" * filled + "░" * (5 - filled)


class MarketIntelPanel(Static):
    """
    Full panel showing market intel for multiple mints.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._intel_cache: Dict[str, dict] = {}
    
    def on_mount(self) -> None:
        """Subscribe to all MARKET_INTEL signals."""
        signal_bus.subscribe(SignalType.MARKET_INTEL, self._on_intel)
        self.set_interval(2.0, self.refresh)
    
    def _on_intel(self, signal: Signal) -> None:
        """Cache incoming intel."""
        mint = signal.data.get("mint")
        if mint:
            self._intel_cache[mint] = signal.data
    
    def render(self) -> str:
        """Render multi-mint panel."""
        if not self._intel_cache:
            return "[dim]Waiting for market intel...[/dim]"
        
        lines = ["[bold]📡 MARKET INTEL PANEL[/bold]", ""]
        
        for mint, data in list(self._intel_cache.items())[:5]:
            heat = data.get("heat", 0.0)
            regime = data.get("regime", "?")
            whiffs = data.get("whiff_count", 0)
            
            heat_emoji = "🔥" if heat > 0.5 else "❄️" if heat < 0.2 else "🌡️"
            
            lines.append(f"{mint[:8]}.. {heat_emoji}{heat:.0%} [{regime}] 👃{whiffs}")
        
        return "\n".join(lines)
