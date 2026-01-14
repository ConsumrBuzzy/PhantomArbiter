"""
Shadow Execution Engine
=======================
Calculates the 'Real Receipt' to explain exactly why a trade is profitable or not.
Deconstructs fees into atomic components:
- Two-Hop DEX Fees
- Fixed Network Costs
- Slippage Impact
- ML Risk Penalty
"""

from dataclasses import dataclass


@dataclass
class ShadowReceipt:
    gross_usd: float
    dex_fees_usd: float
    network_costs_usd: float
    slippage_usd: float
    ml_penalty_usd: float
    net_final_usd: float

    def to_string(self) -> str:
        """Format receipt as a multi-line string."""
        return (
            f"   🧾 SHADOW RECEIPT:\n"
            f"      Gross Profit:   ${self.gross_usd:>.4f}\n"
            f"      - DEX Fees:     ${self.dex_fees_usd:>.4f} (0.6% two-hop)\n"
            f"      - Network:      ${self.network_costs_usd:>.4f} (Gas + Priority)\n"
            f"      - Slippage:     ${self.slippage_usd:>.4f}\n"
            f"      - ML Penalty:   ${self.ml_penalty_usd:>.4f} (Decay/Risk)\n"
            f"      -------------------------\n"
            f"      = NET PROFIT:   ${self.net_final_usd:>.4f}"
        )


class ShadowEngine:
    """Production-grade fee modeling for detailed breakdowns."""

    # 2025 Solana Reality: ~0.3% per hop (Orca/Raydium/Meteora)
    DEX_FEE_RATE = 0.003

    def get_receipt(
        self,
        gross_spread_usd: float,
        trade_size: float,
        fees_obj=None,
        ml_decay_cost: float = 0.0,
        ml_slippage_cost: float = 0.0,
    ) -> ShadowReceipt:
        """
        Generate a comprehensive receipt for a potential trade.

        Args:
            gross_spread_usd: Raw profit before any fees
            trade_size: Size of trade in USD
            fees_obj: FeeEstimate object from FeeEstimator (optional)
            ml_decay_cost: Calculated ML decay penalty
            ml_slippage_cost: Calculated ML slippage penalty
        """

        if fees_obj:
            # Use detailed estimate if available
            dex_fees = fees_obj.trading_fee_usd
            network_costs = (
                fees_obj.gas_fee_usd
                + fees_obj.priority_fee_usd
                + fees_obj.safety_buffer_usd
            )
            slippage = fees_obj.slippage_cost_usd + ml_slippage_cost
        else:
            # Fallback estimation
            # 1. Variable DEX Fees (Buy Hop + Sell Hop = 0.6% total)
            dex_fees = (trade_size * self.DEX_FEE_RATE) * 2

            # 2. Fixed Network Costs (Gas + Priority + Jito)
            network_costs = 0.12

            # 3. Slippage
            slippage = trade_size * 0.002 + ml_slippage_cost

        # 4. ML Penalty (Decay)
        ml_penalty = ml_decay_cost

        net = gross_spread_usd - (dex_fees + network_costs + slippage + ml_penalty)

        return ShadowReceipt(
            gross_usd=gross_spread_usd,
            dex_fees_usd=dex_fees,
            network_costs_usd=network_costs,
            slippage_usd=slippage,
            ml_penalty_usd=ml_penalty,
            net_final_usd=net,
        )


# Singleton
_shadow_engine = None


def get_shadow_engine():
    global _shadow_engine
    if _shadow_engine is None:
        _shadow_engine = ShadowEngine()
    return _shadow_engine
