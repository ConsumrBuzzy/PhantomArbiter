import requests
from typing import Optional

from src.shared.system.logging import Logger
from src.drift_engine.core.types import DriftMarginMetrics

class DriftMarginMonitor:
    """
    Monitor for Drift Protocol margin health and risk metrics.
    """
    
    def __init__(self, endpoint: str = "https://drift-gateway-api.mainnet.drift.trade"):
        self.base_url = endpoint
    
    def get_metrics(self, wallet: str) -> DriftMarginMetrics:
        """Fetch and calculate margin metrics for a wallet."""
        try:
            if not wallet:
                return DriftMarginMetrics()
            
            url = f"{self.base_url}/v1/user/{wallet}"
            resp = requests.get(url, timeout=2.0)
            
            if resp.status_code != 200:
                Logger.debug(f"[DriftMarginMonitor] API error: {resp.status_code}")
                return DriftMarginMetrics()
            
            data = resp.json()
            
            # Parse collateral values (6 decimals)
            total_collateral = float(data.get("totalCollateralValue", 0)) / 1e6
            free_collateral = float(data.get("freeCollateral", 0)) / 1e6
            maint_margin = float(data.get("maintenanceMarginRequirement", 0)) / 1e6
            init_margin = float(data.get("initialMarginRequirement", 0)) / 1e6
            
            # Health Score = 1 - (Maintenance Margin / Margin Collateral)
            margin_collateral = total_collateral  # Drift uses total collateral as base
            health_score = 1.0
            if margin_collateral > 0 and maint_margin > 0:
                health_score = max(0.0, 1.0 - (maint_margin / margin_collateral))
            
            # Leverage = Notional / Collateral
            # Use deployed capital as proxy for notional since we don't have full positions here
            deployed = max(0.0, total_collateral - free_collateral)
            leverage = deployed / max(total_collateral, 1.0) if total_collateral > 0 else 0.0
            
            return DriftMarginMetrics(
                total_collateral=total_collateral,
                free_collateral=free_collateral,
                maintenance_margin=maint_margin,
                initial_margin=init_margin,
                health_score=health_score,
                leverage=leverage,
                is_healthy=health_score > 0.5,
                liquidation_risk=health_score < 0.2,
            )
            
        except Exception as e:
            Logger.debug(f"[DriftMarginMonitor] Metrics fetch failed: {e}")
            return DriftMarginMetrics()
