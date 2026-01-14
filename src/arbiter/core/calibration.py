"""
Calibration Module
==================
ML-informed thresholds and bootstrap defaults for pair-level trading decisions.
Extracted from arbiter.py for modularity.
"""

import time


# Bootstrap defaults based on observed data (used until ML has enough samples)
# These protect against wasted gas on pairs with known issues
BOOTSTRAP_MIN_SPREADS = {
    "PIPPIN": 4.0,  # Observed extreme slippage: +$0.21 scan → -$0.34 quote
    "PNUT": 1.8,  # Observed 1.2% → reverts with -$0.13
    "ACT": 2.5,  # High LIQ failure rate
    "GOAT": 2.0,  # V88.0: Observed consistent ~$0.44 quote loss
    "FWOG": 2.0,  # V88.0: Similar decay pattern
}


def get_pair_threshold(pair: str, default: float = 0.12) -> float:
    """
    Get ML-informed fast-path threshold for a specific pair.

    Uses historical profit_delta from fast_path_attempts table to calculate
    the required buffer for each pair.

    Returns: minimum scan profit required for fast-path execution
    """
    try:
        from src.shared.system.db_manager import db_manager

        with db_manager.cursor() as c:
            # Get average profit_delta for this pair (last 24 hours)
            c.execute(
                """
            SELECT 
                AVG(profit_delta) as avg_delta,
                COUNT(*) as attempts
            FROM fast_path_attempts 
            WHERE pair LIKE ? AND timestamp > ?
            """,
                (f"{pair.split('/')[0]}%", time.time() - 86400),
            )

            row = c.fetchone()
            if row and row["attempts"] and row["attempts"] >= 3:
                avg_delta = row["avg_delta"] or 0
                # Required threshold = enough to absorb average decay + safety margin
                # If avg_delta is -0.10, we need at least +0.12 at scan time
                required = abs(avg_delta) + 0.02  # 2 cent safety margin

                # Sanity Check: Cap at $0.50
                # If we need >$0.50 buffer, the pair is too volatile for fast path
                final = max(required, default)
                return min(final, 0.50)

        return default

    except Exception:
        return default


def get_bootstrap_min_spread(pair: str) -> float:
    """
    Get bootstrap minimum spread for a pair based on observations.
    Returns 0.0 if no bootstrap default (allows all spreads).
    """
    base_token = pair.split("/")[0]
    return BOOTSTRAP_MIN_SPREADS.get(base_token, 0.0)
