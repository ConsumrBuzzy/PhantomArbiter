"""
Phantom Arbiter - Opportunity Alert System
===========================================
Continuously monitors for:
1. Spatial spreads > 0.2% (quick flip opportunities)
2. Funding rate spikes > 20% APY (enter funding arb)
3. Volatility events (liquidation cascades = funding spikes)

Also includes Jito bundle preparation for MEV protection.

Usage:
    python run_opportunity_alerts.py
    python run_opportunity_alerts.py --min-spread 0.3 --min-apr 25
"""

import asyncio
import time
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from config.settings import Settings
from src.system.logging import Logger


@dataclass
class OpportunityAlert:
    """An actionable opportunity detected."""
    alert_type: str          # "SPATIAL", "FUNDING_SPIKE", "VOLATILITY"
    coin: str
    details: str
    profit_potential: float
    urgency: str             # "IMMEDIATE", "SOON", "MONITOR"
    action: str              # What to do
    timestamp: float = field(default_factory=time.time)
    
    def __str__(self) -> str:
        emoji = {
            "IMMEDIATE": "🚨",
            "SOON": "⚠️",
            "MONITOR": "👀"
        }.get(self.urgency, "ℹ️")
        
        return (
            f"\n{emoji} {self.alert_type} ALERT: {self.coin}\n"
            f"   {self.details}\n"
            f"   Potential: ${self.profit_potential:.2f}\n"
            f"   Action: {self.action}\n"
        )


class OpportunityScanner:
    """
    Scans for all types of arbitrage opportunities.
    
    Combines:
    - Spatial spread detection
    - Funding rate monitoring
    - Volatility spike detection
    """
    
    # Thresholds
    MIN_SPATIAL_SPREAD = 0.20    # 0.2% minimum for spatial
    MIN_FUNDING_APR = 20.0       # 20% APY minimum for funding
    VOLATILITY_THRESHOLD = 5.0  # 5% price move in 1 hour
    
    def __init__(self):
        self.last_prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[tuple]] = {}  # coin -> [(time, price), ...]
        self.alerts: List[OpportunityAlert] = []
        
    async def scan_spatial_opportunities(self, budget: float = 100.0) -> List[OpportunityAlert]:
        """Scan for cross-DEX spread opportunities."""
        alerts = []
        
        try:
            from src.arbitrage.core.spread_detector import SpreadDetector
            from src.arbitrage.feeds.jupiter_feed import JupiterFeed
            from src.arbitrage.feeds.raydium_feed import RaydiumFeed
            from src.arbitrage.feeds.orca_feed import OrcaFeed
            
            detector = SpreadDetector(feeds=[
                JupiterFeed(),
                RaydiumFeed(),
                OrcaFeed(use_on_chain=False),
            ])
            
            # Pairs to scan
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            pairs = [
                ("SOL/USDC", "So11111111111111111111111111111111111111112", USDC),
                ("BONK/USDC", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", USDC),
                ("WIF/USDC", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", USDC),
                ("JUP/USDC", "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", USDC),
            ]
            
            opportunities = detector.scan_all_pairs(pairs)
            
            for opp in opportunities:
                if opp.spread_pct >= self.MIN_SPATIAL_SPREAD:
                    # Calculate net profit
                    gross = budget * (opp.spread_pct / 100)
                    fees = budget * 0.002  # 0.1% x 2
                    net = gross - fees
                    
                    if net > 0:
                        alerts.append(OpportunityAlert(
                            alert_type="SPATIAL",
                            coin=opp.pair,
                            details=f"Buy {opp.buy_dex} @ ${opp.buy_price:.6f} → Sell {opp.sell_dex} @ ${opp.sell_price:.6f} | Spread: +{opp.spread_pct:.2f}%",
                            profit_potential=net,
                            urgency="IMMEDIATE",
                            action=f"Execute quick flip with ${budget:.0f}"
                        ))
                        
        except Exception as e:
            Logger.debug(f"Spatial scan error: {e}")
            
        return alerts
    
    async def scan_funding_spikes(self, budget: float = 500.0) -> List[OpportunityAlert]:
        """Scan for high funding rate opportunities."""
        alerts = []
        
        try:
            from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed
            
            feed = MockDriftFundingFeed()
            markets = ["SOL-PERP", "BTC-PERP", "ETH-PERP", "WIF-PERP"]
            
            for market in markets:
                info = await feed.get_funding_rate(market)
                if info and info.rate_annual >= self.MIN_FUNDING_APR:
                    # Calculate potential
                    daily_profit = budget * (info.rate_annual / 100) / 365
                    
                    urgency = "IMMEDIATE" if info.rate_annual >= 50 else "SOON" if info.rate_annual >= 30 else "MONITOR"
                    
                    alerts.append(OpportunityAlert(
                        alert_type="FUNDING_SPIKE",
                        coin=market,
                        details=f"Funding Rate: {info.rate_8h:.4f}% per 8h ({info.rate_annual:.0f}% APY)",
                        profit_potential=daily_profit,
                        urgency=urgency,
                        action=f"Enter delta-neutral position (Long spot + Short perp)"
                    ))
                    
        except Exception as e:
            Logger.debug(f"Funding scan error: {e}")
            
        return alerts
    
    async def scan_volatility(self) -> List[OpportunityAlert]:
        """Detect volatility spikes that lead to funding opportunities."""
        alerts = []
        
        try:
            # Get current prices
            from src.arbitrage.feeds.jupiter_feed import JupiterFeed
            
            feed = JupiterFeed()
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            tokens = {
                "SOL": "So11111111111111111111111111111111111111112",
                "BTC": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # Wrapped BTC
            }
            
            for name, mint in tokens.items():
                spot = feed.get_spot_price(mint, USDC)
                if spot:
                    now = time.time()
                    
                    # Initialize history if needed
                    if name not in self.price_history:
                        self.price_history[name] = []
                    
                    # Add current price
                    self.price_history[name].append((now, spot.price))
                    
                    # Keep only last hour
                    cutoff = now - 3600
                    self.price_history[name] = [
                        (t, p) for t, p in self.price_history[name] if t > cutoff
                    ]
                    
                    # Calculate % change
                    if len(self.price_history[name]) >= 2:
                        old_price = self.price_history[name][0][1]
                        new_price = spot.price
                        pct_change = abs((new_price - old_price) / old_price) * 100
                        
                        if pct_change >= self.VOLATILITY_THRESHOLD:
                            direction = "📈 UP" if new_price > old_price else "📉 DOWN"
                            
                            alerts.append(OpportunityAlert(
                                alert_type="VOLATILITY",
                                coin=name,
                                details=f"Price moved {pct_change:.1f}% {direction} in last hour",
                                profit_potential=0,  # Indirect benefit
                                urgency="MONITOR",
                                action="Watch for funding rate spike (liquidations incoming)"
                            ))
                            
        except Exception as e:
            Logger.debug(f"Volatility scan error: {e}")
            
        return alerts
    
    async def scan_all(self, budget: float = 500.0) -> List[OpportunityAlert]:
        """Run all scans and return combined alerts."""
        all_alerts = []
        
        # Parallel scanning
        spatial, funding, volatility = await asyncio.gather(
            self.scan_spatial_opportunities(budget),
            self.scan_funding_spikes(budget),
            self.scan_volatility()
        )
        
        all_alerts.extend(spatial)
        all_alerts.extend(funding)
        all_alerts.extend(volatility)
        
        # Sort by urgency
        urgency_order = {"IMMEDIATE": 0, "SOON": 1, "MONITOR": 2}
        all_alerts.sort(key=lambda x: urgency_order.get(x.urgency, 3))
        
        return all_alerts


class JitoBundle:
    """
    Jito bundle for MEV protection.
    
    Jito allows you to submit transactions privately to validators,
    preventing MEV bots from front-running your trades.
    """
    
    JITO_BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
    
    def __init__(self, tip_amount_sol: float = 0.001):
        self.tip_amount = tip_amount_sol
        
    def prepare_bundle(self, transactions: List[Any]) -> Dict:
        """
        Prepare a Jito bundle for submission.
        
        In production, this would:
        1. Serialize all transactions
        2. Add tip instruction
        3. Sign with your wallet
        4. Submit to Jito block engine
        """
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendBundle",
            "params": [
                [tx for tx in transactions],  # Serialized transactions
                {"tip": self.tip_amount}
            ]
        }
    
    async def submit_bundle(self, bundle: Dict) -> Dict:
        """Submit bundle to Jito."""
        # This is a placeholder - real implementation needs wallet signing
        Logger.info(f"[JITO] Would submit bundle with {self.tip_amount} SOL tip")
        return {"success": False, "error": "Wallet signing not implemented"}


# ═══════════════════════════════════════════════════════════════════
# ALERT LOOP
# ═══════════════════════════════════════════════════════════════════

async def run_alert_loop(
    budget: float = 500.0,
    interval: int = 30,
    telegram: bool = True
):
    """
    Run continuous opportunity scanning.
    
    Args:
        budget: Budget for profit calculations
        interval: Scan interval in seconds
        telegram: Send alerts to Telegram
    """
    print("\n" + "="*70)
    print("   PHANTOM ARBITER - OPPORTUNITY ALERT SYSTEM")
    print("="*70)
    print(f"   Budget: ${budget:.2f}")
    print(f"   Scan Interval: {interval}s")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("\n   Scanning for opportunities... (Ctrl+C to stop)\n")
    
    scanner = OpportunityScanner()
    
    # Telegram notifier (if enabled)
    notifier = None
    if telegram:
        try:
            from src.utils.notifications import get_notifier
            notifier = get_notifier()
        except:
            pass
    
    scan_count = 0
    total_opportunities = 0
    
    try:
        while True:
            scan_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            
            try:
                # Scan for opportunities
                alerts = await scanner.scan_all(budget)
            except asyncio.CancelledError:
                break
            
            # Show status
            print(f"\r   [{now}] Scan #{scan_count}: ", end="")
            
            if alerts:
                immediate = [a for a in alerts if a.urgency == "IMMEDIATE"]
                soon = [a for a in alerts if a.urgency == "SOON"]
                
                print(f"🚨 {len(immediate)} IMMEDIATE, ⚠️ {len(soon)} SOON")
                
                for alert in alerts:
                    if alert.urgency in ["IMMEDIATE", "SOON"]:
                        print(alert)
                        total_opportunities += 1
                        
                        # Send to Telegram
                        if notifier and alert.urgency == "IMMEDIATE":
                            try:
                                msg = (
                                    f"🚨 {alert.alert_type}: {alert.coin}\n\n"
                                    f"{alert.details}\n\n"
                                    f"Potential: ${alert.profit_potential:.2f}\n"
                                    f"Action: {alert.action}"
                                )
                                notifier.send_alert(msg, "INFO")
                            except:
                                pass
            else:
                print("No opportunities above threshold", end="")
            
            await asyncio.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n   Stopped. Total scans: {scan_count}, Opportunities found: {total_opportunities}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Opportunity Alert System")
    parser.add_argument("--budget", type=float, default=500.0, help="Budget in USD")
    parser.add_argument("--interval", type=int, default=30, help="Scan interval in seconds")
    parser.add_argument("--min-spread", type=float, default=0.2, help="Min spatial spread percent")
    parser.add_argument("--min-apr", type=float, default=20.0, help="Min funding APR percent")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram alerts")
    
    args = parser.parse_args()
    
    # Update thresholds
    OpportunityScanner.MIN_SPATIAL_SPREAD = args.min_spread
    OpportunityScanner.MIN_FUNDING_APR = args.min_apr
    
    asyncio.run(run_alert_loop(
        budget=args.budget,
        interval=args.interval,
        telegram=not args.no_telegram
    ))
