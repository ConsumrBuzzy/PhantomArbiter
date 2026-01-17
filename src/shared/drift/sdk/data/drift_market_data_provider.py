"""
Drift Market Data Provider
=========================

Concrete implementation of MarketDataProvider for Drift Protocol.
Integrates with Drift's market data APIs and WebSocket feeds.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .market_data_provider import MarketDataProvider
from ..models.market import MarketSummary, OrderbookSnapshot, OrderbookLevel, MarketStatus
from src.shared.system.logging import Logger


class DriftMarketDataProvider(MarketDataProvider):
    """
    Concrete market data provider for Drift Protocol.
    
    Integrates with Drift's APIs to provide real-time market data,
    orderbook snapshots, and historical price information.
    """
    
    def __init__(self, drift_adapter):
        """
        Initialize Drift market data provider.
        
        Args:
            drift_adapter: DriftAdapter instance for API access
        """
        super().__init__()
        self.drift_adapter = drift_adapter
        self.logger = Logger
        
        # Market data cache with shorter TTL for real-time data
        self.set_cache_ttl(30)  # 30 seconds for market data
        
        self.logger.info("Drift Market Data Provider initialized")
    
    async def get_market_summary(self, market: str) -> Optional[MarketSummary]:
        """
        Get market summary from Drift Protocol.
        
        Args:
            market: Market identifier (e.g., "SOL-PERP")
            
        Returns:
            MarketSummary or None if market not found
        """
        try:
            cache_key = self._get_cache_key("market_summary", market)
            
            # Check cache first
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            # Get market data from Drift
            market_data = await self.drift_adapter.get_market_summary(market)
            
            if not market_data:
                return None
            
            # Convert to our MarketSummary model
            summary = MarketSummary(
                market=market,
                base_asset=self._extract_base_asset(market),
                quote_asset=self._extract_quote_asset(market),
                mark_price=float(market_data.get('mark_price', 0)),
                index_price=float(market_data.get('index_price', 0)) if market_data.get('index_price') else None,
                last_price=float(market_data.get('last_price', 0)) if market_data.get('last_price') else None,
                price_24h_change=float(market_data.get('price_24h_change', 0)),
                price_24h_change_pct=float(market_data.get('price_24h_change_pct', 0)),
                volume_24h=float(market_data.get('volume_24h', 0)),
                high_24h=float(market_data.get('high_24h', 0)) if market_data.get('high_24h') else None,
                low_24h=float(market_data.get('low_24h', 0)) if market_data.get('low_24h') else None,
                funding_rate=float(market_data.get('funding_rate', 0)) if market_data.get('funding_rate') else None,
                predicted_funding_rate=float(market_data.get('predicted_funding_rate', 0)) if market_data.get('predicted_funding_rate') else None,
                funding_rate_timestamp=self._parse_timestamp(market_data.get('funding_rate_timestamp')),
                open_interest=float(market_data.get('open_interest', 0)) if market_data.get('open_interest') else None,
                open_interest_change_24h=float(market_data.get('open_interest_change_24h', 0)) if market_data.get('open_interest_change_24h') else None,
                status=self._parse_market_status(market_data.get('status', 'active')),
                min_order_size=float(market_data.get('min_order_size', 0)),
                tick_size=float(market_data.get('tick_size', 0.0001)),
                step_size=float(market_data.get('step_size', 0.001)),
                timestamp=datetime.now()
            )
            
            # Cache the result
            self._set_cache(cache_key, summary)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting market summary for {market}: {e}")
            return None
    
    async def get_orderbook_snapshot(self, market: str, depth: int = 10) -> Optional[OrderbookSnapshot]:
        """
        Get orderbook snapshot from Drift Protocol.
        
        Args:
            market: Market identifier
            depth: Number of levels to include on each side
            
        Returns:
            OrderbookSnapshot or None if not available
        """
        try:
            cache_key = self._get_cache_key("orderbook", market, depth)
            
            # Check cache (shorter TTL for orderbook)
            if self._is_cache_valid(cache_key):
                cached_data = self._get_from_cache(cache_key)
                if cached_data:
                    return cached_data
            
            # Get orderbook from Drift
            orderbook_data = await self.drift_adapter.get_orderbook(market, depth)
            
            if not orderbook_data:
                return None
            
            # Convert bids and asks
            bids = []
            asks = []
            
            for bid_data in orderbook_data.get('bids', []):
                bid = OrderbookLevel(
                    price=float(bid_data.get('price', 0)),
                    size=float(bid_data.get('size', 0)),
                    orders=int(bid_data.get('orders', 1))
                )
                bids.append(bid)
            
            for ask_data in orderbook_data.get('asks', []):
                ask = OrderbookLevel(
                    price=float(ask_data.get('price', 0)),
                    size=float(ask_data.get('size', 0)),
                    orders=int(ask_data.get('orders', 1))
                )
                asks.append(ask)
            
            # Sort bids (descending) and asks (ascending)
            bids.sort(key=lambda x: x.price, reverse=True)
            asks.sort(key=lambda x: x.price)
            
            snapshot = OrderbookSnapshot(
                market=market,
                timestamp=datetime.now(),
                bids=bids,
                asks=asks,
                sequence_number=orderbook_data.get('sequence_number')
            )
            
            # Cache with shorter TTL for orderbook
            self._set_cache(cache_key, snapshot)
            
            return snapshot
            
        except Exception as e:
            self.logger.error(f"Error getting orderbook for {market}: {e}")
            return None
    
    async def get_historical_prices(
        self, 
        market: str, 
        start_time: datetime, 
        end_time: datetime,
        resolution: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data from Drift Protocol.
        
        Args:
            market: Market identifier
            start_time: Start time for data
            end_time: End time for data
            resolution: Data resolution ("1m", "5m", "1h", "1d")
            
        Returns:
            List of OHLCV data points
        """
        try:
            cache_key = self._get_cache_key("historical_prices", market, start_time.isoformat(), end_time.isoformat(), resolution)
            
            # Check cache (longer TTL for historical data)
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            # Get historical data from Drift
            historical_data = await self.drift_adapter.get_historical_prices(
                market=market,
                start_time=start_time,
                end_time=end_time,
                resolution=resolution
            )
            
            if not historical_data:
                return []
            
            # Convert to standard OHLCV format
            ohlcv_data = []
            for data_point in historical_data:
                ohlcv = {
                    'timestamp': self._parse_timestamp(data_point.get('timestamp')),
                    'open': float(data_point.get('open', 0)),
                    'high': float(data_point.get('high', 0)),
                    'low': float(data_point.get('low', 0)),
                    'close': float(data_point.get('close', 0)),
                    'volume': float(data_point.get('volume', 0))
                }
                ohlcv_data.append(ohlcv)
            
            # Cache the result
            self._set_cache(cache_key, ohlcv_data)
            
            return ohlcv_data
            
        except Exception as e:
            self.logger.error(f"Error getting historical prices for {market}: {e}")
            return []
    
    async def get_recent_trades(self, market: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent trades from Drift Protocol.
        
        Args:
            market: Market identifier
            limit: Maximum number of trades to return
            
        Returns:
            List of recent trades
        """
        try:
            cache_key = self._get_cache_key("recent_trades", market, limit)
            
            # Check cache
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            # Get recent trades from Drift
            trades_data = await self.drift_adapter.get_recent_trades(market, limit)
            
            if not trades_data:
                return []
            
            # Convert to standard trade format
            trades = []
            for trade_data in trades_data:
                trade = {
                    'id': trade_data.get('id'),
                    'timestamp': self._parse_timestamp(trade_data.get('timestamp')),
                    'price': float(trade_data.get('price', 0)),
                    'size': float(trade_data.get('size', 0)),
                    'side': trade_data.get('side', 'unknown'),
                    'market': market
                }
                trades.append(trade)
            
            # Cache the result
            self._set_cache(cache_key, trades)
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Error getting recent trades for {market}: {e}")
            return []
    
    # ==========================================================================
    # DRIFT-SPECIFIC METHODS
    # ==========================================================================
    
    async def get_all_markets(self) -> List[str]:
        """
        Get list of all available markets on Drift.
        
        Returns:
            List of market identifiers
        """
        try:
            markets_data = await self.drift_adapter.get_all_markets()
            
            if not markets_data:
                return []
            
            return [market.get('symbol', '') for market in markets_data if market.get('symbol')]
            
        except Exception as e:
            self.logger.error(f"Error getting all markets: {e}")
            return []
    
    async def get_funding_rates(self, market: str, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get historical funding rates for a perpetual market.
        
        Args:
            market: Market identifier
            hours: Number of hours of history
            
        Returns:
            List of funding rate data points
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            funding_data = await self.drift_adapter.get_funding_rates(
                market=market,
                start_time=start_time,
                end_time=end_time
            )
            
            if not funding_data:
                return []
            
            # Convert to standard format
            funding_rates = []
            for data_point in funding_data:
                funding_rate = {
                    'timestamp': self._parse_timestamp(data_point.get('timestamp')),
                    'funding_rate': float(data_point.get('funding_rate', 0)),
                    'funding_rate_long': float(data_point.get('funding_rate_long', 0)),
                    'funding_rate_short': float(data_point.get('funding_rate_short', 0)),
                    'market': market
                }
                funding_rates.append(funding_rate)
            
            return funding_rates
            
        except Exception as e:
            self.logger.error(f"Error getting funding rates for {market}: {e}")
            return []
    
    async def get_market_stats(self, market: str) -> Dict[str, Any]:
        """
        Get comprehensive market statistics.
        
        Args:
            market: Market identifier
            
        Returns:
            Dictionary with market statistics
        """
        try:
            # Get multiple data sources
            summary = await self.get_market_summary(market)
            orderbook = await self.get_orderbook_snapshot(market, depth=20)
            recent_trades = await self.get_recent_trades(market, limit=50)
            
            stats = {
                'market': market,
                'timestamp': datetime.now().isoformat()
            }
            
            # Add summary stats
            if summary:
                stats.update({
                    'mark_price': summary.mark_price,
                    'volume_24h': summary.volume_24h,
                    'price_change_24h_pct': summary.price_24h_change_pct,
                    'funding_rate': summary.funding_rate,
                    'open_interest': summary.open_interest
                })
            
            # Add orderbook stats
            if orderbook:
                stats.update({
                    'spread_bps': orderbook.spread_bps,
                    'mid_price': orderbook.mid_price,
                    'bid_liquidity': orderbook.calculate_liquidity('bid', 10),
                    'ask_liquidity': orderbook.calculate_liquidity('ask', 10)
                })
            
            # Add trade stats
            if recent_trades:
                trade_sizes = [t['size'] for t in recent_trades]
                stats.update({
                    'recent_trades_count': len(recent_trades),
                    'avg_trade_size': sum(trade_sizes) / len(trade_sizes) if trade_sizes else 0,
                    'last_trade_price': recent_trades[0]['price'] if recent_trades else 0
                })
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting market stats for {market}: {e}")
            return {'market': market, 'error': str(e)}
    
    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================
    
    def _extract_base_asset(self, market: str) -> str:
        """Extract base asset from market identifier."""
        if '-' in market:
            return market.split('-')[0]
        return market
    
    def _extract_quote_asset(self, market: str) -> str:
        """Extract quote asset from market identifier."""
        if '-' in market:
            parts = market.split('-')
            if len(parts) > 1:
                return 'USD' if 'PERP' in parts[1] else parts[1]
        return 'USD'
    
    def _parse_market_status(self, status_str: str) -> MarketStatus:
        """Parse market status string to enum."""
        status_map = {
            'active': MarketStatus.ACTIVE,
            'paused': MarketStatus.PAUSED,
            'delisted': MarketStatus.DELISTED,
            'settlement': MarketStatus.SETTLEMENT
        }
        return status_map.get(status_str.lower(), MarketStatus.ACTIVE)
    
    def _parse_timestamp(self, timestamp_data: Any) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if not timestamp_data:
            return None
        
        try:
            if isinstance(timestamp_data, datetime):
                return timestamp_data
            elif isinstance(timestamp_data, (int, float)):
                # Unix timestamp
                return datetime.fromtimestamp(timestamp_data)
            elif isinstance(timestamp_data, str):
                # ISO format string
                return datetime.fromisoformat(timestamp_data.replace('Z', '+00:00'))
            else:
                return None
        except Exception:
            return None