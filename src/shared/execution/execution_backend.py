"""
V1.0: Execution Backend Protocol
================================
Unified execution abstraction for Paper and Live trading.

Both backends use IDENTICAL slippage/fee math to ensure Paper = Live parity.
The only difference is the "output layer":
- Paper: Simulates the fill
- Live: Submits to Jito/Jupiter
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any, Protocol, runtime_checkable

from config.settings import Settings
from src.shared.models.trade_result import TradeResult
from src.shared.system.logging import Logger


# =============================================================================
# SHARED SLIPPAGE CALCULATOR
# =============================================================================

@dataclass
class SlippageParams:
    """Parameters for slippage calculation."""
    base_pct: float = 0.003       # 0.3% base slippage
    volatility_mult: float = 3.0   # Volatility scaling factor
    impact_mult: float = 0.05      # Size impact factor
    max_pct: float = 0.05          # 5% cap


def calculate_slippage(
    size_usd: float,
    liquidity_usd: float,
    velocity_1m: float = 0.0,
    latency_ms: float = 0.0,
    params: Optional[SlippageParams] = None
) -> float:
    """
    Unified slippage calculation used by BOTH Paper and Live backends.
    
    Formula: Slippage = Base + LiquidityImpact + VolatilityPenalty + LatencyPenalty
    
    Args:
        size_usd: Trade size in USD
        liquidity_usd: Pool/market liquidity
        velocity_1m: 1-minute price velocity (%)
        latency_ms: Execution latency in milliseconds
        params: Optional custom parameters
        
    Returns:
        Slippage as decimal (e.g., 0.01 = 1%)
    """
    if params is None:
        params = SlippageParams()
    
    # 1. Base Slippage
    slippage = params.base_pct
    
    # 2. Liquidity Impact (larger trades vs smaller pools = more slippage)
    if liquidity_usd > 0:
        size_ratio = size_usd / liquidity_usd
        slippage += size_ratio * params.impact_mult
    
    # 3. Volatility Penalty (faster markets = more slippage)
    if velocity_1m != 0:
        slippage += abs(velocity_1m) * 0.01 * params.volatility_mult
    
    # 4. Latency Penalty (slower execution = worse fill)
    if latency_ms > 0 and velocity_1m > 0:
        latency_sec = latency_ms / 1000.0
        # Assume we catch the "tail" of the move
        slippage += velocity_1m * (latency_sec / 60.0) * 2.0
    
    # 5. Cap at max
    return min(slippage, params.max_pct)


def calculate_gas_fee_usd(sol_price: float = 150.0) -> float:
    """Calculate gas fee in USD."""
    gas_sol = getattr(Settings, 'SIMULATION_SWAP_FEE_SOL', 0.0002)
    return gas_sol * sol_price


def calculate_dex_fee(size_usd: float, fee_bps: int = 30) -> float:
    """Calculate DEX trading fee."""
    return size_usd * (fee_bps / 10000.0)


# =============================================================================
# EXECUTION BACKEND PROTOCOL
# =============================================================================

@runtime_checkable
class ExecutionBackend(Protocol):
    """
    Protocol that both Paper and Live execution must implement.
    
    Ensures identical logic paths with only the output layer differing.
    """
    
    def execute_buy(
        self,
        token: str,
        mint: str,
        size_usd: float,
        signal_price: float,
        liquidity_usd: float,
        velocity_1m: float = 0.0,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """Execute a buy order and return standardized result."""
        ...
    
    def execute_sell(
        self,
        token: str,
        mint: str,
        quantity: float,
        signal_price: float,
        entry_price: float,
        liquidity_usd: float,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """Execute a sell order and return standardized result."""
        ...


# =============================================================================
# PAPER BACKEND
# =============================================================================

class PaperBackend:
    """
    Simulated execution using identical slippage/fee math as Live.
    
    All calculations mirror what Live would do, but the "fill" is simulated
    rather than submitted to the network.
    """
    
    def __init__(self, capital_manager: Any, engine_name: str = "PRIMARY"):
        """
        Initialize PaperBackend.
        
        Args:
            capital_manager: CapitalManager instance for state management
            engine_name: Engine identifier for multi-engine support
        """
        self.cm = capital_manager
        self.engine_name = engine_name
        self._latency_ms = getattr(Settings, 'EXECUTION_DELAY_MIN_MS', 200)
    
    def execute_buy(
        self,
        token: str,
        mint: str,
        size_usd: float,
        signal_price: float,
        liquidity_usd: float,
        velocity_1m: float = 0.0,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """
        Simulate a buy order using unified slippage math.
        
        Returns:
            TradeResult with simulated fill details
        """
        start_time = time.time()
        
        # 1. Pre-flight: Check cash
        engine_state = self.cm.state.get("engines", {}).get(self.engine_name)
        if not engine_state:
            return TradeResult.failed(token, "BUY", f"Engine {self.engine_name} not found", "PAPER")
        
        if engine_state.get("cash_balance", 0) < size_usd:
            return TradeResult.failed(token, "BUY", "Insufficient cash", "PAPER")
        
        # 2. Calculate slippage (SHARED LOGIC)
        slippage_pct = calculate_slippage(
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
            velocity_1m=velocity_1m,
            latency_ms=self._latency_ms
        )
        
        # 3. Calculate fill price
        fill_price = signal_price * (1.0 + slippage_pct)
        
        # 4. Calculate quantity
        quantity = size_usd / fill_price
        
        # 5. Calculate fees
        gas_fee_usd = calculate_gas_fee_usd()
        dex_fee_usd = calculate_dex_fee(size_usd)
        total_fees = gas_fee_usd + dex_fee_usd
        
        # 6. Update state
        engine_state["cash_balance"] -= size_usd
        engine_state["stats"]["fees_paid_usd"] = engine_state["stats"].get("fees_paid_usd", 0) + total_fees
        
        # Record position
        from src.shared.execution.paper_wallet import PaperAsset
        if token not in engine_state["positions"]:
            engine_state["positions"][token] = PaperAsset(symbol=token, mint=mint, balance=0.0, avg_price=0.0)
        
        asset = engine_state["positions"][token]
        total_val = (asset.balance * asset.avg_price) + size_usd
        new_bal = asset.balance + quantity
        asset.avg_price = total_val / new_bal if new_bal > 0 else fill_price
        asset.balance = new_bal
        
        # 7. Log
        Logger.info(
            f"📝 [PAPER] BUY {token} | ${signal_price:.4f} → ${fill_price:.4f} "
            f"(Slip: {slippage_pct*100:.2f}%, Qty: {quantity:.6f})"
        )
        
        return TradeResult(
            success=True,
            action="BUY",
            token=token,
            fill_price=fill_price,
            quantity=quantity,
            slippage_pct=slippage_pct * 100,
            timestamp=time.time(),
            tx_id=f"paper_{int(start_time*1000)}",
            source="PAPER",
            requested_price=signal_price,
            latency_ms=self._latency_ms,
            reason=reason,
        )
    
    def execute_sell(
        self,
        token: str,
        mint: str,
        quantity: float,
        signal_price: float,
        entry_price: float,
        liquidity_usd: float,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """
        Simulate a sell order using unified slippage math.
        
        Returns:
            TradeResult with simulated fill details and PnL
        """
        start_time = time.time()
        
        # 1. Pre-flight: Check position
        engine_state = self.cm.state.get("engines", {}).get(self.engine_name)
        if not engine_state:
            return TradeResult.failed(token, "SELL", f"Engine {self.engine_name} not found", "PAPER")
        
        position = engine_state.get("positions", {}).get(token)
        if not position or position.balance <= 0:
            return TradeResult.failed(token, "SELL", f"No position in {token}", "PAPER")
        
        sell_qty = min(quantity, position.balance) if quantity > 0 else position.balance
        size_usd = sell_qty * signal_price
        
        # 2. Calculate slippage (negative for sells in trending down)
        slippage_pct = calculate_slippage(
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
            velocity_1m=kwargs.get("velocity_1m", 0.0),
            latency_ms=self._latency_ms
        )
        
        # 3. Calculate fill price (slippage works against us on sells)
        fill_price = signal_price * (1.0 - slippage_pct)
        
        # 4. Calculate PnL
        gross_pnl = (fill_price - entry_price) * sell_qty
        fees = calculate_gas_fee_usd() + calculate_dex_fee(size_usd)
        net_pnl = gross_pnl - fees
        
        # 5. Update state
        position.balance -= sell_qty
        engine_state["cash_balance"] += size_usd * (1 - slippage_pct) - fees
        engine_state["stats"]["fees_paid_usd"] = engine_state["stats"].get("fees_paid_usd", 0) + fees
        engine_state["stats"]["total_pnl_usd"] = engine_state["stats"].get("total_pnl_usd", 0) + net_pnl
        
        if net_pnl > 0:
            engine_state["stats"]["wins"] = engine_state["stats"].get("wins", 0) + 1
        else:
            engine_state["stats"]["losses"] = engine_state["stats"].get("losses", 0) + 1
        
        # 6. Log
        emoji = "🟢" if net_pnl > 0 else "🔴"
        Logger.info(
            f"📝 [PAPER] SELL {token} | ${signal_price:.4f} → ${fill_price:.4f} "
            f"| PnL: {emoji} ${net_pnl:.2f}"
        )
        
        return TradeResult(
            success=True,
            action="SELL",
            token=token,
            fill_price=fill_price,
            quantity=sell_qty,
            slippage_pct=slippage_pct * 100,
            timestamp=time.time(),
            tx_id=f"paper_{int(start_time*1000)}",
            pnl_usd=net_pnl,
            source="PAPER",
            requested_price=signal_price,
            latency_ms=self._latency_ms,
            reason=reason,
        )


# =============================================================================
# LIVE BACKEND
# =============================================================================

class LiveBackend:
    """
    Real execution via Jito/Jupiter.
    
    Uses identical slippage calculation to set max_slippage on transactions.
    The actual fill may differ, which is what ShadowManager audits.
    """
    
    def __init__(self, swapper: Any, engine_name: str = "PRIMARY"):
        """
        Initialize LiveBackend.
        
        Args:
            swapper: SwapExecutor instance for real trades
            engine_name: Engine identifier
        """
        self.swapper = swapper
        self.engine_name = engine_name
    
    def execute_buy(
        self,
        token: str,
        mint: str,
        size_usd: float,
        signal_price: float,
        liquidity_usd: float,
        velocity_1m: float = 0.0,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """
        Execute a real buy order via the swapper.
        
        Uses shared slippage calculation to set max_slippage parameter.
        """
        start_time = time.time()
        
        # 1. Calculate expected slippage (for max_slippage setting)
        expected_slippage = calculate_slippage(
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
            velocity_1m=velocity_1m,
            latency_ms=0  # Live has actual network latency
        )
        
        # 2. Execute via swapper
        try:
            tx_id = self.swapper.execute_swap(
                direction="BUY",
                amount_usd=size_usd,
                reason=reason,
                target_mint=mint,
                max_slippage_pct=expected_slippage * 100  # Convert to percentage
            )
        except Exception as e:
            Logger.error(f"[LIVE] Buy failed: {e}")
            return TradeResult.failed(token, "BUY", str(e), "LIVE")
        
        if not tx_id:
            return TradeResult.failed(token, "BUY", "Swap returned no tx_id", "LIVE")
        
        # 3. Estimate fill (actual fill comes from on-chain confirmation)
        # For now, use expected values - real fill should be fetched from tx
        estimated_fill = signal_price * (1.0 + expected_slippage)
        estimated_qty = size_usd / estimated_fill
        
        latency = (time.time() - start_time) * 1000
        
        Logger.info(
            f"🚀 [LIVE] BUY {token} | ${signal_price:.4f} → ~${estimated_fill:.4f} "
            f"| TX: {tx_id[:16]}..."
        )
        
        return TradeResult(
            success=True,
            action="BUY",
            token=token,
            fill_price=estimated_fill,  # TODO: Fetch actual from tx
            quantity=estimated_qty,
            slippage_pct=expected_slippage * 100,
            timestamp=time.time(),
            tx_id=tx_id,
            source="LIVE",
            requested_price=signal_price,
            latency_ms=latency,
            reason=reason,
        )
    
    def execute_sell(
        self,
        token: str,
        mint: str,
        quantity: float,
        signal_price: float,
        entry_price: float,
        liquidity_usd: float,
        reason: str = "",
        **kwargs
    ) -> TradeResult:
        """
        Execute a real sell order via the swapper.
        """
        start_time = time.time()
        size_usd = quantity * signal_price
        
        # 1. Calculate expected slippage
        expected_slippage = calculate_slippage(
            size_usd=size_usd,
            liquidity_usd=liquidity_usd,
            velocity_1m=kwargs.get("velocity_1m", 0.0),
            latency_ms=0
        )
        
        # 2. Execute via swapper
        try:
            tx_id = self.swapper.execute_swap(
                direction="SELL",
                amount_usd=size_usd,
                reason=reason,
                target_mint=mint,
                max_slippage_pct=expected_slippage * 100
            )
        except Exception as e:
            Logger.error(f"[LIVE] Sell failed: {e}")
            return TradeResult.failed(token, "SELL", str(e), "LIVE")
        
        if not tx_id:
            return TradeResult.failed(token, "SELL", "Swap returned no tx_id", "LIVE")
        
        # 3. Estimate results
        estimated_fill = signal_price * (1.0 - expected_slippage)
        estimated_pnl = (estimated_fill - entry_price) * quantity
        
        latency = (time.time() - start_time) * 1000
        
        emoji = "🟢" if estimated_pnl > 0 else "🔴"
        Logger.info(
            f"🚀 [LIVE] SELL {token} | ${signal_price:.4f} → ~${estimated_fill:.4f} "
            f"| PnL: {emoji} ~${estimated_pnl:.2f} | TX: {tx_id[:16]}..."
        )
        
        return TradeResult(
            success=True,
            action="SELL",
            token=token,
            fill_price=estimated_fill,  # TODO: Fetch actual from tx
            quantity=quantity,
            slippage_pct=expected_slippage * 100,
            timestamp=time.time(),
            tx_id=tx_id,
            pnl_usd=estimated_pnl,
            source="LIVE",
            requested_price=signal_price,
            latency_ms=latency,
            reason=reason,
        )
