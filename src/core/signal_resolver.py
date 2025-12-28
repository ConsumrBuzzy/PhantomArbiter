"""
V133: SignalResolver - Extracted from DataBroker (SRP Refactor)
================================================================
Handles signal consensus and conflict resolution.

Responsibilities:
- Group signals by symbol
- Resolve conflicting signals (BUY vs SELL)
- Apply priority rankings
"""

from typing import List, Dict, Any
from src.shared.system.logging import Logger


class SignalResolver:
    """
    V133: Resolves conflicts between multiple trading signals.
    
    Currently implements passthrough logic (Ensemble Strategy handles
    conflict internally). Ready for future expansion with:
    - Per-symbol vote aggregation
    - Confidence-weighted consensus
    - Multi-engine conflict resolution
    """
    
    def __init__(self):
        """Initialize SignalResolver."""
        self._resolution_stats = {
            'signals_received': 0,
            'signals_resolved': 0,
            'conflicts_detected': 0
        }
    
    def resolve(self, signals: List[Dict]) -> List[Dict]:
        """
        Resolve signal conflicts and return executable signals.
        
        Args:
            signals: List of signal dicts from all engines
            
        Returns:
            List of resolved signals to execute
        """
        if not signals:
            return []
        
        self._resolution_stats['signals_received'] += len(signals)
        
        # Group by symbol
        by_symbol = self._group_by_symbol(signals)
        
        # Resolve conflicts per symbol
        final_signals = []
        for symbol, symbol_signals in by_symbol.items():
            resolved = self._resolve_symbol(symbol, symbol_signals)
            if resolved:
                final_signals.extend(resolved)
        
        self._resolution_stats['signals_resolved'] += len(final_signals)
        
        return final_signals
    
    def _group_by_symbol(self, signals: List[Dict]) -> Dict[str, List[Dict]]:
        """Group signals by symbol."""
        by_symbol = {}
        for s in signals:
            sym = s.get('symbol', 'UNKNOWN')
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(s)
        return by_symbol
    
    def _resolve_symbol(self, symbol: str, signals: List[Dict]) -> List[Dict]:
        """
        Resolve conflicts for a single symbol.
        
        Current implementation: Passthrough (Ensemble handles internally)
        Future: Could implement voting, confidence-weighted consensus, etc.
        """
        if len(signals) == 1:
            return signals
        
        # Check for action conflicts
        actions = set(s.get('action') for s in signals)
        if len(actions) > 1:
            self._resolution_stats['conflicts_detected'] += 1
            # Currently: Pass all through (let executor decide)
            # Future: Vote, average confidence, pick highest, etc.
            Logger.debug(f"[RESOLVER] Conflict on {symbol}: {actions}")
        
        return signals  # Passthrough for now
    
    def get_stats(self) -> Dict:
        """Return resolution statistics."""
        return self._resolution_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset resolution statistics."""
        self._resolution_stats = {
            'signals_received': 0,
            'signals_resolved': 0,
            'conflicts_detected': 0
        }
