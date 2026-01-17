"""
Market Data Provider
===================

Shared market data interface for all trading engines.
Provides consistent access to market data across different sources.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..models.market import MarketSummary, OrderbookSnapshot, MarketData
from src.shared.system.logging import Logger


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    
    Provides a consistent interface for accessing market data
    regardless of the underlying data source (Drift, external APIs, etc.).
    """
    
    def __init__(self):
        self.logger = Logger
        self._cache = {}
        self._cache_ttl = 60  # Default 1 minute cache TTL
    
    # ==========================================================================
    # ABSTRACT METHODS - Must be implemented by concrete providers
    # ==========================================================================
    
    @abstractmethod
    async def get_market_summary(self, market: str) -> Optional[MarketSummary]:
        """
        Get market summary for a specific market.
        
        Args:
            market: Market identifier (e.g., "SOL-PERP")
            
        Returns:
            MarketSummary or None if market not found
        """
        pass
    
    @abstractmethod
    async def get_orderbook_snapshot(self, market: str, depth: int = 10) -> Optional[OrderbookSnapshot]:
        """
        Get orderbook snapshot for a specific market.
        
        Args:
            market: Market identifier
            depth: Number of levels to include on each side
            
        Returns:
            OrderbookSnapshot or None if not available
        """
        pass
    
    @abstractmethod
    async def get_historical_prices(
        self, 
        market: str, 
        start_time: datetime, 
        end_time: datetime,
        resolution: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data.
        
        Args:
            market: Market identifier
            start_time: Start time for data
            end_time: End time for data
            resolution: Data resolution ("1m", "5m", "1h", "1d")
            
        Returns:
            List of OHLCV data points
        """
        pass
    
    @abstractmethod
    async def get_recent_trades(self, market: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent trades for a market.
        
        Args:
            market: Market identifier
            limit: Maximum number of trades to return
            
        Returns:
            List of recent trades
        """
        pass
    
    # ==========================================================================
    # CONCRETE METHODS - Implemented using abstract methods
    # ==========================================================================
    
    async def get_market_data(self, market: str, include_orderbook: bool = True) -> Optional[MarketData]:
        """
        Get comprehensive market data for a market.
        
        Args:
            market: Market identifier
            include_orderbook: Whether to include orderbook data
            
        Returns:
            Complete MarketData object or None
        """
        try:
            # Get market summary
            summary = await self.get_market_summary(market)
            if not summary:
                return None
            
            # Get orderbook if requested
            orderbook = None
            if include_orderbook:
                orderbook = await self.get_orderbook_snapshot(market)
            
            # Get recent trades
            recent_trades = await self.get_recent_trades(market, limit=50)
            
            # Calculate data age
            data_age_ms = (datetime.now() - summary.timestamp).total_seconds() * 1000
            
            # Create market data object
            market_data = MarketData(
                summary=summary,
                orderbook=orderbook,
                recent_trades=recent_trades,
                data_age_ms=data_age_ms,
                data_quality_score=self._calculate_data_quality_score(summary, orderbook, recent_trades)
            )
            
            return market_data
            
        except Exception as e:
            self.logger.error(f"Error getting market data for {market}: {e}")
            return None
    
    async def get_multiple_market_summaries(self, markets: List[str]) -> Dict[str, MarketSummary]:
        """
        Get market summaries for multiple markets.
        
        Args:
            markets: List of market identifiers
            
        Returns:
            Dictionary mapping market -> MarketSummary
        """
        summaries = {}
        
        for market in markets:
            try:
                summary = await self.get_market_summary(market)
                if summary:
                    summaries[market] = summary
            except Exception as e:
                self.logger.error(f"Error getting summary for {market}: {e}")
        
        return summaries
    
    async def get_historical_returns(
        self, 
        market: str, 
        days: int = 30,
        resolution: str = "1d"
    ) -> List[float]:
        """
        Get historical returns for a market.
        
        Args:
            market: Market identifier
            days: Number of days of history
            resolution: Data resolution
            
        Returns:
            List of period returns
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # Get historical prices
            price_data = await self.get_historical_prices(market, start_time, end_time, resolution)
            
            if not price_data or len(price_data) < 2:
                return []
            
            # Calculate returns
            returns = []
            for i in range(1, len(price_data)):
                prev_close = price_data[i-1].get('close', 0)
                curr_close = price_data[i].get('close', 0)
                
                if prev_close > 0:
                    ret = (curr_close - prev_close) / prev_close
                    returns.append(ret)
            
            return returns
            
        except Exception as e:
            self.logger.error(f"Error calculating returns for {market}: {e}")
            return []
    
    async def get_market_volatility(
        self, 
        market: str, 
        window_days: int = 30,
        annualize: bool = True
    ) -> float:
        """
        Calculate market volatility.
        
        Args:
            market: Market identifier
            window_days: Window for volatility calculation
            annualize: Whether to annualize the volatility
            
        Returns:
            Volatility (annualized if requested)
        """
        try:
            returns = await self.get_historical_returns(market, window_days)
            
            if len(returns) < 2:
                return 0.0
            
            # Calculate standard deviation
            from statistics import stdev
            volatility = stdev(returns)
            
            # Annualize if requested
            if annualize:
                import math
                volatility *= math.sqrt(252)  # Assume 252 trading days per year
            
            return volatility
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility for {market}: {e}")
            return 0.0
    
    async def get_correlation_matrix(
        self, 
        markets: List[str], 
        window_days: int = 30
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate correlation matrix between markets.
        
        Args:
            markets: List of market identifiers
            window_days: Window for correlation calculation
            
        Returns:
            Correlation matrix as nested dictionary
        """
        try:
            # Get returns for all markets
            market_returns = {}
            for market in markets:
                returns = await self.get_historical_returns(market, window_days)
                if returns:
                    market_returns[market] = returns
            
            # Calculate correlation matrix
            from ..math.correlation_calculator import CorrelationCalculator
            
            correlation_result = CorrelationCalculator.correlation_matrix(market_returns, window_days)
            return correlation_result.matrix
            
        except Exception as e:
            self.logger.error(f"Error calculating correlation matrix: {e}")
            return {}
    
    async def get_liquidity_metrics(self, market: str) -> Dict[str, float]:
        """
        Calculate liquidity metrics for a market.
        
        Args:
            market: Market identifier
            
        Returns:
            Dictionary of liquidity metrics
        """
        try:
            # Get market data
            market_data = await self.get_market_data(market, include_orderbook=True)
            
            if not market_data or not market_data.orderbook:
                return {}
            
            orderbook = market_data.orderbook
            
            # Calculate liquidity metrics
            metrics = {
                'spread_bps': orderbook.spread_bps,
                'bid_liquidity': orderbook.calculate_liquidity('bid', 10),
                'ask_liquidity': orderbook.calculate_liquidity('ask', 10),
                'total_liquidity': 0.0,
                'liquidity_imbalance': 0.0
            }
            
            # Total liquidity
            metrics['total_liquidity'] = metrics['bid_liquidity'] + metrics['ask_liquidity']
            
            # Liquidity imbalance
            if metrics['total_liquidity'] > 0:
                metrics['liquidity_imbalance'] = abs(
                    metrics['bid_liquidity'] - metrics['ask_liquidity']
                ) / metrics['total_liquidity']
            
            # Add volume-based metrics
            if market_data.summary.volume_24h > 0:
                metrics['volume_24h'] = market_data.summary.volume_24h
                metrics['turnover_ratio'] = metrics['total_liquidity'] / market_data.summary.volume_24h
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating liquidity metrics for {market}: {e}")
            return {}
    
    # ==========================================================================
    # CACHING METHODS
    # ==========================================================================
    
    def _get_cache_key(self, method: str, *args) -> str:
        """Generate cache key for method and arguments."""
        return f"{method}:{':'.join(str(arg) for arg in args)}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache:
            return False
        
        cached_time, _ = self._cache[cache_key]
        age_seconds = (datetime.now() - cached_time).total_seconds()
        
        return age_seconds < self._cache_ttl
    
    def _get_from_cache(self, cache_key: str) -> Any:
        """Get data from cache if valid."""
        if self._is_cache_valid(cache_key):
            _, data = self._cache[cache_key]
            return data
        return None
    
    def _set_cache(self, cache_key: str, data: Any) -> None:
        """Set data in cache."""
        self._cache[cache_key] = (datetime.now(), data)
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
    
    def set_cache_ttl(self, ttl_seconds: int) -> None:
        """Set cache TTL in seconds."""
        self._cache_ttl = ttl_seconds
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    def _calculate_data_quality_score(
        self, 
        summary: MarketSummary, 
        orderbook: Optional[OrderbookSnapshot],
        recent_trades: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate data quality score based on available data.
        
        Returns:
            Quality score between 0 and 1
        """
        score = 0.0
        
        # Summary data quality (40% weight)
        if summary:
            summary_score = 0.4
            
            # Check for required fields
            if summary.mark_price > 0:
                summary_score += 0.1
            if summary.volume_24h >= 0:
                summary_score += 0.1
            if summary.timestamp:
                age_minutes = (datetime.now() - summary.timestamp).total_seconds() / 60
                if age_minutes < 5:  # Fresh data
                    summary_score += 0.1
                elif age_minutes < 15:  # Reasonably fresh
                    summary_score += 0.05
            
            score += min(0.4, summary_score)
        
        # Orderbook data quality (35% weight)
        if orderbook:
            orderbook_score = 0.0
            
            if orderbook.bids and orderbook.asks:
                orderbook_score += 0.2
                
                # Check spread reasonableness
                if orderbook.spread_bps < 1000:  # Less than 10% spread
                    orderbook_score += 0.1
                
                # Check depth
                if len(orderbook.bids) >= 5 and len(orderbook.asks) >= 5:
                    orderbook_score += 0.05
            
            score += min(0.35, orderbook_score)
        
        # Recent trades quality (25% weight)
        if recent_trades:
            trades_score = 0.0
            
            if len(recent_trades) > 0:
                trades_score += 0.15
                
                # Check for recent activity
                if len(recent_trades) >= 10:
                    trades_score += 0.1
            
            score += min(0.25, trades_score)
        
        return min(1.0, score)