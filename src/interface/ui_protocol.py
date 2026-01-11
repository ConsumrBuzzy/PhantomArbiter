"""
UI Protocol
===========
Interface-agnostic rendering protocol for Web, TUI, and Console.

Implements "Headless UI" architecture where:
- HeartbeatDataCollector is the single source of truth
- All interfaces consume the same standardized payloads
- Math and data are identical across Web, TUI, Console

Components:
- EngineUIState: Standardized engine state for any display
- OpportunitySnapshot: Market opportunity for heat-map display
- RenderPayload: Complete UI state for a single frame
"""

from __future__ import annotations

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

class EngineType(Enum):
    """Types of trading engines."""
    ARB = "ARB"
    FUNDING = "FUNDING"
    SCALP = "SCALP"
    LST = "LST"
    SNIPER = "SNIPER"


class UrgencyLevel(Enum):
    """Visual urgency for UI elements."""
    IDLE = "IDLE"          # Gray - no activity
    NORMAL = "NORMAL"      # Green - healthy operation
    ATTENTION = "ATTENTION"  # Yellow - needs look
    WARNING = "WARNING"    # Orange - potential issue
    CRITICAL = "CRITICAL"  # Red - immediate action needed
    OPPORTUNITY = "OPPORTUNITY"  # Purple - paper opportunity detected


class TradingMode(Enum):
    """Trading mode affects UI colors."""
    PAPER = "PAPER"   # Purple theme
    LIVE = "LIVE"     # Red theme


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE UI STATE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EngineUIState:
    """
    Standardized engine state for any display.
    
    This is the "Universal Truth" - identical data for Web, TUI, Console.
    """
    
    # Identity
    engine_id: str
    engine_type: EngineType
    display_name: str
    
    # Status
    is_running: bool = False
    mode: TradingMode = TradingMode.PAPER
    urgency: UrgencyLevel = UrgencyLevel.IDLE
    status_text: str = "Idle"
    
    # Key metric (depends on engine type)
    primary_metric: float = 0.0
    primary_metric_label: str = ""
    primary_metric_unit: str = ""
    
    # Secondary metrics
    secondary_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Performance
    pnl_session: float = 0.0
    pnl_24h: float = 0.0
    trades_count: int = 0
    win_rate: float = 0.0
    
    # Timing
    uptime_seconds: float = 0.0
    last_signal_at: Optional[float] = None
    last_trade_at: Optional[float] = None
    
    # Alerts
    active_alerts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "engine_id": self.engine_id,
            "engine_type": self.engine_type.value,
            "display_name": self.display_name,
            "is_running": self.is_running,
            "mode": self.mode.value,
            "urgency": self.urgency.value,
            "status_text": self.status_text,
            "primary_metric": round(self.primary_metric, 4),
            "primary_metric_label": self.primary_metric_label,
            "primary_metric_unit": self.primary_metric_unit,
            "secondary_metrics": self.secondary_metrics,
            "pnl_session": round(self.pnl_session, 2),
            "pnl_24h": round(self.pnl_24h, 2),
            "trades_count": self.trades_count,
            "win_rate": round(self.win_rate, 1),
            "uptime_seconds": round(self.uptime_seconds, 0),
            "last_signal_at": self.last_signal_at,
            "last_trade_at": self.last_trade_at,
            "active_alerts": self.active_alerts,
        }
    
    @classmethod
    def for_arb_engine(
        cls,
        spread_pct: float,
        is_running: bool = False,
        mode: TradingMode = TradingMode.PAPER,
        pnl: float = 0.0,
        **kwargs,
    ) -> "EngineUIState":
        """Factory for Arb Engine UI state."""
        urgency = UrgencyLevel.IDLE
        if is_running:
            if spread_pct > 0.5:
                urgency = UrgencyLevel.OPPORTUNITY
            elif spread_pct > 0.2:
                urgency = UrgencyLevel.ATTENTION
            else:
                urgency = UrgencyLevel.NORMAL
        
        return cls(
            engine_id="arb",
            engine_type=EngineType.ARB,
            display_name="Arbitrage",
            is_running=is_running,
            mode=mode,
            urgency=urgency,
            status_text=f"Spread: {spread_pct:.2f}%" if is_running else "Idle",
            primary_metric=spread_pct,
            primary_metric_label="Best Spread",
            primary_metric_unit="%",
            pnl_session=pnl,
            **kwargs,
        )
    
    @classmethod
    def for_funding_engine(
        cls,
        net_apy: float,
        drift_pct: float = 0.0,
        is_running: bool = False,
        mode: TradingMode = TradingMode.PAPER,
        **kwargs,
    ) -> "EngineUIState":
        """Factory for Funding Engine UI state."""
        urgency = UrgencyLevel.IDLE
        if is_running:
            if drift_pct > 2.0:
                urgency = UrgencyLevel.WARNING
            elif net_apy > 10.0:
                urgency = UrgencyLevel.OPPORTUNITY
            else:
                urgency = UrgencyLevel.NORMAL
        
        return cls(
            engine_id="funding",
            engine_type=EngineType.FUNDING,
            display_name="Delta Neutral",
            is_running=is_running,
            mode=mode,
            urgency=urgency,
            status_text=f"APY: {net_apy:.1f}%" if is_running else "Idle",
            primary_metric=net_apy,
            primary_metric_label="Net APY",
            primary_metric_unit="%",
            secondary_metrics={"drift_pct": drift_pct},
            **kwargs,
        )
    
    @classmethod
    def for_scalp_engine(
        cls,
        active_positions: int = 0,
        unrealized_pnl: float = 0.0,
        is_running: bool = False,
        mode: TradingMode = TradingMode.PAPER,
        **kwargs,
    ) -> "EngineUIState":
        """Factory for Scalp Engine UI state."""
        urgency = UrgencyLevel.IDLE
        if is_running:
            if unrealized_pnl < -5.0:
                urgency = UrgencyLevel.WARNING
            elif active_positions > 0:
                urgency = UrgencyLevel.ATTENTION
            else:
                urgency = UrgencyLevel.NORMAL
        
        return cls(
            engine_id="scalp",
            engine_type=EngineType.SCALP,
            display_name="Scalper",
            is_running=is_running,
            mode=mode,
            urgency=urgency,
            status_text=f"{active_positions} Positions" if is_running else "Idle",
            primary_metric=float(active_positions),
            primary_metric_label="Positions",
            primary_metric_unit="",
            secondary_metrics={"unrealized_pnl": unrealized_pnl},
            **kwargs,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# OPPORTUNITY SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OpportunitySnapshot:
    """
    Market opportunity for heat-map display.
    
    Used in the Opportunity Matrix for at-a-glance monitoring.
    """
    
    opportunity_id: str
    source_engine: EngineType
    
    # Opportunity details
    asset_pair: str  # e.g., "SOL/USDC"
    opportunity_type: str  # "ARB", "FUNDING", "DEPEG"
    
    # Metrics
    profit_estimate_usd: float = 0.0
    profit_estimate_pct: float = 0.0
    confidence: float = 0.0  # 0-100
    
    # Risk
    risk_level: UrgencyLevel = UrgencyLevel.NORMAL
    time_sensitivity: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "URGENT"
    
    # Status
    is_actionable: bool = False
    requires_live_mode: bool = False
    
    # Timestamps
    detected_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "source_engine": self.source_engine.value,
            "asset_pair": self.asset_pair,
            "opportunity_type": self.opportunity_type,
            "profit_estimate_usd": round(self.profit_estimate_usd, 2),
            "profit_estimate_pct": round(self.profit_estimate_pct, 3),
            "confidence": round(self.confidence, 1),
            "risk_level": self.risk_level.value,
            "time_sensitivity": self.time_sensitivity,
            "is_actionable": self.is_actionable,
            "requires_live_mode": self.requires_live_mode,
            "detected_at": self.detected_at,
            "expires_at": self.expires_at,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# RENDER PAYLOAD
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RenderPayload:
    """
    Complete UI state for a single frame.
    
    Sent to all interfaces (Web, TUI, Console) simultaneously.
    """
    
    # Engine states
    engines: List[EngineUIState] = field(default_factory=list)
    
    # Active opportunities
    opportunities: List[OpportunitySnapshot] = field(default_factory=list)
    
    # Global state
    global_mode: TradingMode = TradingMode.PAPER
    is_armed: bool = False  # Master arm status
    
    # Wallet summary
    paper_equity_usd: float = 0.0
    live_equity_usd: float = 0.0
    
    # Market data
    sol_price: float = 0.0
    
    # Delta state (from monitoring)
    delta_status: str = "UNKNOWN"
    delta_drift_pct: float = 0.0
    
    # System health
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    latency_ms: float = 0.0
    
    # Frame metadata
    frame_id: int = 0
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON for WebSocket broadcast."""
        return {
            "engines": [e.to_dict() for e in self.engines],
            "opportunities": [o.to_dict() for o in self.opportunities],
            "global_mode": self.global_mode.value,
            "is_armed": self.is_armed,
            "paper_equity_usd": round(self.paper_equity_usd, 2),
            "live_equity_usd": round(self.live_equity_usd, 2),
            "sol_price": round(self.sol_price, 2),
            "delta_status": self.delta_status,
            "delta_drift_pct": round(self.delta_drift_pct, 3),
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_percent": round(self.memory_percent, 1),
            "latency_ms": round(self.latency_ms, 1),
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
        }
    
    def to_console_summary(self) -> str:
        """Format for console/TUI display."""
        lines = []
        
        mode_color = "🟣" if self.global_mode == TradingMode.PAPER else "🔴"
        lines.append(f"{mode_color} Mode: {self.global_mode.value} | SOL: ${self.sol_price:.2f}")
        lines.append(f"   Equity: ${self.paper_equity_usd:.2f} (Paper) / ${self.live_equity_usd:.2f} (Live)")
        lines.append("")
        
        for engine in self.engines:
            status_icon = self._urgency_icon(engine.urgency)
            running = "▶" if engine.is_running else "⏹"
            lines.append(
                f"  {running} {engine.display_name:<12} {status_icon} "
                f"{engine.primary_metric_label}: {engine.primary_metric:.2f}{engine.primary_metric_unit} "
                f"| PnL: ${engine.pnl_session:+.2f}"
            )
        
        if self.opportunities:
            lines.append("")
            lines.append("  📊 Opportunities:")
            for opp in self.opportunities[:3]:
                lines.append(f"     • {opp.asset_pair}: ${opp.profit_estimate_usd:.2f} ({opp.opportunity_type})")
        
        return "\n".join(lines)
    
    @staticmethod
    def _urgency_icon(urgency: UrgencyLevel) -> str:
        icons = {
            UrgencyLevel.IDLE: "⚪",
            UrgencyLevel.NORMAL: "🟢",
            UrgencyLevel.ATTENTION: "🟡",
            UrgencyLevel.WARNING: "🟠",
            UrgencyLevel.CRITICAL: "🔴",
            UrgencyLevel.OPPORTUNITY: "🟣",
        }
        return icons.get(urgency, "⚪")


# ═══════════════════════════════════════════════════════════════════════════════
# RENDER BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

class RenderBuilder:
    """
    Builds RenderPayload from SystemSnapshot.
    
    Transforms the raw data from HeartbeatDataCollector into
    display-ready state for all interfaces.
    """
    
    _frame_counter = 0
    
    @classmethod
    def from_snapshot(cls, snapshot: Any) -> RenderPayload:
        """
        Build RenderPayload from SystemSnapshot.
        
        Args:
            snapshot: SystemSnapshot from HeartbeatDataCollector
            
        Returns:
            RenderPayload ready for broadcast
        """
        cls._frame_counter += 1
        
        # Determine global mode
        global_mode = TradingMode.PAPER
        if hasattr(snapshot, 'global_mode') and snapshot.global_mode == "live":
            global_mode = TradingMode.LIVE
        
        # Build engine UI states
        engines = []
        if hasattr(snapshot, 'engines'):
            for name, engine in snapshot.engines.items():
                engine_state = cls._build_engine_state(name, engine, global_mode)
                if engine_state:
                    engines.append(engine_state)
        
        # Extract delta state
        delta_status = "UNKNOWN"
        delta_drift = 0.0
        if hasattr(snapshot, 'delta_state') and snapshot.delta_state:
            delta_status = getattr(snapshot.delta_state, 'status', 'UNKNOWN')
            if hasattr(delta_status, 'value'):
                delta_status = delta_status.value
            delta_drift = getattr(snapshot.delta_state, 'drift_pct', 0.0)
        
        # Extract metrics
        cpu = 0.0
        memory = 0.0
        if hasattr(snapshot, 'metrics'):
            cpu = snapshot.metrics.cpu_percent
            memory = snapshot.metrics.memory_percent
        
        return RenderPayload(
            engines=engines,
            opportunities=[],  # TODO: Build from arb scanner
            global_mode=global_mode,
            paper_equity_usd=snapshot.paper_wallet.equity if hasattr(snapshot, 'paper_wallet') else 0.0,
            live_equity_usd=snapshot.live_wallet.equity if hasattr(snapshot, 'live_wallet') else 0.0,
            sol_price=getattr(snapshot, 'sol_price', 0.0),
            delta_status=str(delta_status),
            delta_drift_pct=delta_drift,
            cpu_percent=cpu,
            memory_percent=memory,
            latency_ms=getattr(snapshot, 'collector_latency_ms', 0.0),
            frame_id=cls._frame_counter,
        )
    
    @classmethod
    def _build_engine_state(
        cls,
        name: str,
        engine: Any,
        mode: TradingMode,
    ) -> Optional[EngineUIState]:
        """Build EngineUIState from engine snapshot."""
        
        is_running = getattr(engine, 'status', '') == 'running'
        pnl = getattr(engine, 'pnl', 0.0)
        uptime = getattr(engine, 'uptime', 0.0)
        
        # Map engine name to type and factory
        name_lower = name.lower()
        
        if 'arb' in name_lower:
            spread = getattr(engine, 'config', {}).get('best_spread', 0.0)
            return EngineUIState.for_arb_engine(
                spread_pct=spread,
                is_running=is_running,
                mode=mode,
                pnl=pnl,
                uptime_seconds=uptime,
            )
        
        elif 'funding' in name_lower or 'neutral' in name_lower:
            apy = getattr(engine, 'config', {}).get('net_apy', 0.0)
            return EngineUIState.for_funding_engine(
                net_apy=apy,
                is_running=is_running,
                mode=mode,
                pnl_session=pnl,
                uptime_seconds=uptime,
            )
        
        elif 'scalp' in name_lower:
            positions = getattr(engine, 'config', {}).get('active_positions', 0)
            return EngineUIState.for_scalp_engine(
                active_positions=positions,
                is_running=is_running,
                mode=mode,
                pnl_session=pnl,
                uptime_seconds=uptime,
            )
        
        # Generic fallback
        return EngineUIState(
            engine_id=name,
            engine_type=EngineType.ARB,
            display_name=name,
            is_running=is_running,
            mode=mode,
            pnl_session=pnl,
            uptime_seconds=uptime,
        )
