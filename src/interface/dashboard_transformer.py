"""
Dashboard Transformer
=====================
v1.0: Converts SignalBus signals into optimized payloads for the Web Dashboard.
"""

from typing import Dict, Any, Optional
from src.shared.system.signal_bus import Signal, SignalType

class DashboardTransformer:
    """
    Translates reactive signals into UI-ready states.
    """
    
    @staticmethod
    def transform(signal: Signal) -> Optional[Dict[str, Any]]:
        """
        Main entry point for signal transformation.
        """
        sig_type = signal.type
        data = signal.data
        
        # 1. Arb Opportunities
        if sig_type == SignalType.ARB_OPP:
            return {
                "type": "ARB_OPP",
                "data": {
                    "token": data.get("token", "???"),
                    "route": data.get("route", "???"),
                    "profit_pct": data.get("profit_pct", 0.0),
                    "est_profit_sol": data.get("est_profit_sol", 0.0),
                    "timestamp": signal.timestamp
                }
            }
            
        # 2. Scalp Signals
        elif sig_type == SignalType.SCALP_SIGNAL:
            return {
                "type": "SCALP_SIGNAL",
                "data": {
                    "token": data.get("token", "???"),
                    "signal": data.get("signal_type", "???"),
                    "action": data.get("action", "BUY"),
                    "confidence": data.get("confidence", 0.0),
                    "price": data.get("price", 0.0),
                    "timestamp": signal.timestamp
                }
            }
            
        # 3. Log Updates
        elif sig_type == SignalType.LOG_UPDATE:
            return {
                "type": "LOG_ENTRY",
                "data": {
                    "level": data.get("level", "INFO"),
                    "source": signal.source,
                    "message": data.get("message", ""),
                    "timestamp": signal.timestamp
                }
            }
            
        # 4. System Stats
        elif sig_type == SignalType.SYSTEM_STATS:
            return {
                "type": "SYSTEM_STATS",
                "data": data
            }
            
        # 5. Market Pulse / Intel
        elif sig_type == SignalType.MARKET_INTEL:
            return {
                "type": "MARKET_INTEL",
                "data": data
            }

        # Passthrough unknown but valid signals
        return {
            "type": sig_type.value,
            "data": data,
            "source": signal.source
        }
