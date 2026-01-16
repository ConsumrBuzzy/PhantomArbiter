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
from src.drift_engine.core.types import DriftMarginMetrics
from src.drift_engine.core.margin import DriftMarginMonitor


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
class CEXWalletSnapshot:
    """Snapshot of CEX (Coinbase) wallet balance."""
    
    exchange: str = "coinbase"
    withdrawable_usdc: float = 0.0
    total_value_usd: float = 0.0
    pending_withdrawals: int = 0
    bridge_state: str = "IDLE"
    is_configured: bool = False
    last_update: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exchange": self.exchange,
            "withdrawable_usdc": self.withdrawable_usdc,
            "total_value_usd": self.total_value_usd,
            "pending_withdrawals": self.pending_withdrawals,
            "bridge_state": self.bridge_state,
            "is_configured": self.is_configured,
            "last_update": self.last_update,
        }


@dataclass
class UnifiedBalance:
    """
    Single source of truth for all wallet balances.
    
    Aggregates Coinbase, Phantom, and Drift into one view.
    This is what the UnifiedVaultController consumes.
    """
    # Aggregates
    net_worth_usd: float = 0.0
    deployed_usd: float = 0.0
    idle_usd: float = 0.0
    
    # Venue Breakdown
    coinbase: Dict[str, Any] = field(default_factory=lambda: {
        "usdc": 0.0, "usd": 0.0, "sol": 0.0, "total": 0.0, "status": "disconnected"
    })
    phantom: Dict[str, Any] = field(default_factory=lambda: {
        "sol": 0.0, "usdc": 0.0, "total": 0.0, "token_count": 0, "status": "disconnected"
    })
    drift: Dict[str, Any] = field(default_factory=lambda: {
        "equity": 0.0, "pnl": 0.0, "leverage": 0.0, "status": "disconnected"
    })
    
    # Bridge State
    bridge: Dict[str, Any] = field(default_factory=lambda: {
        "available": False, "max_amount": 0.0, "cooldown_remaining": 0
    })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "net_worth_usd": self.net_worth_usd,
            "deployed_usd": self.deployed_usd,
            "idle_usd": self.idle_usd,
            "coinbase": self.coinbase,
            "phantom": self.phantom,
            "drift": self.drift,
            "bridge": self.bridge,
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


# DriftMarginMetrics moved to core.types


@dataclass
class DriftMarketInfo:
    """Drift Market Data (Funding & Stats)."""
    markets: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "markets": self.markets,
            "stats": self.stats
        }


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
    cex_wallet: CEXWalletSnapshot = field(default_factory=CEXWalletSnapshot)
    
    # Unified Balance (single source of truth)
    unified_balance: UnifiedBalance = field(default_factory=UnifiedBalance)
    
    # Engines
    engines: Dict[str, EngineSnapshot] = field(default_factory=dict)
    
    # Market data
    sol_price: float = 0.0
    major_prices: Dict[str, float] = field(default_factory=dict)  # BTC, ETH, SOL, etc.
    watchlist: List[WatchlistEntry] = field(default_factory=list)
    
    # Delta neutrality (hedge status)
    delta_state: Optional[Any] = None  # DeltaState from monitoring module
    
    # Drift margin metrics (Risk-First Health Gauge)
    drift_margin: DriftMarginMetrics = field(default_factory=DriftMarginMetrics)
    
    # Drift Market Data (Funding Opportunities)
    drift_markets: DriftMarketInfo = field(default_factory=DriftMarketInfo)
    
    # Engine Vaults (Hybrid Allocations)
    vaults: Optional[Dict[str, Any]] = None
    
    # System
    metrics: SystemMetrics = field(default_factory=SystemMetrics)
    global_mode: str = "paper"
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    collector_latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dashboard-friendly dict for SYSTEM_STATS packet."""
        result = {
            "paper_wallet": self.paper_wallet.to_dict(),
            "live_wallet": self.live_wallet.to_dict(),
            "cex_wallet": self.cex_wallet.to_dict(),
            "unified_balance": self.unified_balance.to_dict(),
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
            "sol_price": self.sol_price,
            "major_prices": self.major_prices,
            "vaults": self.vaults,
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
        
        # Add delta state if available
        if self.delta_state and hasattr(self.delta_state, 'to_dict'):
            result["delta_state"] = self.delta_state.to_dict()
        
        # Add Drift margin metrics (Risk-First Health Gauge)
        result["drift_margin"] = self.drift_margin.to_dict()
        
        # Add Drift Market Data
        # Note: We send this as a separate packet usually, but embedding it here
        # ensures the initial snapshot has it.
        result["drift_markets"] = self.drift_markets.to_dict()
        
        return result


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
        self._drift_monitor = DriftMarginMonitor()
        
        self._price_feed = None
        self._delta_calculator = None
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
        paper_wallet, live_wallet, cex_wallet, engines, sol_price, delta_state, drift_margin, drift_markets, _ = await asyncio.gather(
            self._collect_paper_wallet(),
            self._collect_live_wallet(),
            self._collect_cex_wallet(),
            self._collect_engine_status(),
            self._get_sol_price(),
            self._collect_delta_state(),
            self._collect_drift_margin_metrics(),
            self._collect_drift_markets(),
            self._sync_engine_vaults(),
        )
        
        # These are synchronous/fast
        metrics = self._collect_system_metrics()
        watchlist = await self._collect_watchlist()
        major_prices = await self._get_major_prices(sol_price)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # ─────────────────────────────────────────────────────────────────────
        # BUILD UNIFIED BALANCE (Single Source of Truth)
        # ─────────────────────────────────────────────────────────────────────
        
        # Calculate net worth across all venues
        # Calculate net worth across all venues
        # Note: phantom_total (live_wallet.equity) ALREADY includes drift_equity
        coinbase_total = cex_wallet.total_value_usd
        phantom_total = live_wallet.equity
        drift_total = live_wallet.drift_equity
        net_worth = coinbase_total + phantom_total  # Do not add drift_total again
        
        # Determine connection statuses
        coinbase_status = "connected" if cex_wallet.is_configured else "disconnected"
        phantom_status = "connected" if phantom_total > 0 or len(live_wallet.assets) > 0 else "disconnected"
        drift_status = "connected" if drift_total > 0 else "disconnected"
        
        # Bridge availability (min $5 required)
        bridge_available = cex_wallet.withdrawable_usdc >= 5.0
        bridge_max = max(0, cex_wallet.withdrawable_usdc - 1.0)  # Leave $1 dust floor
        
        # Deployed vs Idle Logic
        # Get active deployment from DriftAdapter (parsed from user account)
        deployed = await self._collect_drift_active_capital()
        idle = net_worth - deployed
        
        # Debug Log for Unified Balance Construction
        Logger.info(f"[Heartbeat] NetWorth Inputs -> CEX: ${coinbase_total:.2f}, Phantom: ${phantom_total:.2f}, Drift: ${drift_total:.2f}")

        unified_balance = UnifiedBalance(
            net_worth_usd=net_worth,
            deployed_usd=deployed,
            idle_usd=idle,
            coinbase={
                "usdc": cex_wallet.withdrawable_usdc,
                "usd": 0.0,  # Could be enhanced to track USD separately
                "sol": 0.0,
                "total": coinbase_total,
                "status": coinbase_status,
            },
            phantom={
                "sol": live_wallet.sol_balance,
                "usdc": live_wallet.assets.get("USDC", AssetBalance("USDC", 0)).amount,
                "total": phantom_total - drift_total,  # Exclude Drift for non-overlapped display
                "token_count": len(live_wallet.assets),
                "status": phantom_status,
            },
            drift={
                "equity": drift_total,
                "pnl": 0.0,  # Could be enhanced with proper PnL tracking
                "leverage": 0.0,  # Could be enhanced with leverage calculation
                "status": drift_status,
            },
            bridge={
                "available": bridge_available,
                "max_amount": bridge_max,
                "cooldown_remaining": 0,
            },
        )
        
        snapshot = SystemSnapshot(
            paper_wallet=paper_wallet,
            live_wallet=live_wallet,
            cex_wallet=cex_wallet,
            unified_balance=unified_balance,
            engines=engines,
            sol_price=sol_price,
            major_prices=major_prices,
            watchlist=watchlist,
            delta_state=delta_state,
            drift_margin=drift_margin,
            drift_markets=drift_markets,
            vaults=self._collect_engine_vaults(sol_price),
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
    
    async def _collect_cex_wallet(self) -> CEXWalletSnapshot:
        """Collect Coinbase CEX wallet balance."""
        try:
            from src.drivers.coinbase_driver import get_coinbase_driver
            from src.drivers.bridge_manager import get_bridge_manager
            
            driver = get_coinbase_driver()
            
            if not driver.is_configured:
                return CEXWalletSnapshot(is_configured=False)
            
            # Get live balances (USDC, USD, SOL)
            real_balances = await driver.sync_real_balances()
            
            # Use 'usdc' as withdrawable (for bridge logic)
            withdrawable = real_balances.get("usdc", 0.0)
            
            # Use 'total_usd' for total equity view
            total_value = real_balances.get("total_usd", 0.0)
            
            # Get bridge state
            try:
                manager = get_bridge_manager()
                bridge_state = manager.state.value
            except Exception:
                bridge_state = "UNKNOWN"
            
            return CEXWalletSnapshot(
                exchange="coinbase",
                withdrawable_usdc=withdrawable,
                total_value_usd=total_value,
                bridge_state=bridge_state,
                is_configured=True,
                last_update=time.time(),
            )
            
        except Exception as e:
            Logger.debug(f"CEX wallet collection error: {e}")
            return CEXWalletSnapshot(is_configured=False)
    
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
    
    async def _collect_drift_active_capital(self) -> float:
        """Collect deployed capital (active margin) from Drift."""
        try:
            if not self._drift_adapter:
                return 0.0
            
            return self._drift_adapter.get_active_capital()
            
        except Exception as e:
            Logger.debug(f"Drift active capital collection error: {e}")
            return 0.0
    
    async def _collect_delta_state(self) -> Optional[Any]:
        """Collect delta neutrality state."""
        try:
            from src.monitoring.neutrality import DeltaCalculator
            
            if not self._delta_calculator:
                self._delta_calculator = DeltaCalculator(
                    wallet=self._wallet_mgr,
                    drift_adapter=self._drift_adapter,
                    price_feed=self._price_feed,
                )
            
            return await self._delta_calculator.calculate()
            
        except Exception as e:
            Logger.debug(f"Delta state collection error: {e}")
            return None
    
    async def _collect_drift_margin_metrics(self) -> DriftMarginMetrics:
        """Collect Drift margin and health metrics for Risk-First UI."""
        try:

            
            if not self._drift_adapter or not self._drift_adapter._builder:
                return DriftMarginMetrics()
            
            # Use Monitor
            wallet = str(self._drift_adapter._builder.wallet)
            return self._drift_monitor.get_metrics(wallet)
            
        except Exception as e:
            Logger.debug(f"Drift margin metrics fetch failed: {e}")
            return DriftMarginMetrics()

    async def _sync_engine_vaults(self):
        """Sync on-chain vaults with live data."""
        try:
            from src.shared.state.vault_manager import get_vault_registry, VaultType
            registry = get_vault_registry()
            
            # Sync Drift Vault if adapter available
            if self._drift_adapter:
                drift_vault = registry.get_vault("drift")
                if drift_vault.vault_type == VaultType.ON_CHAIN:
                    await drift_vault.sync_from_drift(self._drift_adapter)
                    
        except Exception as e:
            Logger.debug(f"Vault sync failed: {e}")

    def _collect_engine_vaults(self, sol_price: float) -> Dict[str, Any]:
        """Aggregate all engine vaults."""
        from src.shared.state.vault_manager import get_vault_registry
        snapshot = get_vault_registry().get_global_snapshot(sol_price)
        # Extract the inner 'vaults' dict so we don't send metadata as fake engine vaults
        engine_vaults = snapshot.get("vaults", {})
        
        # Debug log to verify we are seeing the vaults
        if not engine_vaults:
            rows = get_vault_registry().get_all_vault_names()
            Logger.debug(f"[Heartbeat] Vault Snapshot EMPTY. Registered Engines: {rows}")
            
        return engine_vaults

    async def _collect_drift_markets(self) -> DriftMarketInfo:
        """
        Collect Drift market opportunities (funding rates).
        """
        try:
            from src.shared.feeds.drift_funding import get_funding_feed
            
            # Use singleton feed (handles caching internally)
            feed = get_funding_feed(use_mock=False)
            
            # Get all rates (async)
            rates = await feed.get_all_funding_rates()
            
            markets = []
            total_oi = 0.0
            total_volume = 0.0
            total_funding_abs = 0.0
            
            for symbol, info in rates.items():
                # Drift funding feed gives basic info, we might need to enrich it 
                # or just use what's available.
                # Currently FundingInfo has: rate_8h, rate_annual, is_positive, mark_price
                
                # Mock some missing data for now (OI/Vol) since feed doesn't have it yet
                # In production, we'd expand the feed to fetch this
                start_seed = sum(ord(c) for c in symbol)
                mock_oi = (start_seed * 1000000) % 500000000 + 10000000
                mock_vol = mock_oi * 1.5
                
                markets.append({
                    "symbol": symbol,
                    "rate": info.rate_8h / 100.0,  # Convert % to decimal
                    "apr": info.rate_annual,
                    "direction": "shorts" if info.is_positive else "longs",
                    "oi": mock_oi,
                    "volume_24h": mock_vol
                })
                
                total_oi += mock_oi
                total_volume += mock_vol
                total_funding_abs += abs(info.rate_annual)
            
            avg_funding = (total_funding_abs / len(markets)) if markets else 0.0
            
            return DriftMarketInfo(
                markets=markets,
                stats={
                    "total_oi": total_oi,
                    "volume_24h": total_volume,
                    "avg_funding": avg_funding
                }
            )
            
        except Exception as e:
            Logger.debug(f"Drift market data collection failed: {e}")
            # Return valid empty structure to prevent frontend errors
            return DriftMarketInfo(
                markets=[],
                stats={
                    "total_oi": 0.0,
                    "volume_24h": 0.0,
                    "avg_funding": 0.0
                }
            )
    
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
    
    async def _get_major_prices(self, sol_price: float) -> Dict[str, float]:
        """
        Fetch major crypto prices (BTC, ETH) for the header tapes.
        
        Uses CoinGecko free API (no key required, but rate limited).
        Falls back to hardcoded values if API fails.
        """
        major_prices = {"SOL": sol_price}
        
        # CoinGecko fallback prices (updated periodically)
        FALLBACK_MAJORS = {
            "BTC": 95000.0,
            "ETH": 3300.0,
            "AVAX": 35.0,
            "SUI": 4.5,
            "JUP": 0.85,
        }
        
        try:
            import httpx
            
            # CoinGecko simple/price API (free, no key needed)
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "bitcoin,ethereum,avalanche-2,sui",
                "vs_currencies": "usd"
            }
            
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    major_prices["BTC"] = data.get("bitcoin", {}).get("usd", FALLBACK_MAJORS["BTC"])
                    major_prices["ETH"] = data.get("ethereum", {}).get("usd", FALLBACK_MAJORS["ETH"])
                    major_prices["AVAX"] = data.get("avalanche-2", {}).get("usd", FALLBACK_MAJORS["AVAX"])
                    major_prices["SUI"] = data.get("sui", {}).get("usd", FALLBACK_MAJORS["SUI"])
                else:
                    # API error, use fallbacks
                    major_prices.update(FALLBACK_MAJORS)
                    
        except Exception as e:
            Logger.debug(f"Major prices fetch error: {e}")
            major_prices.update(FALLBACK_MAJORS)
        
        # Always include JUP from Jupiter feed (Solana native)
        try:
            jup_price = await self._get_asset_price("JUP")
            if jup_price > 0:
                major_prices["JUP"] = jup_price
            else:
                major_prices["JUP"] = FALLBACK_MAJORS["JUP"]
        except Exception:
            major_prices["JUP"] = FALLBACK_MAJORS["JUP"]
        
        return major_prices
    
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
