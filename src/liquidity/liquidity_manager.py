"""
V49.0: Liquidity Manager
========================
ML-driven CLMM position orchestrator for Orca Whirlpools.

Responsibilities:
- Calculate optimal range based on volatility and ML regime
- Deploy liquidity during sideways markets
- Harvest fees periodically
- Exit positions when trend is detected

Strategy Rules:
- SIDEWAYS regime → Tight range (±1%) for max fee capture
- NEUTRAL regime → Wide range (±5%) for passive accumulation  
- TREND regime → Remove liquidity to avoid impermanent loss

Capital Recommendations (from Orca analysis):
- $10-30: Full range, passive, learning mode
- $50-100: Medium range, daily rebalancing
- $500+: Active botting, narrow ranges, frequent rebalancing
"""

import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from src.system.logging import Logger
from src.liquidity.orca_adapter import get_orca_adapter, SOL_MINT, USDC_MINT
from src.liquidity.types import WhirlpoolState, PositionState, LiquidityParams
from config.settings import Settings


class MarketRegime(Enum):
    """Market regime classification from ML model."""
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    SIDEWAYS = "sideways"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass
class LiquidityPosition:
    """
    Active liquidity position being managed.
    """
    pool_address: str
    position_address: str  # Position NFT (will be set after opening)
    
    # Range
    tick_lower: int
    tick_upper: int
    price_lower: float
    price_upper: float
    range_pct: float
    
    # Capital deployed
    amount_a: float
    amount_b: float
    value_usd: float
    
    # Fees earned
    fees_earned_a: float = 0.0
    fees_earned_b: float = 0.0
    fees_usd_total: float = 0.0
    
    # Metadata
    entry_time: float = field(default_factory=time.time)
    entry_price: float = 0.0
    regime_at_entry: MarketRegime = MarketRegime.UNKNOWN
    
    # Status
    is_active: bool = True
    exit_reason: str = ""
    exit_time: float = 0.0
    
    @property
    def age_hours(self) -> float:
        return (time.time() - self.entry_time) / 3600
    
    @property
    def is_in_range(self) -> bool:
        """Check if current price is within position range."""
        # This would need current price passed in
        return True  # Placeholder
    
    def __repr__(self):
        status = "🟢" if self.is_active else "⚫"
        return f"{status} Position ${self.value_usd:.2f} range=[${self.price_lower:.4f}, ${self.price_upper:.4f}]"


class LiquidityManager:
    """
    V49.0: Intelligent CLMM Position Manager.
    
    Coordinates with:
    - OrcaAdapter: Low-level pool interactions
    - ML Model: Regime detection  
    - CapitalManager: Position sizing
    
    Usage:
        manager = get_liquidity_manager()
        
        # Check if we should deploy liquidity
        if manager.should_deploy(regime=MarketRegime.SIDEWAYS):
            position = manager.deploy_range(pool_address, range_pct=1.0)
        
        # Periodic fee harvesting
        manager.harvest_all_fees()
        
        # Exit on trend detection
        if regime == MarketRegime.TREND_UP:
            manager.close_all_positions(reason="Trend detected")
    """
    
    def __init__(self, simulation_mode: bool = True):
        """
        Initialize liquidity manager.
        
        Args:
            simulation_mode: If True, transactions are simulated (default: True)
        """
        from src.infrastructure.signer import get_signer, ExecutionMode
        
        self.adapter = get_orca_adapter()
        self.positions: Dict[str, LiquidityPosition] = {}
        self._last_harvest_time = 0
        
        # Transaction signer (SIMULATION by default for safety)
        signer_mode = ExecutionMode.SIMULATION if simulation_mode else ExecutionMode.PAPER
        self.signer = get_signer(signer_mode)
        self.simulation_mode = simulation_mode
        
        # Settings from config
        self.tight_range_pct = getattr(Settings, 'ORCA_TIGHT_RANGE_PCT', 1.0)
        self.wide_range_pct = getattr(Settings, 'ORCA_WIDE_RANGE_PCT', 5.0)
        self.harvest_interval = getattr(Settings, 'ORCA_HARVEST_INTERVAL_HOURS', 4) * 3600
        self.min_liquidity = getattr(Settings, 'ORCA_MIN_LIQUIDITY_USD', 100)
        self.max_liquidity_pct = getattr(Settings, 'ORCA_MAX_LIQUIDITY_PCT', 0.20)
        
        mode_str = "SIMULATION" if simulation_mode else "PAPER"
        Logger.info(f"   💧 [LIQUIDITY] Manager Initialized ({mode_str} MODE)")
    
    # =========================================================================
    # REGIME-BASED DECISION LOGIC
    # =========================================================================
    
    def get_optimal_range(self, regime: MarketRegime) -> float:
        """
        Calculate optimal range width based on market regime.
        
        Args:
            regime: Current market regime from ML model
            
        Returns:
            Range percentage (e.g., 1.0 = ±1%)
        """
        if regime == MarketRegime.SIDEWAYS:
            return self.tight_range_pct  # ±1% - Maximum fee capture
        elif regime == MarketRegime.NEUTRAL:
            return self.wide_range_pct   # ±5% - Safe passive
        else:
            return 0.0  # Don't deploy during trends
    
    def should_deploy(
        self, 
        regime: MarketRegime, 
        available_capital: float
    ) -> Tuple[bool, str]:
        """
        Determine if we should deploy liquidity.
        
        Args:
            regime: Current market regime
            available_capital: Available capital in USD
            
        Returns:
            (should_deploy, reason_string)
        """
        # Check if Orca is enabled
        if not getattr(Settings, 'ORCA_ENABLED', False):
            return False, "Orca CLMM disabled in settings"
        
        # Check regime
        if regime in [MarketRegime.TREND_UP, MarketRegime.TREND_DOWN]:
            return False, f"Trend detected ({regime.value}) - avoiding IL"
        
        # Check capital
        if available_capital < self.min_liquidity:
            return False, f"Insufficient capital (${available_capital:.2f} < ${self.min_liquidity})"
        
        # Check existing positions
        active_value = sum(p.value_usd for p in self.positions.values() if p.is_active)
        max_allowed = available_capital * self.max_liquidity_pct
        
        if active_value >= max_allowed:
            return False, f"Max liquidity deployed (${active_value:.2f}/${max_allowed:.2f})"
        
        return True, f"Clear to deploy ({regime.value})"
    
    # =========================================================================
    # POSITION LIFECYCLE
    # =========================================================================
    
    def calculate_position_params(
        self,
        pool_address: str,
        capital_usd: float,
        range_pct: float
    ) -> Optional[LiquidityParams]:
        """
        Calculate position parameters for deployment.
        
        Args:
            pool_address: Target Whirlpool
            capital_usd: USD value to deploy
            range_pct: Range width percentage
            
        Returns:
            LiquidityParams with calculated values, or None on error
        """
        # Fetch current pool state
        state = self.adapter.get_whirlpool_state(pool_address)
        if not state:
            Logger.error("   💧 [LIQUIDITY] Failed to fetch pool state")
            return None
        
        # Calculate tick range
        tick_lower, tick_upper = self.adapter.calculate_range_ticks(
            state.price, 
            range_pct, 
            state.tick_spacing
        )
        
        # Calculate token amounts (50/50 split for CLMM)
        # In practice, this depends on where in the range the price is
        half_capital = capital_usd / 2
        amount_a = half_capital / state.price if state.price > 0 else 0
        amount_b = half_capital
        
        params = LiquidityParams(
            pool_address=pool_address,
            range_pct=range_pct,
            amount_usd=capital_usd,
            center_price=state.price,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            amount_a=amount_a,
            amount_b=amount_b,
        )
        
        Logger.info(f"   💧 [LIQUIDITY] Calculated: ±{range_pct}% range, ${capital_usd:.2f}")
        
        return params
    
    def deploy_position(
        self,
        pool_address: str,
        capital_usd: float,
        regime: MarketRegime = MarketRegime.NEUTRAL,
        owner_pubkey: str = ""
    ) -> Optional[LiquidityPosition]:
        """
        Deploy a new liquidity position.
        
        Uses the TransactionSigner to execute (or simulate) the transaction.
        
        Args:
            pool_address: Target Whirlpool
            capital_usd: USD value to deploy
            regime: Current market regime
            owner_pubkey: Wallet public key
            
        Returns:
            LiquidityPosition if successful, None otherwise
        """
        # Calculate optimal range
        range_pct = self.get_optimal_range(regime)
        if range_pct == 0:
            Logger.warning("   💧 [LIQUIDITY] Range is 0% - skipping deployment")
            return None
        
        # Calculate position parameters
        params = self.calculate_position_params(pool_address, capital_usd, range_pct)
        if not params:
            return None
        
        # Fetch pool state for tick spacing
        state = self.adapter.get_whirlpool_state(pool_address)
        tick_spacing = state.tick_spacing if state else 64
        
        # Build transaction instruction
        ix = self.adapter.build_open_position_ix(
            pool_address=pool_address,
            tick_lower=params.tick_lower,
            tick_upper=params.tick_upper,
            owner_pubkey=owner_pubkey or "SIMULATION_WALLET",
            tick_spacing=tick_spacing,
        )
        
        if not ix:
            Logger.error("   💧 [LIQUIDITY] Failed to build open_position instruction")
            return None
        
        # Sign and submit (or simulate)
        result = self.signer.sign_and_submit(ix)
        
        if not result.success:
            Logger.error(f"   💧 [LIQUIDITY] Transaction failed: {result.error}")
            return None
        
        # Create position with signature
        position = LiquidityPosition(
            pool_address=pool_address,
            position_address=ix.get("position_pda", result.signature),
            tick_lower=params.tick_lower,
            tick_upper=params.tick_upper,
            price_lower=self.adapter.tick_to_price(params.tick_lower),
            price_upper=self.adapter.tick_to_price(params.tick_upper),
            range_pct=range_pct,
            amount_a=params.amount_a,
            amount_b=params.amount_b,
            value_usd=capital_usd,
            entry_price=params.center_price,
            regime_at_entry=regime,
        )
        
        # Track position
        position_id = f"{pool_address[:8]}_{int(time.time())}"
        self.positions[position_id] = position
        
        Logger.success(f"   💧 [LIQUIDITY] Position created: {position}")
        Logger.info(f"   💧 [LIQUIDITY]   TX: {result.signature}")
        
        return position
    
    def harvest_fees(self, position_id: str) -> Tuple[float, float]:
        """
        Collect accumulated fees from a position.
        
        NOTE: This is a STUB - actual transaction execution requires Phase B.2
        
        Args:
            position_id: Position identifier
            
        Returns:
            (fees_token_a, fees_token_b)
        """
        position = self.positions.get(position_id)
        if not position or not position.is_active:
            return (0.0, 0.0)
        
        # TODO: Phase B.2 - Execute collect_fees transaction
        # fees = self.adapter.build_collect_fees_ix(position.position_address)
        
        Logger.info(f"   💧 [LIQUIDITY] Harvested fees from {position_id}")
        
        return (0.0, 0.0)  # Placeholder
    
    def harvest_all_fees(self) -> Dict[str, Tuple[float, float]]:
        """
        Harvest fees from all active positions.
        
        Returns:
            Dict of position_id -> (fees_a, fees_b)
        """
        now = time.time()
        
        # Respect harvest interval
        if (now - self._last_harvest_time) < self.harvest_interval:
            hours_until = (self.harvest_interval - (now - self._last_harvest_time)) / 3600
            Logger.debug(f"   💧 [LIQUIDITY] Harvest cooldown: {hours_until:.1f}h remaining")
            return {}
        
        results = {}
        for pos_id, position in self.positions.items():
            if position.is_active:
                results[pos_id] = self.harvest_fees(pos_id)
        
        self._last_harvest_time = now
        Logger.success(f"   💧 [LIQUIDITY] Harvested {len(results)} positions")
        
        return results
    
    def close_position(self, position_id: str, reason: str = "") -> bool:
        """
        Close a liquidity position and withdraw capital.
        
        NOTE: This is a STUB - actual transaction execution requires Phase B.2
        
        Args:
            position_id: Position identifier
            reason: Exit reason for logging
            
        Returns:
            True if successful
        """
        position = self.positions.get(position_id)
        if not position:
            Logger.warning(f"   💧 [LIQUIDITY] Position not found: {position_id}")
            return False
        
        if not position.is_active:
            Logger.warning(f"   💧 [LIQUIDITY] Position already closed: {position_id}")
            return False
        
        # TODO: Phase B.2 - Execute close_position transaction
        # 1. Collect final fees
        # 2. Remove liquidity
        # 3. Close position account
        
        position.is_active = False
        position.exit_reason = reason
        position.exit_time = time.time()
        
        Logger.info(f"   💧 [LIQUIDITY] Closed position: {position_id} ({reason})")
        
        return True
    
    def close_all_positions(self, reason: str = "Manual exit") -> int:
        """
        Close all active positions.
        
        Args:
            reason: Exit reason for logging
            
        Returns:
            Number of positions closed
        """
        closed = 0
        for pos_id in list(self.positions.keys()):
            if self.close_position(pos_id, reason):
                closed += 1
        
        Logger.success(f"   💧 [LIQUIDITY] Closed {closed} positions ({reason})")
        return closed
    
    # =========================================================================
    # STATUS & MONITORING
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get manager status for monitoring."""
        active = [p for p in self.positions.values() if p.is_active]
        
        return {
            "active_positions": len(active),
            "total_value_usd": sum(p.value_usd for p in active),
            "total_fees_usd": sum(p.fees_usd_total for p in active),
            "positions": [repr(p) for p in active],
        }
    
    def display_positions(self) -> None:
        """Print formatted position summary."""
        active = [p for p in self.positions.values() if p.is_active]
        
        if not active:
            print("   No active liquidity positions")
            return
        
        print("\n" + "=" * 60)
        print("💧 ACTIVE LIQUIDITY POSITIONS")
        print("=" * 60)
        
        total_value = 0
        total_fees = 0
        
        for pos in active:
            total_value += pos.value_usd
            total_fees += pos.fees_usd_total
            
            print(f"\n   Pool: {pos.pool_address[:16]}...")
            print(f"   Range: ${pos.price_lower:.4f} - ${pos.price_upper:.4f} (±{pos.range_pct}%)")
            print(f"   Value: ${pos.value_usd:.2f}")
            print(f"   Fees Earned: ${pos.fees_usd_total:.4f}")
            print(f"   Age: {pos.age_hours:.1f}h")
        
        print("\n" + "-" * 60)
        print(f"   Total Value: ${total_value:.2f}")
        print(f"   Total Fees: ${total_fees:.4f}")
        print("=" * 60 + "\n")
    
    # =========================================================================
    # HARVESTING LOOP (Phase C - Self-Healing Position Management)
    # =========================================================================
    
    def run_health_check(self, current_regime: MarketRegime) -> Dict[str, Any]:
        """
        Run health check on all active positions.
        
        Called periodically (every ~1 hour) to:
        1. Check if price is still in range
        2. Check if fees are ready to harvest
        3. Check if regime changed (need to exit)
        
        Args:
            current_regime: Current market regime from ML model
            
        Returns:
            Health report with recommended actions
        """
        report = {
            "timestamp": time.time(),
            "regime": current_regime.value,
            "positions_checked": 0,
            "needs_harvest": [],
            "out_of_range": [],
            "emergency_exit": [],
            "actions_taken": [],
        }
        
        # Check for regime change requiring exit
        if current_regime in [MarketRegime.TREND_UP, MarketRegime.TREND_DOWN]:
            for pos_id, pos in self.positions.items():
                if pos.is_active:
                    report["emergency_exit"].append({
                        "position_id": pos_id,
                        "reason": f"Regime changed to {current_regime.value}",
                    })
            Logger.warning(f"   💧 [LIQUIDITY] Regime change detected: {current_regime.value}")
        
        for pos_id, position in self.positions.items():
            if not position.is_active:
                continue
            
            report["positions_checked"] += 1
            
            # Get current pool state
            state = self.adapter.get_whirlpool_state(position.pool_address)
            if not state:
                continue
            
            current_price = state.price
            
            # Check if out of range
            price_lower = self.adapter.tick_to_price(position.tick_lower)
            price_upper = self.adapter.tick_to_price(position.tick_upper)
            
            # Boundary warning: within 0.5% of edge
            boundary_threshold = 0.005
            near_lower = current_price < price_lower * (1 + boundary_threshold)
            near_upper = current_price > price_upper * (1 - boundary_threshold)
            
            if current_price < price_lower or current_price > price_upper:
                report["out_of_range"].append({
                    "position_id": pos_id,
                    "current_price": current_price,
                    "range": [price_lower, price_upper],
                    "action": "recommend_close",
                })
            elif near_lower or near_upper:
                report["emergency_exit"].append({
                    "position_id": pos_id,
                    "reason": f"Price near boundary (${current_price:.2f})",
                    "action": "emergency_close",
                })
            
            # Check if harvest worthwhile (> $0.50)
            MIN_HARVEST_VALUE = 0.50
            estimated_fees = position.fees_usd_total  # TODO: Fetch actual pending fees
            
            if estimated_fees >= MIN_HARVEST_VALUE:
                report["needs_harvest"].append({
                    "position_id": pos_id,
                    "estimated_fees": estimated_fees,
                })
        
        return report
    
    def execute_harvesting_cycle(self, current_regime: MarketRegime) -> Dict[str, Any]:
        """
        Execute a full harvesting cycle.
        
        This is the main entry point for the self-healing loop.
        Should be called every ~1 hour by the main orchestrator.
        
        Steps:
        1. Run health check
        2. Emergency exit positions at boundary
        3. Harvest fees from healthy positions
        4. Deploy new positions if regime allows
        
        Args:
            current_regime: Current market regime
            
        Returns:
            Cycle results
        """
        Logger.info("   💧 [LIQUIDITY] Starting harvesting cycle...")
        
        results = {
            "health_check": {},
            "positions_closed": 0,
            "fees_harvested": 0.0,
            "positions_opened": 0,
        }
        
        # 1. Health Check
        report = self.run_health_check(current_regime)
        results["health_check"] = report
        
        # 2. Emergency Exit
        for exit_item in report.get("emergency_exit", []):
            pos_id = exit_item["position_id"]
            reason = exit_item.get("reason", "Emergency exit")
            
            if self.close_position(pos_id, reason):
                results["positions_closed"] += 1
                Logger.warning(f"   💧 [LIQUIDITY] Emergency exit: {pos_id} ({reason})")
        
        # 3. Harvest Fees
        if report.get("needs_harvest"):
            harvested = self.harvest_all_fees()
            results["fees_harvested"] = sum(
                sum(fees) for fees in harvested.values()
            )
        
        # 4. Close out-of-range positions
        for oor_item in report.get("out_of_range", []):
            pos_id = oor_item["position_id"]
            if self.close_position(pos_id, "Out of range"):
                results["positions_closed"] += 1
        
        Logger.success(f"   💧 [LIQUIDITY] Cycle complete: {results['positions_closed']} closed, ${results['fees_harvested']:.2f} harvested")
        
        return results
    
    def is_price_near_boundary(
        self, 
        position_id: str, 
        threshold_pct: float = 0.5
    ) -> Tuple[bool, str]:
        """
        Check if current price is near position boundary.
        
        Args:
            position_id: Position to check
            threshold_pct: Warning threshold (0.5 = 0.5%)
            
        Returns:
            (is_near_boundary, boundary_side)
        """
        position = self.positions.get(position_id)
        if not position or not position.is_active:
            return False, ""
        
        state = self.adapter.get_whirlpool_state(position.pool_address)
        if not state:
            return False, ""
        
        current_price = state.price
        
        # Calculate threshold prices
        threshold = threshold_pct / 100
        lower_threshold = position.price_lower * (1 + threshold)
        upper_threshold = position.price_upper * (1 - threshold)
        
        if current_price <= lower_threshold:
            return True, "lower"
        elif current_price >= upper_threshold:
            return True, "upper"
        
        return False, ""


# =============================================================================
# SINGLETON
# =============================================================================

_manager_instance: Optional[LiquidityManager] = None


def get_liquidity_manager() -> LiquidityManager:
    """Get or create the singleton liquidity manager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LiquidityManager()
    return _manager_instance


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    
    print("\n💧 Liquidity Manager Test")
    print("=" * 50)
    
    manager = get_liquidity_manager()
    
    # Test deployment logic
    print("\n📊 Testing deployment decision...")
    
    for regime in MarketRegime:
        should, reason = manager.should_deploy(regime, available_capital=500)
        status = "✅" if should else "❌"
        print(f"   {status} {regime.value}: {reason}")
    
    # Test position calculation
    pool = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"
    print(f"\n📐 Calculating position params for ${100}...")
    
    params = manager.calculate_position_params(pool, 100, 1.0)
    if params:
        print(f"   Range: tick [{params.tick_lower}, {params.tick_upper}]")
        print(f"   Amount A: {params.amount_a:.4f}")
        print(f"   Amount B: {params.amount_b:.4f}")
    
    print("\n✅ Test complete!")
