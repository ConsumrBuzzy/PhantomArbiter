"""
Portfolio Management Example
===========================

Example usage of the new Portfolio & Risk Management components.
Demonstrates basic portfolio analytics, risk calculations, and hedging.

Usage:
    python examples/portfolio_management_example.py
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.shared.drift.portfolio_manager import DriftPortfolioManager, RiskLimits
from src.shared.drift.risk_engine import DriftRiskEngine
from unittest.mock import Mock, AsyncMock


class MockDriftAdapter:
    """Mock DriftAdapter for demonstration purposes."""
    
    def __init__(self):
        self.get_user_account = AsyncMock()
        self.get_positions = AsyncMock()
        self.get_open_orders = AsyncMock()
        
        # Setup sample data
        self.get_user_account.return_value = {
            'total_collateral': 10000.0,
            'unrealized_pnl': 250.0,
            'total_position_value': 3000.0,
            'health': 180.0
        }
        
        self.get_positions.return_value = [
            {
                'market': 'SOL-PERP',
                'base_asset_amount': 20.0,
                'quote_entry_amount': 3000.0,
                'quote_asset_amount': 3000.0,
                'unrealized_pnl': 150.0
            },
            {
                'market': 'BTC-PERP',
                'base_asset_amount': 0.05,
                'quote_entry_amount': 2500.0,
                'quote_asset_amount': 2500.0,
                'unrealized_pnl': 100.0
            }
        ]
        
        self.get_open_orders.return_value = []


class MockTradingManager:
    """Mock TradingManager for demonstration purposes."""
    
    def __init__(self, drift_adapter):
        self.drift_adapter = drift_adapter
        self.place_market_order = AsyncMock()
        self.place_limit_order = AsyncMock()
        
        # Mock successful order placement
        self.place_market_order.return_value = "order_12345"
        self.place_limit_order.return_value = "order_67890"


class MockMarketDataManager:
    """Mock MarketDataManager for demonstration purposes."""
    
    def __init__(self, drift_adapter):
        self.drift_adapter = drift_adapter
        self.get_market_summary = AsyncMock()
        
        # Mock market data
        def mock_market_data(market):
            prices = {
                'SOL-PERP': 150.0,
                'BTC-PERP': 50000.0,
                'ETH-PERP': 3000.0
            }
            return {'mark_price': prices.get(market, 100.0)}
        
        self.get_market_summary.side_effect = mock_market_data


async def demonstrate_portfolio_analytics():
    """Demonstrate portfolio analytics functionality."""
    print("\n=== Portfolio Analytics Demo ===")
    
    # Setup mock components
    drift_adapter = MockDriftAdapter()
    trading_manager = MockTradingManager(drift_adapter)
    market_data_manager = MockMarketDataManager(drift_adapter)
    
    # Create portfolio manager
    portfolio_manager = DriftPortfolioManager(
        drift_adapter=drift_adapter,
        trading_manager=trading_manager,
        market_data_manager=market_data_manager
    )
    
    # Get portfolio summary
    print("📊 Getting portfolio summary...")
    summary = await portfolio_manager.get_portfolio_summary()
    
    print(f"   Total Value: ${summary.total_value:,.2f}")
    print(f"   Unrealized PnL: ${summary.unrealized_pnl:,.2f}")
    print(f"   Leverage: {summary.leverage:.2f}x")
    print(f"   Health Ratio: {summary.health_ratio:.1f}")
    print(f"   Active Positions: {len(summary.positions)}")
    
    # Get position breakdown
    print("\n📈 Analyzing positions...")
    positions = await portfolio_manager.get_position_breakdown()
    
    for position in positions:
        pnl_pct = (position.unrealized_pnl / (position.size * position.entry_price)) * 100 if position.size * position.entry_price > 0 else 0
        print(f"   {position.market}: {position.size:.4f} @ ${position.entry_price:.2f} (PnL: {pnl_pct:+.2f}%)")
    
    return portfolio_manager


async def demonstrate_risk_management():
    """Demonstrate risk management functionality."""
    print("\n=== Risk Management Demo ===")
    
    # Setup components
    drift_adapter = MockDriftAdapter()
    portfolio_manager = await demonstrate_portfolio_analytics()
    
    # Configure risk limits
    print("⚠️  Setting risk limits...")
    risk_limits = RiskLimits(
        max_portfolio_leverage=4.0,
        max_position_size_usd=5000.0,
        min_health_ratio=150.0
    )
    
    await portfolio_manager.set_risk_limits(risk_limits)
    print(f"   Max Leverage: {risk_limits.max_portfolio_leverage}x")
    print(f"   Max Position Size: ${risk_limits.max_position_size_usd:,.0f}")
    print(f"   Min Health Ratio: {risk_limits.min_health_ratio}")
    
    # Check risk violations
    print("\n🔍 Checking risk violations...")
    violations = await portfolio_manager.check_risk_limits()
    
    if violations:
        print(f"   Found {len(violations)} risk violations:")
        for violation in violations:
            print(f"   - {violation.limit_type}: {violation.message}")
            print(f"     Action: {violation.recommended_action}")
    else:
        print("   ✅ No risk violations found")
    
    return portfolio_manager


async def demonstrate_risk_calculations():
    """Demonstrate risk calculation functionality."""
    print("\n=== Risk Calculations Demo ===")
    
    # Setup risk engine
    drift_adapter = MockDriftAdapter()
    risk_engine = DriftRiskEngine(drift_adapter, lookback_days=100)
    
    # Calculate VaR
    print("📉 Calculating Value at Risk...")
    var_result = await risk_engine.calculate_var(confidence_level=0.95)
    
    print(f"   1-Day VaR (95%): ${var_result.var_1d:,.2f}")
    print(f"   7-Day VaR (95%): ${var_result.var_7d:,.2f}")
    print(f"   Portfolio Value: ${var_result.portfolio_value:,.2f}")
    
    # Calculate performance metrics
    print("\n📊 Calculating performance metrics...")
    performance = await risk_engine.calculate_performance_metrics()
    
    print(f"   Annualized Return: {performance.annualized_return:.2%}")
    print(f"   Volatility: {performance.volatility:.2%}")
    print(f"   Sharpe Ratio: {performance.sharpe_ratio:.2f}")
    print(f"   Max Drawdown: {performance.max_drawdown:.2%}")
    print(f"   Win Rate: {performance.win_rate:.1%}")
    
    # Calculate correlation matrix
    print("\n🔗 Calculating correlation matrix...")
    correlation_matrix = await risk_engine.calculate_correlation_matrix()
    
    print(f"   Assets analyzed: {len(correlation_matrix.assets)}")
    if correlation_matrix.assets:
        print("   Sample correlations:")
        for i, asset1 in enumerate(correlation_matrix.assets[:3]):
            for j, asset2 in enumerate(correlation_matrix.assets[:3]):
                if i < j:
                    corr = correlation_matrix.matrix[asset1][asset2]
                    print(f"     {asset1} vs {asset2}: {corr:.3f}")


async def demonstrate_hedging():
    """Demonstrate automated hedging functionality."""
    print("\n=== Automated Hedging Demo ===")
    
    # Get portfolio manager from previous demo
    portfolio_manager = await demonstrate_risk_management()
    
    # Calculate current portfolio delta
    print("⚖️  Analyzing portfolio delta...")
    positions = await portfolio_manager.get_position_breakdown()
    current_delta = sum(pos.size for pos in positions)
    
    print(f"   Current Portfolio Delta: {current_delta:.4f}")
    print(f"   Target Delta: 0.0000 (delta-neutral)")
    
    # Execute auto-hedging
    if abs(current_delta) > 0.01:  # If delta > 1%
        print("\n🔄 Executing auto-hedge...")
        order_ids = await portfolio_manager.auto_hedge_portfolio(target_delta=0.0)
        
        if order_ids:
            print(f"   ✅ Placed {len(order_ids)} hedge orders:")
            for order_id in order_ids:
                print(f"     - Order ID: {order_id}")
        else:
            print("   ❌ Failed to place hedge orders")
    else:
        print("   ✅ Portfolio delta within tolerance, no hedging needed")


async def demonstrate_position_sizing():
    """Demonstrate position sizing functionality."""
    print("\n=== Position Sizing Demo ===")
    
    # Get portfolio manager
    portfolio_manager = await demonstrate_risk_management()
    
    # Get position sizing recommendations
    markets = ['SOL-PERP', 'BTC-PERP', 'ETH-PERP']
    
    print("📏 Calculating optimal position sizes...")
    
    for market in markets:
        try:
            sizing = await portfolio_manager.suggest_position_sizes(
                market=market,
                strategy="momentum",
                risk_tolerance=0.6
            )
            
            print(f"   {market}:")
            print(f"     Recommended Size: {sizing.recommended_size:.4f}")
            print(f"     Max Size: {sizing.max_size:.4f}")
            print(f"     Risk-Adjusted Size: {sizing.risk_adjusted_size:.4f}")
            print(f"     Confidence: {sizing.confidence:.1%}")
            
        except Exception as e:
            print(f"   {market}: Error calculating sizing - {e}")


async def main():
    """Run all demonstrations."""
    print("🚀 Portfolio & Risk Management System Demo")
    print("=" * 50)
    
    try:
        # Run all demonstrations
        await demonstrate_portfolio_analytics()
        await demonstrate_risk_management()
        await demonstrate_risk_calculations()
        await demonstrate_hedging()
        await demonstrate_position_sizing()
        
        print("\n" + "=" * 50)
        print("✅ Demo completed successfully!")
        print("\nNext steps:")
        print("1. Integrate with real DriftAdapter")
        print("2. Configure risk limits for your strategy")
        print("3. Enable automated hedging and rebalancing")
        print("4. Monitor portfolio risk in real-time")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())