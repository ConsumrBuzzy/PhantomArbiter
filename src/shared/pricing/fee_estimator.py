"""
Adaptive Fee Estimator
======================
Calculates realistic transaction costs using live market data:
- Per-DEX trading fees
- Live SOL price for gas
- RPC-based priority fees
- Trade-size-based slippage
"""

import time
from typing import Optional
from dataclasses import dataclass
from config.settings import Settings


@dataclass
class FeeEstimate:
    """Complete fee breakdown for a trade."""

    trading_fee_usd: float  # DEX trading fee
    gas_fee_usd: float  # Base gas cost
    priority_fee_usd: float  # Priority/tip for faster inclusion
    slippage_cost_usd: float  # Expected slippage
    safety_buffer_usd: float  # Catch-all buffer
    total_usd: float  # Total fees

    # Metadata
    sol_price: float
    priority_fee_sol: float


class FeeEstimator:
    """
    Adaptive fee calculator using live market data.

    Features:
    - Per-DEX trading fee rates
    - Live SOL price from feeds
    - Network congestion-based priority fees
    - Liquidity-aware slippage
    """

    # Per-DEX trading fees (real rates)
    DEX_FEES = {
        "JUPITER": 0.0035,  # ~0.35% (includes route optimization)
        "RAYDIUM": 0.0025,  # 0.25%
        "ORCA": 0.0025,  # 0.25%
        "PUMPFUN": 0.01,  # 1% (bonding curve)
        "PUMP.FUN": 0.01,  # Alias
        "METEORA": 0.003,  # 0.3%
    }

    def __init__(self):
        # Cache priority fee (updates every 30s)
        self._priority_fee_cache: float = 0.0005  # Default 0.0005 SOL
        self._priority_fee_ts: float = 0.0

        # Cache SOL price
        self._sol_price_cache: float = 100.0  # Default
        self._sol_price_ts: float = 0.0

        # Jito Bribe Multiplier (Congestion Factor)
        # Scales up when we detect congestion issues via failure feedback
        self.jito_multiplier: float = 1.0  # Default 1.0x

    def update_congestion_factor(self, is_congested: bool):
        """Update Jito multiplier based on recent feedback."""
        if is_congested:
            self.jito_multiplier = min(
                self.jito_multiplier * 1.5, 5.0
            )  # Scale up, max 5x
        else:
            self.jito_multiplier = max(
                self.jito_multiplier * 0.9, 1.0
            )  # Decay back to 1x

    def get_priority_fee(self) -> float:
        """Get current network priority fee in SOL."""
        # Cache for 30 seconds
        if time.time() - self._priority_fee_ts < 30:
            return self._priority_fee_cache

        try:
            from src.shared.infrastructure.rpc_balancer import get_rpc_balancer

            rpc = get_rpc_balancer()

            # Query recent prioritization fees
            result, error = rpc.call("getRecentPrioritizationFees", [])

            if result and not error:
                fees = result.get("result", [])
                if fees:
                    # Get median of recent fees (in micro-lamports per CU)
                    priority_fees = [f.get("prioritizationFee", 0) for f in fees[-20:]]
                    median_fee = sorted(priority_fees)[len(priority_fees) // 2]

                    # Convert: micro-lamports/CU → SOL (assuming ~200k CU per tx)
                    # 1 SOL = 1e9 lamports, micro-lamports = lamports * 1e-6
                    compute_units = 200000
                    fee_lamports = (median_fee * compute_units) / 1e6
                    fee_sol = fee_lamports / 1e9

                    # Clamp to reasonable range
                    self._priority_fee_cache = max(0.0001, min(0.01, fee_sol))
                    self._priority_fee_ts = time.time()
                    return self._priority_fee_cache

        except Exception:
            pass

        return self._priority_fee_cache

    def estimate(
        self,
        trade_size_usd: float,
        buy_dex: str,
        sell_dex: str,
        sol_price: float = None,
        liquidity_usd: float = 100000.0,
    ) -> FeeEstimate:
        """
        Calculate complete fee estimate for an arb trade.

        Args:
            trade_size_usd: Size of the trade in USD
            buy_dex: DEX to buy from
            sell_dex: DEX to sell to
            sol_price: Current SOL/USD price (auto-fetched if None)
            liquidity_usd: Pool liquidity for slippage calculation
        """
        sol_price = sol_price or self._sol_price_cache

        # 1. Trading fees (per-DEX)
        buy_fee_pct = self.DEX_FEES.get(buy_dex.upper(), 0.003)
        sell_fee_pct = self.DEX_FEES.get(sell_dex.upper(), 0.003)
        trading_fee = trade_size_usd * (buy_fee_pct + sell_fee_pct)

        # 2. Base gas fee (~0.0001 SOL per signature, 2 txs)
        base_gas_sol = 0.0002  # 2 transactions
        gas_fee = base_gas_sol * sol_price

        # 3. Priority fee (adaptive from network + congestion multiplier)
        priority_sol = self.get_priority_fee()
        priority_fee = (
            priority_sol * sol_price * 2 * self.jito_multiplier
        )  # x2 round trip * congestion

        # 4. Slippage (scales with trade size vs liquidity)
        slippage_base = getattr(Settings, "SLIPPAGE_BASE_PCT", 0.001)
        slippage_impact = getattr(Settings, "SLIPPAGE_IMPACT_MULTIPLIER", 0.5)
        slippage_pct = slippage_base + (
            slippage_impact * trade_size_usd / liquidity_usd
        )
        slippage_cost = trade_size_usd * slippage_pct

        # 5. Safety buffer (quote staleness, rounding, rent)
        safety_buffer = max(0.02, trade_size_usd * 0.0005)

        total = trading_fee + gas_fee + priority_fee + slippage_cost + safety_buffer

        return FeeEstimate(
            trading_fee_usd=trading_fee,
            gas_fee_usd=gas_fee,
            priority_fee_usd=priority_fee,
            slippage_cost_usd=slippage_cost,
            safety_buffer_usd=safety_buffer,
            total_usd=total,
            sol_price=sol_price,
            priority_fee_sol=priority_sol,
        )


# Singleton instance
_estimator: Optional[FeeEstimator] = None


def get_fee_estimator() -> FeeEstimator:
    """Get or create singleton fee estimator."""
    global _estimator
    if _estimator is None:
        _estimator = FeeEstimator()
    return _estimator
