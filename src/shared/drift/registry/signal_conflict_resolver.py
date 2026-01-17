"""
Signal Conflict Resolver
========================

Resolves conflicts between trade signals from multiple engines.
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ..sdk.models.trading import TradeSignal, OrderSide
from ..sdk.models.portfolio import PortfolioState
from ..sdk.data.market_data_provider import MarketDataProvider
from ..sdk.data.portfolio_data_provider import PortfolioDataProvider
from src.shared.system.logging import Logger


class ConflictType(Enum):
    """Types of signal conflicts."""
    OPPOSING_SIDES = "opposing_sides"  # Buy vs Sell same market
    SIZE_CONFLICT = "size_conflict"  # Different sizes for same market/side
    TIMING_CONFLICT = "timing_conflict"  # Multiple signals close in time
    CORRELATION_CONFLICT = "correlation_conflict"  # Highly correlated markets
    RISK_CONFLICT = "risk_conflict"  # Combined signals exceed risk limits


class ResolutionStrategy(Enum):
    """Conflict resolution strategies."""
    PRIORITY_BASED = "priority_based"  # Use engine priority
    SIZE_WEIGHTED = "size_weighted"  # Weight by signal size
    CONFIDENCE_BASED = "confidence_based"  # Use signal confidence
    RISK_ADJUSTED = "risk_adjusted"  # Minimize risk
    COMBINED = "combined"  # Combine compatible signals
    CANCEL_ALL = "cancel_all"  # Cancel conflicting signals


@dataclass
class ConflictResolution:
    """Result of conflict resolution."""
    
    conflict_type: ConflictType
    resolution_strategy: ResolutionStrategy
    original_signals: List[TradeSignal]
    resolved_signals: List[TradeSignal]
    cancelled_signals: List[TradeSignal]
    
    # Resolution details
    resolution_reason: str
    confidence_score: float  # 0-1 confidence in resolution
    risk_impact: float  # Estimated risk impact
    
    # Metadata
    resolution_time: datetime
    resolver_version: str = "1.0"


class SignalConflictResolver:
    """
    Resolves conflicts between trade signals from multiple engines.
    
    Analyzes signals for conflicts and applies resolution strategies
    to produce a coherent set of trade signals.
    """
    
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        portfolio_data_provider: PortfolioDataProvider
    ):
        """
        Initialize signal conflict resolver.
        
        Args:
            market_data_provider: Market data provider
            portfolio_data_provider: Portfolio data provider
        """
        self.market_data = market_data_provider
        self.portfolio_data = portfolio_data_provider
        self.logger = Logger
        
        # Configuration
        self.default_resolution_strategy = ResolutionStrategy.PRIORITY_BASED
        self.correlation_threshold = 0.7  # Threshold for correlation conflicts
        self.timing_window_minutes = 5  # Window for timing conflicts
        
        self.logger.info("Signal Conflict Resolver initialized")
    
    async def resolve_conflicts(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]],
        engine_priorities: Optional[Dict[str, int]] = None
    ) -> List[ConflictResolution]:
        """
        Resolve conflicts between signals from multiple engines.
        
        Args:
            engine_signals: List of (engine_name, signal) tuples
            engine_priorities: Optional engine priority mapping
            
        Returns:
            List of conflict resolutions
        """
        try:
            self.logger.info(f"Resolving conflicts for {len(engine_signals)} signals")
            
            if not engine_signals:
                return []
            
            # Group signals by market
            market_signals = self._group_signals_by_market(engine_signals)
            
            # Detect conflicts
            conflicts = await self._detect_conflicts(engine_signals, market_signals)
            
            if not conflicts:
                self.logger.info("No conflicts detected")
                return []
            
            # Resolve each conflict
            resolutions = []
            for conflict_data in conflicts:
                resolution = await self._resolve_single_conflict(
                    conflict_data, 
                    engine_priorities or {}
                )
                resolutions.append(resolution)
            
            self.logger.info(f"Resolved {len(resolutions)} conflicts")
            return resolutions
            
        except Exception as e:
            self.logger.error(f"Error resolving signal conflicts: {e}")
            return []
    
    async def get_final_signals(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]],
        engine_priorities: Optional[Dict[str, int]] = None
    ) -> List[TradeSignal]:
        """
        Get final resolved signals after conflict resolution.
        
        Args:
            engine_signals: List of (engine_name, signal) tuples
            engine_priorities: Optional engine priority mapping
            
        Returns:
            List of resolved trade signals
        """
        try:
            # Resolve conflicts
            resolutions = await self.resolve_conflicts(engine_signals, engine_priorities)
            
            # Start with all original signals
            final_signals = [signal for _, signal in engine_signals]
            
            # Apply resolutions
            for resolution in resolutions:
                # Remove original conflicting signals
                for original_signal in resolution.original_signals:
                    if original_signal in final_signals:
                        final_signals.remove(original_signal)
                
                # Add resolved signals
                final_signals.extend(resolution.resolved_signals)
            
            self.logger.info(f"Final signal count: {len(final_signals)} (from {len(engine_signals)} original)")
            return final_signals
            
        except Exception as e:
            self.logger.error(f"Error getting final signals: {e}")
            return [signal for _, signal in engine_signals]  # Return original signals on error
    
    # ==========================================================================
    # CONFLICT DETECTION
    # ==========================================================================
    
    def _group_signals_by_market(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]]
    ) -> Dict[str, List[Tuple[str, TradeSignal]]]:
        """Group signals by market."""
        market_signals = {}
        
        for engine_name, signal in engine_signals:
            market = signal.market
            if market not in market_signals:
                market_signals[market] = []
            market_signals[market].append((engine_name, signal))
        
        return market_signals
    
    async def _detect_conflicts(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]],
        market_signals: Dict[str, List[Tuple[str, TradeSignal]]]
    ) -> List[Dict[str, Any]]:
        """Detect various types of conflicts."""
        conflicts = []
        
        # 1. Detect opposing sides conflicts
        opposing_conflicts = self._detect_opposing_sides(market_signals)
        conflicts.extend(opposing_conflicts)
        
        # 2. Detect size conflicts
        size_conflicts = self._detect_size_conflicts(market_signals)
        conflicts.extend(size_conflicts)
        
        # 3. Detect timing conflicts
        timing_conflicts = self._detect_timing_conflicts(engine_signals)
        conflicts.extend(timing_conflicts)
        
        # 4. Detect correlation conflicts
        correlation_conflicts = await self._detect_correlation_conflicts(engine_signals)
        conflicts.extend(correlation_conflicts)
        
        return conflicts
    
    def _detect_opposing_sides(
        self, 
        market_signals: Dict[str, List[Tuple[str, TradeSignal]]]
    ) -> List[Dict[str, Any]]:
        """Detect opposing buy/sell signals for same market."""
        conflicts = []
        
        for market, signals in market_signals.items():
            if len(signals) < 2:
                continue
            
            # Group by side
            buy_signals = []
            sell_signals = []
            
            for engine_name, signal in signals:
                if signal.side == OrderSide.BUY:
                    buy_signals.append((engine_name, signal))
                else:
                    sell_signals.append((engine_name, signal))
            
            # Check for opposing sides
            if buy_signals and sell_signals:
                conflicts.append({
                    'type': ConflictType.OPPOSING_SIDES,
                    'market': market,
                    'buy_signals': buy_signals,
                    'sell_signals': sell_signals,
                    'all_signals': signals
                })
        
        return conflicts
    
    def _detect_size_conflicts(
        self, 
        market_signals: Dict[str, List[Tuple[str, TradeSignal]]]
    ) -> List[Dict[str, Any]]:
        """Detect size conflicts for same market/side."""
        conflicts = []
        
        for market, signals in market_signals.items():
            if len(signals) < 2:
                continue
            
            # Group by side
            side_groups = {}
            for engine_name, signal in signals:
                side = signal.side
                if side not in side_groups:
                    side_groups[side] = []
                side_groups[side].append((engine_name, signal))
            
            # Check for size conflicts within each side
            for side, side_signals in side_groups.items():
                if len(side_signals) < 2:
                    continue
                
                sizes = [signal.size for _, signal in side_signals]
                
                # Check if sizes differ significantly
                min_size = min(sizes)
                max_size = max(sizes)
                
                if max_size > min_size * 1.5:  # 50% difference threshold
                    conflicts.append({
                        'type': ConflictType.SIZE_CONFLICT,
                        'market': market,
                        'side': side,
                        'signals': side_signals,
                        'size_range': (min_size, max_size)
                    })
        
        return conflicts
    
    def _detect_timing_conflicts(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]]
    ) -> List[Dict[str, Any]]:
        """Detect timing conflicts (multiple signals close in time)."""
        conflicts = []
        
        # Sort signals by creation time
        sorted_signals = sorted(
            engine_signals,
            key=lambda x: x[1].created_at
        )
        
        # Look for signals within timing window
        for i, (engine1, signal1) in enumerate(sorted_signals):
            close_signals = [(engine1, signal1)]
            
            for j in range(i + 1, len(sorted_signals)):
                engine2, signal2 = sorted_signals[j]
                
                time_diff = (signal2.created_at - signal1.created_at).total_seconds() / 60
                
                if time_diff <= self.timing_window_minutes:
                    close_signals.append((engine2, signal2))
                else:
                    break  # Signals are sorted, so no more close signals
            
            if len(close_signals) > 1:
                conflicts.append({
                    'type': ConflictType.TIMING_CONFLICT,
                    'signals': close_signals,
                    'time_window_minutes': self.timing_window_minutes
                })
        
        return conflicts
    
    async def _detect_correlation_conflicts(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]]
    ) -> List[Dict[str, Any]]:
        """Detect correlation conflicts (highly correlated markets)."""
        conflicts = []
        
        try:
            # Get unique markets
            markets = list(set(signal.market for _, signal in engine_signals))
            
            if len(markets) < 2:
                return conflicts
            
            # Get correlation matrix
            correlation_matrix = await self.market_data.get_correlation_matrix(markets, window_days=30)
            
            if not correlation_matrix:
                return conflicts
            
            # Find highly correlated market pairs
            for i, market1 in enumerate(markets):
                for j, market2 in enumerate(markets[i+1:], i+1):
                    correlation = correlation_matrix.get(market1, {}).get(market2, 0.0)
                    
                    if abs(correlation) > self.correlation_threshold:
                        # Find signals for these markets
                        market1_signals = [(e, s) for e, s in engine_signals if s.market == market1]
                        market2_signals = [(e, s) for e, s in engine_signals if s.market == market2]
                        
                        if market1_signals and market2_signals:
                            conflicts.append({
                                'type': ConflictType.CORRELATION_CONFLICT,
                                'market1': market1,
                                'market2': market2,
                                'correlation': correlation,
                                'market1_signals': market1_signals,
                                'market2_signals': market2_signals
                            })
            
        except Exception as e:
            self.logger.error(f"Error detecting correlation conflicts: {e}")
        
        return conflicts
    
    # ==========================================================================
    # CONFLICT RESOLUTION
    # ==========================================================================
    
    async def _resolve_single_conflict(
        self, 
        conflict_data: Dict[str, Any],
        engine_priorities: Dict[str, int]
    ) -> ConflictResolution:
        """Resolve a single conflict."""
        conflict_type = conflict_data['type']
        
        if conflict_type == ConflictType.OPPOSING_SIDES:
            return await self._resolve_opposing_sides(conflict_data, engine_priorities)
        elif conflict_type == ConflictType.SIZE_CONFLICT:
            return await self._resolve_size_conflict(conflict_data, engine_priorities)
        elif conflict_type == ConflictType.TIMING_CONFLICT:
            return await self._resolve_timing_conflict(conflict_data, engine_priorities)
        elif conflict_type == ConflictType.CORRELATION_CONFLICT:
            return await self._resolve_correlation_conflict(conflict_data, engine_priorities)
        else:
            return self._create_default_resolution(conflict_data)
    
    async def _resolve_opposing_sides(
        self, 
        conflict_data: Dict[str, Any],
        engine_priorities: Dict[str, int]
    ) -> ConflictResolution:
        """Resolve opposing buy/sell signals."""
        buy_signals = conflict_data['buy_signals']
        sell_signals = conflict_data['sell_signals']
        
        # Calculate net position
        total_buy_size = sum(signal.size for _, signal in buy_signals)
        total_sell_size = sum(signal.size for _, signal in sell_signals)
        
        net_size = total_buy_size - total_sell_size
        
        original_signals = [signal for _, signal in buy_signals + sell_signals]
        
        if abs(net_size) < min(total_buy_size, total_sell_size) * 0.1:  # Nearly equal
            # Cancel all signals if nearly equal
            return ConflictResolution(
                conflict_type=ConflictType.OPPOSING_SIDES,
                resolution_strategy=ResolutionStrategy.CANCEL_ALL,
                original_signals=original_signals,
                resolved_signals=[],
                cancelled_signals=original_signals,
                resolution_reason="Opposing signals with similar sizes cancelled",
                confidence_score=0.8,
                risk_impact=0.0,
                resolution_time=datetime.now()
            )
        else:
            # Keep the net position using highest priority engine
            if net_size > 0:
                # Net buy position
                best_buy_signal = self._select_best_signal(buy_signals, engine_priorities)
                best_buy_signal.size = net_size
                resolved_signals = [best_buy_signal]
            else:
                # Net sell position
                best_sell_signal = self._select_best_signal(sell_signals, engine_priorities)
                best_sell_signal.size = abs(net_size)
                resolved_signals = [best_sell_signal]
            
            return ConflictResolution(
                conflict_type=ConflictType.OPPOSING_SIDES,
                resolution_strategy=ResolutionStrategy.COMBINED,
                original_signals=original_signals,
                resolved_signals=resolved_signals,
                cancelled_signals=[s for s in original_signals if s not in resolved_signals],
                resolution_reason=f"Combined opposing signals into net position: {net_size:.2f}",
                confidence_score=0.7,
                risk_impact=abs(net_size) / max(total_buy_size, total_sell_size),
                resolution_time=datetime.now()
            )
    
    async def _resolve_size_conflict(
        self, 
        conflict_data: Dict[str, Any],
        engine_priorities: Dict[str, int]
    ) -> ConflictResolution:
        """Resolve size conflicts for same market/side."""
        signals = conflict_data['signals']
        
        # Use priority-based selection or average sizing
        if engine_priorities:
            best_signal = self._select_best_signal(signals, engine_priorities)
            resolved_signals = [best_signal]
            strategy = ResolutionStrategy.PRIORITY_BASED
            reason = f"Selected signal from highest priority engine"
        else:
            # Average the sizes
            avg_size = sum(signal.size for _, signal in signals) / len(signals)
            best_signal = self._select_best_signal(signals, {})
            best_signal.size = avg_size
            resolved_signals = [best_signal]
            strategy = ResolutionStrategy.SIZE_WEIGHTED
            reason = f"Averaged signal sizes: {avg_size:.2f}"
        
        original_signals = [signal for _, signal in signals]
        
        return ConflictResolution(
            conflict_type=ConflictType.SIZE_CONFLICT,
            resolution_strategy=strategy,
            original_signals=original_signals,
            resolved_signals=resolved_signals,
            cancelled_signals=[s for s in original_signals if s not in resolved_signals],
            resolution_reason=reason,
            confidence_score=0.6,
            risk_impact=0.2,
            resolution_time=datetime.now()
        )
    
    async def _resolve_timing_conflict(
        self, 
        conflict_data: Dict[str, Any],
        engine_priorities: Dict[str, int]
    ) -> ConflictResolution:
        """Resolve timing conflicts."""
        signals = conflict_data['signals']
        
        # Select the most recent signal from highest priority engine
        best_signal = self._select_best_signal(signals, engine_priorities)
        
        original_signals = [signal for _, signal in signals]
        
        return ConflictResolution(
            conflict_type=ConflictType.TIMING_CONFLICT,
            resolution_strategy=ResolutionStrategy.PRIORITY_BASED,
            original_signals=original_signals,
            resolved_signals=[best_signal],
            cancelled_signals=[s for s in original_signals if s != best_signal],
            resolution_reason="Selected most recent signal from highest priority engine",
            confidence_score=0.7,
            risk_impact=0.1,
            resolution_time=datetime.now()
        )
    
    async def _resolve_correlation_conflict(
        self, 
        conflict_data: Dict[str, Any],
        engine_priorities: Dict[str, int]
    ) -> ConflictResolution:
        """Resolve correlation conflicts."""
        market1_signals = conflict_data['market1_signals']
        market2_signals = conflict_data['market2_signals']
        correlation = conflict_data['correlation']
        
        all_signals = market1_signals + market2_signals
        
        # If correlation is positive and signals are in same direction, combine
        # If correlation is negative or signals oppose, select best
        
        market1_sides = [signal.side for _, signal in market1_signals]
        market2_sides = [signal.side for _, signal in market2_signals]
        
        same_direction = len(set(market1_sides + market2_sides)) == 1
        
        original_signals = [signal for _, signal in all_signals]
        
        if correlation > 0 and same_direction:
            # Positive correlation, same direction - keep both but reduce sizes
            resolved_signals = []
            for _, signal in all_signals:
                reduced_signal = signal
                reduced_signal.size *= 0.7  # Reduce size due to correlation
                resolved_signals.append(reduced_signal)
            
            return ConflictResolution(
                conflict_type=ConflictType.CORRELATION_CONFLICT,
                resolution_strategy=ResolutionStrategy.RISK_ADJUSTED,
                original_signals=original_signals,
                resolved_signals=resolved_signals,
                cancelled_signals=[],
                resolution_reason=f"Reduced position sizes due to high correlation ({correlation:.2f})",
                confidence_score=0.6,
                risk_impact=0.3,
                resolution_time=datetime.now()
            )
        else:
            # Select best signal to avoid correlation risk
            best_signal = self._select_best_signal(all_signals, engine_priorities)
            
            return ConflictResolution(
                conflict_type=ConflictType.CORRELATION_CONFLICT,
                resolution_strategy=ResolutionStrategy.PRIORITY_BASED,
                original_signals=original_signals,
                resolved_signals=[best_signal],
                cancelled_signals=[s for s in original_signals if s != best_signal],
                resolution_reason=f"Selected single position to avoid correlation risk ({correlation:.2f})",
                confidence_score=0.8,
                risk_impact=0.2,
                resolution_time=datetime.now()
            )
    
    def _create_default_resolution(self, conflict_data: Dict[str, Any]) -> ConflictResolution:
        """Create default resolution for unknown conflict types."""
        return ConflictResolution(
            conflict_type=conflict_data.get('type', ConflictType.RISK_CONFLICT),
            resolution_strategy=ResolutionStrategy.CANCEL_ALL,
            original_signals=[],
            resolved_signals=[],
            cancelled_signals=[],
            resolution_reason="Unknown conflict type - cancelled all signals",
            confidence_score=0.0,
            risk_impact=0.0,
            resolution_time=datetime.now()
        )
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    def _select_best_signal(
        self, 
        engine_signals: List[Tuple[str, TradeSignal]],
        engine_priorities: Dict[str, int]
    ) -> TradeSignal:
        """Select best signal based on priority and other factors."""
        if not engine_signals:
            raise ValueError("No signals to select from")
        
        if len(engine_signals) == 1:
            return engine_signals[0][1]
        
        # Sort by priority (highest first), then by signal strength
        def signal_score(engine_signal):
            engine_name, signal = engine_signal
            priority = engine_priorities.get(engine_name, 0)
            signal_strength = getattr(signal, 'signal_strength', 0.5)
            return (priority, signal_strength, -signal.created_at.timestamp())  # Negative for most recent
        
        sorted_signals = sorted(engine_signals, key=signal_score, reverse=True)
        return sorted_signals[0][1]