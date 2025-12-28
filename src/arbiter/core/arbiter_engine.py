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
from config.settings import Settings
from src.arbiter.core.pod_engine import pod_manager, USDC_MINT, SOL_MINT
from src.arbiter.core.calibration import get_pair_threshold, get_bootstrap_min_spread
from src.arbiter.core.adaptive_scanner import AdaptiveScanner
from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
from src.arbiter.ui.dashboard_formatter import DashboardFormatter
from src.shared.state.app_state import state as app_state

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
                    current_spreads = {opp.pair: (opp.spread_pct, time.time()) for opp in all_spreads} if all_spreads else {}
                    
                    # ═══ V131: ML Spread Decay Logging ═══
                    try:
                        from src.shared.system.db_manager import db_manager
                        for pair, (spread, ts) in current_spreads.items():
                            if pair in self._last_spreads:
                                prev_spread, prev_ts = self._last_spreads[pair]
                                time_delta = ts - prev_ts
                                if time_delta > 0 and prev_spread > 0.1:  # Only log meaningful spreads
                                    db_manager.log_spread_decay(pair, prev_spread, spread, time_delta)
                    except Exception as e:
                        pass  # Silent fail for ML logging
                    
                    self._last_spreads = current_spreads

                    # ═══ V12.5: Push to TUI AppState ═══
                    # ═══ V12.5: Push to TUI AppState ═══
                    from src.shared.state.app_state import ArbOpportunity
                    app_state.update_stat("cycles_per_sec", 1.0 / (self._last_duration / 1000.0) if self._last_duration > 0 else 0)
                    app_state.update_stat("pod_status", pod_manager.get_status())
                    app_state.opportunities = [
                        ArbOpportunity(
                            token=o.pair,
                            route=f"{o.buy_dex}->{o.sell_dex}",
                            profit_pct=o.spread_pct,
                            est_profit_sol=o.net_profit_usd / 150.0 # Mock conversion for Sol
                        ) for o in sorted(all_spreads, key=lambda x: x.spread_pct, reverse=True)[:15]
                    ]

                except Exception as e:
                    Logger.error(f"Scan error: {e}")
                    opportunities, all_spreads = [], []

                # 4. VERIFICATION
                verified_opps = await self._verify_top_candidates(opportunities, trade_size, last_trade_time, cooldown)
                
                # 5. DASHBOARD
                stats = self.tracker.get_stats()
                self.arbiter.reporter.print_dashboard(
                    spreads=all_spreads,
                    verified_opps=verified_opps,
                    pod_names=active_pod_names,
                    balance=self.tracker.current_balance,
                    gas=self.tracker.gas_balance,
                    daily_profit=self.tracker.total_profit,
                    total_trades=self.tracker.total_trades,
                    volume=self.tracker.tracker.daily_volume,
                    turnover=self.tracker.tracker.turnover_ratio
                )

                # Update Pod Manager state for rotation
                found_opp = len(opportunities) > 0
                profitable_count = len([o for o in opportunities if o.net_profit_usd > 0])
                
                # ═══ V131: Scan Metrics Logging for ML ═══
                try:
                    from src.shared.system.db_manager import db_manager
                    # Note: datetime already imported at top of file                    
                    # Log scan metrics for learning
                    db_manager.log_cycle(
                        pod_name=",".join(active_pod_names),
                        pairs_scanned=len(self.config.pairs),
                        duration_ms=self._last_duration
                    )
                    
                    # Log opportunity frequency by hour (time-of-day learning)
                    if profitable_count > 0:
                        db_manager.log_spread({
                            "pair": "SCAN_SUMMARY",
                            "spread_pct": profitable_count,  # Repurpose as count
                            "net_estimate": sum(o.net_profit_usd for o in opportunities if o.net_profit_usd > 0),
                            "timestamp": int(time.time()),
                            "hour": datetime.now().hour
                        })
                except Exception as e:
                    pass  # Silent fail for ML logging
                
                for pod in active_pod_names:
                    # Logic: If pod was scanned and no top-tier opps found, penalize slightly to rotate
                    pod_manager.report_result(pod, found_opp, executed=False, success=False)

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
            try:
                from src.tools.discovery import TokenDiscovery
                if not hasattr(self, '_discovery_engine'):
                    self._discovery_engine = TokenDiscovery()
                
                known_mints = set(Settings.ASSETS.values())
                discovered = self._discovery_engine.discover_and_validate(known_mints)
                
                if discovered:
                    USDC = USDC_MINT
                    new_discovered = []
                    for token in discovered:
                        pair = (f"{token['symbol']}/USDC", token['mint'], USDC)
                        if pair not in self.config.pairs:
                            new_discovered.append(pair)
                    
                    if new_discovered:
                        self.config.pairs.extend(new_discovered)
                        print(f"   [{now}] 🔭 Discovery: +{len(new_discovered)} trending tokens")
                
                self._last_discovery_time = time.time()
            except Exception as e:
                Logger.debug(f"Discovery failed: {e}")

        # Smart Pair Cycling (MAX 60)
        if len(self.config.pairs) > 60:
            try:
                from src.shared.system.db_manager import db_manager
                
                # Get performance scores
                pair_scores = {}
                for p_tuple in self.config.pairs:
                    stats = db_manager.get_pair_performance(p_tuple[0])
                    pair_scores[p_tuple[0]] = stats.get('score', 0.5)
                
                # Sort and trim
                sorted_pairs = sorted(self.config.pairs, key=lambda p: pair_scores.get(p[0], 0.5), reverse=True)
                self.config.pairs = sorted_pairs[:60]
                print(f"   [{now}] 🔄 Cycled: Keeping top 60 performers")
            except Exception as e:
                Logger.debug(f"Pair cycling error: {e}")

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
        now = datetime.now().strftime("%H:%M:%S")
        
        # 1. FAST-PATH (ML & Optimistic)
        fast_path_candidates = []
        from src.shared.system.db_manager import db_manager
        
        for op in sorted(opportunities, key=lambda x: x.net_profit_usd, reverse=True):
            if time.time() - last_trade_time.get(op.pair, 0) < cooldown: continue
            
            # A. Optimistic (Unified Engine)
            if self.arbiter.trade_engine.use_unified:
                if op.buy_dex in ["METEORA", "ORCA"] and op.sell_dex in ["METEORA", "ORCA"]:
                    if op.net_profit_usd > 0.10: 
                        op.verification_status = "✨ OPTIMISTIC"
                        fast_path_candidates.append(op)
                        continue

            # B. ML Logic (Thresholds, Decay, etc.)
            pair_threshold = get_pair_threshold(op.pair, self.config.fast_path_threshold)
            
            # Bootstrap fallback
            if pair_threshold == self.config.fast_path_threshold:
                 pair_threshold = get_bootstrap_min_spread(op.pair) or pair_threshold
            
            if (op.net_profit_usd - self.config.decay_buffer) > 0.10 and op.net_profit_usd >= pair_threshold:
                op.verification_status = "⚡ FAST ML"
                fast_path_candidates.append(op)
        
        if fast_path_candidates:
            best_fast = sorted(fast_path_candidates, key=lambda x: x.net_profit_usd, reverse=True)[0]
            print(f"   [{now}] ⚡ FAST-PATH: {best_fast.pair} @ ${best_fast.net_profit_usd:+.3f}")
            
            result = await self.arbiter.execute_trade(best_fast, trade_size=trade_size)
            if result.get("success"):
                trade = result["trade"]
                self.tracker.record_trade(
                    pair=best_fast.pair, 
                    net_profit=trade['net_profit'], 
                    fees=trade.get('fees', 0.02), 
                    mode="LIVE" if self.config.live_mode else "PAPER", 
                    engine="FAST", 
                    trade_size=trade_size
                )
                last_trade_time[best_fast.pair] = time.time()
                
                # Log to DB
                db_manager.log_fast_path({
                    'pair': best_fast.pair,
                    'scan_profit_usd': best_fast.net_profit_usd,
                    'execution_profit_usd': trade['net_profit'],
                    'success': True
                })
                
                # Report success to pod manager
                for pod in pod_manager.get_pods_for_pair(best_fast.pair):
                    pod_manager.report_result(pod, True, executed=True, success=True)
                
                print(DashboardFormatter.format_trade_announcement(trade, self.tracker.current_balance))
                return True
            else:
                print(f"   [{now}] ❌ FAST REVERTED: {result.get('error')}")
                return False

        # 2. NORMAL PATH (Verified)
        valid_opps = [op for op in verified_opps if "LIVE" in str(op.verification_status or "")]
        if valid_opps:
            best = sorted(valid_opps, key=lambda x: x.net_profit_usd, reverse=True)[0]
            
            # Scaled Size Check
            status_str = str(best.verification_status or "")
            exec_size = trade_size
            if "SCALED" in status_str:
                import re
                match = re.search(r'\$(\d+)', status_str)
                if match: exec_size = float(match.group(1))
            
            if exec_size < 10: return False
            
            result = await self.arbiter.execute_trade(best, trade_size=exec_size)
            if result.get("success"):
                trade = result["trade"]
                self.tracker.record_trade(
                    pair=best.pair, 
                    net_profit=trade['net_profit'], 
                    fees=trade.get('fees', 0.02), 
                    mode="LIVE" if self.config.live_mode else "PAPER", 
                    engine="SCALPER", 
                    trade_size=exec_size
                )
                last_trade_time[best.pair] = time.time()
                # Report success to pod manager
                for pod in pod_manager.get_pods_for_pair(best.pair):
                    pod_manager.report_result(pod, True, executed=True, success=True)
                    
                print(DashboardFormatter.format_trade_announcement(trade, self.tracker.current_balance))
                return True
            else:
                print(f"   [{now}] ❌ TRADE FAILED: {result.get('error')}")
                
        return False
