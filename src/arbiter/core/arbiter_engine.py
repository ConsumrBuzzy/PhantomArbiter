"""
V1.0: Arbiter Engine
====================
The central "brain" of the trading loop.
Orchestrates scanning, verification, and execution.
"""

import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.shared.system.logging import Logger
from src.shared.infrastructure.settings import Settings
from src.arbiter.core.pod_engine import pod_manager, USDC_MINT, SOL_MINT
from src.arbiter.core.calibration import get_pair_threshold, get_bootstrap_min_spread
from src.arbiter.core.adaptive_scanner import AdaptiveScanner
from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
from src.arbiter.ui.dashboard_formatter import DashboardFormatter

class ArbiterEngine:
    """
    Orchestrates the continuous trade cycle.
    """
    
    def __init__(self, arbiter: Any, tracker: Any):
        self.arbiter = arbiter # Reference to PhantomArbiter (orchestrator)
        self.tracker = tracker # TradeTracker
        self.config = arbiter.config
        
        # Internal Loop State
        self._scan_counter = 0
        self._last_vote_time = 0
        self._last_discovery_time = time.time()
        self._last_duration = 0
        self._batch_size = 5
        self._last_spreads = {}
        self._trigger_wallets = {}
        self._blacklist_cache = []
        self._blacklist_cache_ts = 0

    async def run(self, 
                  duration_minutes: int = 10, 
                  scan_interval: int = 5, 
                  smart_pods: bool = False, 
                  landlord: Optional[Any] = None) -> None:
        """The main loop logic (Extracted from arbiter.py)."""
        mode_str = "🔴 LIVE" if self.config.live_mode else "📄 PAPER"
        adaptive_mode = scan_interval == 0
        monitor = AdaptiveScanner() if adaptive_mode else None
        current_interval = monitor.base_interval if adaptive_mode else scan_interval
        
        # Pre-Loop Visuals
        print(f"   PHANTOM ENGINE - {mode_str} ACTIVE")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60) if duration_minutes > 0 else float('inf')
        last_trade_time: Dict[str, float] = {}
        cooldown = 5
        wake_event = asyncio.Event()

        # Signal Coordinator Setup
        from src.arbiter.core.signal_coordinator import SignalCoordinator, CoordinatorConfig
        
        def on_activity(symbol):
            if adaptive_mode and monitor:
                monitor.trigger_activity(f"{symbol}/USDC")
                wake_event.set()
                
        def on_flash_warm(symbol, wallet=None):
            if adaptive_mode and monitor:
                monitor.flash_warm(f"{symbol}/USDC")
                if wallet:
                    self._trigger_wallets[f"{symbol}/USDC"] = wallet
                wake_event.set()

        signal_config = CoordinatorConfig(
            wss_enabled=adaptive_mode,
            pairs=self.config.pairs,
            scraper_poll_interval=60
        )
        coordinator = SignalCoordinator(signal_config, on_activity, on_flash_warm=on_flash_warm)
        await coordinator.start()

        try:
            while time.time() < end_time:
                now = datetime.now().strftime("%H:%M:%S")
                wake_event.clear()
                
                # 0. Remote Commands
                while not self.arbiter.command_queue.empty():
                    cmd = self.arbiter.command_queue.get_nowait()
                    if cmd == "STOP_ENGINE":
                        print(f"   [{now}] 🛑 REMOTE STOP RECEIVED")
                        return
                
                # 1. Maintenance & Housekeeping
                await self._perform_maintenance(coordinator, now)
                
                # 2. Pair Selection & Pod Rotation
                active_pod_names = self._rotate_pods(smart_pods)
                
                # 3. SCAN Lifecycle
                should_print = (self._scan_counter % 3 == 0)
                self._scan_counter += 1
                
                trade_size = self._calculate_trade_size()
                
                try:
                    scan_start = time.time()
                    opportunities, all_spreads = await self.arbiter.scan_opportunities(
                        verbose=should_print,
                        scanner=monitor if adaptive_mode else None
                    )
                    self._last_duration = (time.time() - scan_start) * 1000
                    
                    if should_print:
                        print(f"   ⏱️ Scan: {self._last_duration:.0f}ms | Batch: {self._batch_size} pairs")
                        
                    # Update adaptive logic
                    if adaptive_mode and monitor:
                        current_interval = monitor.update(all_spreads)
                    
                    # Store for decay tracking
                    self._last_spreads = {opp.pair: (opp.spread_pct, time.time()) for opp in all_spreads} if all_spreads else {}

                except Exception as e:
                    Logger.error(f"Scan error: {e}")
                    opportunities, all_spreads = [], []

                # 4. VERIFICATION
                verified_opps = await self._verify_top_candidates(opportunities, trade_size, last_trade_time, cooldown)
                
                # 5. DASHBOARD
                self.arbiter.reporter.print_dashboard(
                    spreads=all_spreads,
                    verified_opps=verified_opps,
                    pod_names=active_pod_names,
                    balance=self.tracker.current_balance,
                    gas=self.tracker.gas_balance,
                    daily_profit=self.tracker.total_profit
                )

                # 6. EXECUTION PATHS (Fast vs Normal)
                executed_this_cycle = await self._process_executions(opportunities, verified_opps, trade_size, last_trade_time, cooldown)

                # 7. LANDLORD
                if landlord and self.config.live_mode and not executed_this_cycle:
                    await landlord.tick(self.tracker.current_balance, arb_opportunity=False)

                # 8. SLEEP
                try:
                    await asyncio.wait_for(wake_event.wait(), timeout=current_interval)
                except asyncio.TimeoutError:
                    pass

        finally:
            await coordinator.stop()

    async def _perform_maintenance(self, coordinator, now):
        """Self-healing, discovery, and cycling."""
        # Poll Signals
        new_pairs = coordinator.poll_signals()
        if new_pairs:
            self.config.pairs.extend(new_pairs)
            await coordinator.register_new_pairs(new_pairs)
            print(f"   [{now}] 🧠 Added {len(new_pairs)} hot tokens from Scraper")

        # RPC Voting (V112)
        if time.time() - self._last_vote_time > 60:
            from src.shared.infrastructure.rpc_balancer import get_rpc_balancer
            vote_result = get_rpc_balancer().perform_provider_vote()
            if "WON BY" in vote_result:
                print(f"   [{now}] 🗳️ RPC VOTE: {vote_result}")
            self._last_vote_time = time.time()

        # Discovery (4 hours)
        if time.time() - self._last_discovery_time > 14400:
            self._last_discovery_time = time.time()
            # ... discovery logic ...

    def _rotate_pods(self, smart_pods: bool) -> List[str]:
        """Update self.config.pairs based on pod rotation."""
        if not smart_pods: return []
        
        active_pod_names = pod_manager.get_active_pods()
        scan_pairs = pod_manager.get_pairs_for_pods(active_pod_names)
        
        # Filter for USDC speed initially (V91.0)
        self.config.pairs = [p for p in scan_pairs if p[2] == USDC_MINT]
        return active_pod_names

    def _calculate_trade_size(self) -> float:
        limit = self.config.max_trade if self.config.max_trade > 0 else float('inf')
        return min(self.tracker.current_balance, limit)

    async def _verify_top_candidates(self, opportunities, trade_size, last_trade_time, cooldown):
        """Parallel verification of top candidates."""
        candidates = [op for op in opportunities[:8] if time.time() - last_trade_time.get(op.pair, 0) >= cooldown]
        if not candidates: return []
        
        # Parallel RPC verify (top 4)
        async def verify_one(opp):
            is_valid, real_net, status = await self.arbiter._executor.verify_liquidity(opp, trade_size)
            opp.verification_status = status
            opp.net_profit_usd = real_net
            return opp
            
        return await asyncio.gather(*[verify_one(c) for c in candidates[:4]])

    async def _process_executions(self, opportunities, verified_opps, trade_size, last_trade_time, cooldown) -> bool:
        """Route to Fast or Normal path."""
        # 1. Check OPTIMISTIC / FAST-PATH
        # ... logic ...
        
        # 2. Check NORMAL PATH
        valid_opps = [op for op in verified_opps if "LIVE" in str(op.verification_status or "")]
        if valid_opps:
            best = sorted(valid_opps, key=lambda x: x.net_profit_usd, reverse=True)[0]
            result = await self.arbiter.execute_trade(best, trade_size=trade_size)
            if result.get("success"):
                self.tracker.record_trade(
                    pair=best.pair,
                    net_profit=result['trade']['net_profit'],
                    fees=result['trade'].get('fees', 0.01),
                    mode="LIVE" if self.config.live_mode else "PAPER",
                    engine="SCALPER",
                    trade_size=trade_size
                )
                last_trade_time[best.pair] = time.time()
                return True
        return False
