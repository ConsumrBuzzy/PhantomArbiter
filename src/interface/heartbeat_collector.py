"""
Heartbeat Data Collector
========================
SRP-compliant data aggregation service for the Dashboard.

Extracts all data collection logic from DashboardServer into a
dedicated, testable component.

The "Heart" of the system - pumps a clean SystemSnapshot at 1Hz.
"""

import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════════
# DATA SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AssetBalance:
    """Single asset balance with valuation."""
    symbol: str
    amount: float
    price: float = 0.0
    value_usd: float = 0.0
    
    def __post_init__(self):
        if self.value_usd == 0 and self.price > 0:
            self.value_usd = self.amount * self.price


@dataclass
class WalletSnapshot:
    """Snapshot of a wallet's balances."""
    
    wallet_type: str  # "PAPER", "LIVE"
    assets: Dict[str, AssetBalance] = field(default_factory=dict)
    equity: float = 0.0
    sol_balance: float = 0.0
    drift_equity: float = 0.0  # For live wallet with Drift perps
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dashboard-friendly dict."""
        return {
            "type": self.wallet_type,
            "assets": {
                sym: {"amount": a.amount, "value_usd": a.value_usd, "price": a.price}
                for sym, a in self.assets.items()
            },
            "equity": self.equity,
            "sol_balance": self.sol_balance,
            "drift_equity": self.drift_equity,
        }


@dataclass
class EngineSnapshot:
    """Status snapshot for a single engine."""
    name: str
    status: str  # "running", "stopped", "error"
    mode: str  # "paper", "live"
    uptime: float = 0.0
    pnl: float = 0.0
    tick_count: int = 0
    last_signal: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """System resource metrics."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "disk_percent": self.disk_percent,
        }


@dataclass
class WatchlistEntry:
    """Token watchlist entry for scalper."""
    symbol: str
    price: float = 0.0
    change_5m: float = 0.0
    change_1h: float = 0.0
    change_24h: float = 0.0
    volume_24h: float = 0.0
    spread_pct: float = 0.0


@dataclass
class SystemSnapshot:
    """
    Complete system state snapshot.
    
    This is the "Pulse" - a single immutable object containing
    everything the Dashboard needs to render the UI.
    """
    
    # Wallets
    paper_wallet: WalletSnapshot
    live_wallet: WalletSnapshot
    
    # Engines
    engines: Dict[str, EngineSnapshot] = field(default_factory=dict)
    
    # Market data
    sol_price: float = 0.0
    watchlist: List[WatchlistEntry] = field(default_factory=list)
    
    # System
    metrics: SystemMetrics = field(default_factory=SystemMetrics)
    global_mode: str = "paper"
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    collector_latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dashboard-friendly dict for SYSTEM_STATS packet."""
        return {
            "paper_wallet": self.paper_wallet.to_dict(),
            "live_wallet": self.live_wallet.to_dict(),
            "wallet": self.paper_wallet.to_dict(),  # Legacy compat
            "engines": {
                name: {
                    "status": e.status,
                    "mode": e.mode,
                    "uptime": e.uptime,
                    "pnl": e.pnl,
                    "config": e.config,
                }
                for name, e in self.engines.items()
            },
            "sol_price": self.sol_price,
            "watchlist": [
                {
                    "symbol": w.symbol,
                    "price": w.price,
                    "change_5m": w.change_5m,
                    "change_1h": w.change_1h,
                    "change_24h": w.change_24h,
                    "volume": w.volume_24h,
                    "spread": w.spread_pct,
                }
                for w in self.watchlist
            ],
            "metrics": self.metrics.to_dict(),
            "mode": self.global_mode,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# DATA COLLECTOR
# ═══════════════════════════════════════════════════════════════════════════════

class HeartbeatDataCollector:
    """
    Centralized data aggregation service.
    
    Collects data from:
    - VaultRegistry (paper wallets)
    - WalletManager (live balances)
    - DriftAdapter (perp equity)
    - EngineManager (engine statuses)
    - TokenWatchlist (market data)
    - System metrics (CPU, RAM)
    
    Returns a single immutable SystemSnapshot.
    
    Usage:
        collector = HeartbeatDataCollector()
        snapshot = await collector.collect()
        await broadcast(snapshot.to_dict())
    """
    
    # Fallback prices when feeds unavailable
    FALLBACK_PRICES = {
        "SOL": 150.0,
        "USDC": 1.0,
        "JTO": 2.5,
        "JUP": 0.8,
        "BONK": 0.00001,
        "WIF": 1.2,
    }
    
    def __init__(self):
        self._wallet_mgr = None
        self._drift_adapter = None
        self._price_feed = None
        self._last_snapshot: Optional[SystemSnapshot] = None
        self._collection_count = 0
        
    async def collect(self, global_mode: str = "paper") -> SystemSnapshot:
        """
        Collect complete system snapshot.
        
        Args:
            global_mode: Current trading mode ("paper" or "live")
            
        Returns:
            Immutable SystemSnapshot with all system state
        """
        start_time = time.time()
        
        # Collect in parallel where possible
        paper_wallet, live_wallet, engines, sol_price = await asyncio.gather(
            self._collect_paper_wallet(),
            self._collect_live_wallet(),
            self._collect_engine_status(),
            self._get_sol_price(),
        )
        
        # These are synchronous/fast
        metrics = self._collect_system_metrics()
        watchlist = await self._collect_watchlist()
        
        latency_ms = (time.time() - start_time) * 1000
        
        snapshot = SystemSnapshot(
            paper_wallet=paper_wallet,
            live_wallet=live_wallet,
            engines=engines,
            sol_price=sol_price,
            watchlist=watchlist,
            metrics=metrics,
            global_mode=global_mode,
            collector_latency_ms=latency_ms,
        )
        
        self._last_snapshot = snapshot
        self._collection_count += 1
        
        return snapshot
    
    async def _collect_paper_wallet(self) -> WalletSnapshot:
        """Collect paper wallet balances with price enrichment."""
        try:
            from src.shared.state.paper_wallet import pw
            pw.reload()
            
            assets = {}
            total_equity = 0.0
            
            for symbol, balance in pw.balances.items():
                price = await self._get_asset_price(symbol)
                value = balance * price
                total_equity += value
                
                assets[symbol] = AssetBalance(
                    symbol=symbol,
                    amount=balance,
                    price=price,
                    value_usd=value,
                )
            
            return WalletSnapshot(
                wallet_type="PAPER",
                assets=assets,
                equity=total_equity,
                sol_balance=pw.balances.get("SOL", 0.0),
            )
            
        except Exception as e:
            Logger.debug(f"Paper wallet collection error: {e}")
            return WalletSnapshot(wallet_type="PAPER (error)")
    
    async def _collect_live_wallet(self) -> WalletSnapshot:
        """Collect live Solana wallet balances."""
        try:
            if not self._wallet_mgr:
                from src.drivers.wallet_manager import WalletManager
                self._wallet_mgr = WalletManager()
            
            live_data = self._wallet_mgr.get_current_live_usd_balance()
            
            assets = {}
            for asset_info in live_data.get("assets", []):
                sym = asset_info.get("symbol", "UNKNOWN")
                amt = asset_info.get("amount", 0)
                val = asset_info.get("usd_value", 0)
                price = val / max(amt, 0.0001) if amt else 0
                
                assets[sym] = AssetBalance(
                    symbol=sym,
                    amount=amt,
                    price=price,
                    value_usd=val,
                )
            
            # Ensure breakdown items are included
            breakdown = live_data.get("breakdown", {})
            if "SOL" in breakdown and "SOL" not in assets:
                sol_bal = breakdown["SOL"]
                sol_price = await self._get_asset_price("SOL")
                assets["SOL"] = AssetBalance("SOL", sol_bal, sol_price)
            if "USDC" in breakdown and "USDC" not in assets:
                assets["USDC"] = AssetBalance("USDC", breakdown["USDC"], 1.0)
            
            # Drift perp equity
            drift_equity = await self._collect_drift_equity()
            if drift_equity > 0:
                assets["DRIFT"] = AssetBalance("DRIFT", drift_equity, 1.0, drift_equity)
            
            total_equity = live_data.get("total_usd", 0.0) + drift_equity
            
            return WalletSnapshot(
                wallet_type="LIVE",
                assets=assets,
                equity=total_equity,
                sol_balance=breakdown.get("SOL", 0.0),
                drift_equity=drift_equity,
            )
            
        except Exception as e:
            Logger.debug(f"Live wallet collection error: {e}")
            return WalletSnapshot(wallet_type="LIVE (error)")
    
    async def _collect_drift_equity(self) -> float:
        """Collect Drift perp account equity."""
        try:
            if not self._drift_adapter:
                from src.delta_neutral.drift_order_builder import DriftAdapter
                self._drift_adapter = DriftAdapter("mainnet")
                if self._wallet_mgr:
                    self._drift_adapter.set_wallet(self._wallet_mgr)
            
            return self._drift_adapter.get_user_equity()
            
        except Exception as e:
            Logger.debug(f"Drift equity collection error: {e}")
            return 0.0
    
    async def _collect_engine_status(self) -> Dict[str, EngineSnapshot]:
        """Collect status from all engines."""
        try:
            from src.interface.engine_manager import engine_manager
            
            status_dict = await engine_manager.get_status()
            
            engines = {}
            for name, status in status_dict.items():
                engines[name] = EngineSnapshot(
                    name=name,
                    status=status.get("status", "unknown"),
                    mode=status.get("mode", "paper"),
                    uptime=status.get("uptime", 0.0),
                    pnl=status.get("pnl", 0.0),
                    config=status.get("config", {}),
                )
            
            return engines
            
        except Exception as e:
            Logger.debug(f"Engine status collection error: {e}")
            return {}
    
    async def _collect_watchlist(self) -> List[WatchlistEntry]:
        """Collect token watchlist data."""
        try:
            from src.shared.feeds.token_watchlist import get_token_watchlist
            
            wl = get_token_watchlist()
            entries = []
            
            for p in wl.prices.values():
                entries.append(WatchlistEntry(
                    symbol=p.symbol,
                    price=p.prices.get("raydium", p.best_ask),
                    change_5m=p.change_5m,
                    change_1h=p.change_1h,
                    change_24h=p.change_24h,
                    volume_24h=p.volume_24h,
                    spread_pct=p.spread_pct,
                ))
            
            return entries
            
        except Exception as e:
            Logger.debug(f"Watchlist collection error: {e}")
            return []
    
    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system resource metrics."""
        try:
            import psutil
            
            try:
                disk_pct = psutil.disk_usage('C:').percent
            except Exception:
                disk_pct = 0.0
            
            return SystemMetrics(
                cpu_percent=psutil.cpu_percent(interval=None),
                memory_percent=psutil.virtual_memory().percent,
                disk_percent=disk_pct,
            )
            
        except Exception as e:
            Logger.debug(f"Metrics collection error: {e}")
            return SystemMetrics()
    
    async def _get_sol_price(self) -> float:
        """Get current SOL price."""
        return await self._get_asset_price("SOL")
    
    async def _get_asset_price(self, symbol: str) -> float:
        """Get price for an asset, with fallback."""
        if symbol == "USDC":
            return 1.0
        
        try:
            if not self._price_feed:
                from src.shared.feeds.jupiter_feed import JupiterFeed
                self._price_feed = JupiterFeed()
            
            quote = self._price_feed.get_spot_price(symbol, "USDC")
            if quote and quote.price > 0:
                return quote.price
                
        except Exception:
            pass
        
        return self.FALLBACK_PRICES.get(symbol, 0.0)
    
    def get_last_snapshot(self) -> Optional[SystemSnapshot]:
        """Get the most recent snapshot (for caching)."""
        return self._last_snapshot
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collector statistics."""
        return {
            "collection_count": self._collection_count,
            "last_latency_ms": self._last_snapshot.collector_latency_ms if self._last_snapshot else 0,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_collector_instance: Optional[HeartbeatDataCollector] = None


def get_heartbeat_collector() -> HeartbeatDataCollector:
    """Get or create the global HeartbeatDataCollector instance."""
    global _collector_instance
    
    if _collector_instance is None:
        _collector_instance = HeartbeatDataCollector()
    
    return _collector_instance


def reset_heartbeat_collector():
    """Reset the global collector (for testing)."""
    global _collector_instance
    _collector_instance = None
