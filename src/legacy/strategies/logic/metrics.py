"""
Strategy Metrics
================
Pure functions for calculating PnL and other trading metrics.
Moved from Watcher.py as part of V10.2 SRP Refactor.
"""


class Metrics:
    @staticmethod
    def calculate_pnl_pct(
        entry_price: float, current_price: float, cost_basis: float = 0.0
    ) -> float:
        """
        Calculate gross PnL percentage.
        Cost basis used for weighting if needed, but standard PnL is just price delta.
        """
        if entry_price > 0:
            # We use simple price delta for PnL %
            return (current_price - entry_price) / entry_price
        return 0.0

    @staticmethod
    def calculate_net_pnl_pct(
        entry_price: float, current_price: float, cost_basis: float
    ) -> float:
        """
        Calculate fee-aware net PnL.
        Accounts for ~0.5% buy fee and ~0.5% estimated sell fee.
        """
        BUY_FEE = 0.005  # 0.5% (DEX + priority)
        SELL_FEE = 0.005  # 0.5% (DEX + priority)

        if entry_price > 0:
            cost = cost_basis if cost_basis > 0 else 5.0
            actual_cost = cost * (1 + BUY_FEE)

            tokens = cost / entry_price
            current_value = tokens * current_price
            net_return = current_value * (1 - SELL_FEE)

            return (net_return - actual_cost) / actual_cost
        return 0.0
