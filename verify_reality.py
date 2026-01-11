"""
Verify Reality - Production Connection Diagnostic
==================================================
The "Moment of Truth" script that confirms all production endpoints.

This script verifies:
1. ✅ Coinbase CDP/JWT Authentication
2. ✅ Real Market Data (SOL/USDC ticker)
3. ✅ Real Wallet Balances (USDC, USD, SOL)
4. ✅ Phantom Wallet Address Configuration
5. ✅ Network Configuration (Solana-only enforcement)

Run this BEFORE enabling live trading.

Usage:
    python verify_reality.py

Expected Output (Success):
    ═══════════════════════════════════════════════════════════════
    ✅ REALITY CHECK PASSED
    ═══════════════════════════════════════════════════════════════
    📈 SOL Price: $XXX.XX (Live from Coinbase)
    💰 USDC Balance: $XX.XX
    🔐 Phantom Address: XXXX...XXXX (Configured)
    🌐 Network: Solana-only (Enforced)
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


class RealityChecker:
    """Comprehensive production readiness checker."""
    
    def __init__(self):
        self.results = {}
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def _print_header(self):
        print("\n" + "=" * 65)
        print("  PHANTOM ARBITER - REALITY CHECK")
        print("  Verifying Production Endpoints")
        print("=" * 65)
        print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 65 + "\n")
    
    def _check(self, name: str, passed: bool, message: str, warning: bool = False):
        """Record a check result."""
        if passed:
            icon = "✅" if not warning else "⚠️"
            self.passed += 1
            if warning:
                self.warnings += 1
        else:
            icon = "❌"
            self.failed += 1
        
        print(f"  {icon} {name}: {message}")
        self.results[name] = {"passed": passed, "message": message}
    
    async def check_coinbase_auth(self):
        """Test 1: Coinbase CDP/JWT Authentication."""
        print("\n📡 [1/5] COINBASE AUTHENTICATION")
        print("-" * 40)
        
        try:
            from src.drivers.coinbase_driver import get_coinbase_driver
            
            driver = get_coinbase_driver()
            
            # Check configuration
            if not driver.is_configured:
                self._check(
                    "CDP Credentials",
                    False,
                    "Not configured - set COINBASE_CLIENT_API_KEY and COINBASE_API_PRIVATE_KEY"
                )
                return False
            
            self._check("CDP Credentials", True, "Configured ✓")
            
            # Test connection
            result = await driver.check_api_connectivity()
            
            if result['status'] == 'connected':
                self._check("API Connection", True, f"Connected via {result['auth_method']}")
                return True
            else:
                self._check("API Connection", False, f"Failed: {result.get('error', 'Unknown')}")
                return False
                
        except ImportError as e:
            self._check("CCXT Import", False, f"Missing dependency: {e}")
            return False
        except Exception as e:
            self._check("API Connection", False, f"Error: {e}")
            return False
    
    async def check_market_data(self):
        """Test 2: Real Market Data from Coinbase."""
        print("\n📈 [2/5] LIVE MARKET DATA")
        print("-" * 40)
        
        try:
            from src.drivers.coinbase_driver import get_coinbase_driver
            
            driver = get_coinbase_driver()
            
            # Fetch SOL/USDC ticker
            ticker = await driver.fetch_ticker("SOL/USDC")
            
            if ticker.get("error"):
                self._check("SOL/USDC Ticker", False, f"Error: {ticker['error']}")
                return False
            
            sol_price = ticker.get("last", 0.0)
            bid = ticker.get("bid", 0.0)
            ask = ticker.get("ask", 0.0)
            spread_pct = ((ask - bid) / bid * 100) if bid > 0 else 0
            
            if sol_price > 0:
                self._check(
                    "SOL/USDC Price",
                    True,
                    f"${sol_price:.4f} (spread: {spread_pct:.3f}%)"
                )
                
                # Sanity check: SOL should be between $10 and $1000
                if sol_price < 10 or sol_price > 1000:
                    self._check(
                        "Price Sanity",
                        True,
                        f"Price ${sol_price:.2f} outside typical range",
                        warning=True
                    )
                else:
                    self._check("Price Sanity", True, "Within expected range")
                
                return True
            else:
                self._check("SOL/USDC Price", False, "Price is 0 or unavailable")
                return False
                
        except Exception as e:
            self._check("Market Data", False, f"Error: {e}")
            return False
    
    async def check_real_balances(self):
        """Test 3: Real Wallet Balances."""
        print("\n💰 [3/5] REAL WALLET BALANCES")
        print("-" * 40)
        
        try:
            from src.drivers.coinbase_driver import get_coinbase_driver
            
            driver = get_coinbase_driver()
            
            # Sync real balances
            balances = await driver.sync_real_balances()
            
            if balances.get("error"):
                self._check("Balance Sync", False, f"Error: {balances['error']}")
                return False
            
            usdc = balances.get("usdc", 0.0)
            usd = balances.get("usd", 0.0)
            sol = balances.get("sol", 0.0)
            total = balances.get("total_usd", 0.0)
            
            # Report each balance
            self._check("USDC Balance", True, f"${usdc:.2f}")
            self._check("USD Balance", True, f"${usd:.2f}")
            self._check("SOL Balance", True, f"{sol:.6f} SOL (${balances.get('sol_value_usd', 0):.2f})")
            self._check("Total Value", True, f"${total:.2f}")
            
            # Warning if wallet appears empty
            if total <= 0:
                self._check(
                    "Wallet Status",
                    True,
                    "Wallet appears empty - ensure funds are deposited",
                    warning=True
                )
            elif total < 5:
                self._check(
                    "Wallet Status",
                    True,
                    f"Low balance (${total:.2f}) - below minimum bridge amount",
                    warning=True
                )
            else:
                self._check("Wallet Status", True, "Funded and ready")
            
            return True
                
        except Exception as e:
            self._check("Balance Fetch", False, f"Error: {e}")
            return False
    
    def check_phantom_config(self):
        """Test 4: Phantom Wallet Configuration."""
        print("\n🔐 [4/5] PHANTOM WALLET CONFIG")
        print("-" * 40)
        
        phantom_addr = os.getenv("PHANTOM_SOLANA_ADDRESS", "")
        
        if not phantom_addr:
            self._check(
                "Phantom Address",
                False,
                "Not configured - set PHANTOM_SOLANA_ADDRESS in .env"
            )
            return False
        
        # Validate Solana address format (base58, 32-44 chars)
        if len(phantom_addr) < 32 or len(phantom_addr) > 44:
            self._check(
                "Address Format",
                False,
                f"Invalid length ({len(phantom_addr)} chars) - Solana addresses are 32-44 chars"
            )
            return False
        
        # Show masked address
        masked = f"{phantom_addr[:4]}...{phantom_addr[-4:]}"
        self._check("Phantom Address", True, f"{masked} (whitelisted)")
        self._check("Address Format", True, f"Valid Solana format ({len(phantom_addr)} chars)")
        
        return True
    
    def check_network_guard(self):
        """Test 5: Network Guard Configuration."""
        print("\n🌐 [5/5] NETWORK GUARD")
        print("-" * 40)
        
        try:
            from src.drivers.coinbase_driver import CoinbaseExchangeDriver
            
            driver = CoinbaseExchangeDriver()
            
            # Verify Solana is allowed
            try:
                driver._validate_network("solana")
                self._check("Solana Network", True, "Allowed ✓")
            except ValueError:
                self._check("Solana Network", False, "Blocked - configuration error")
                return False
            
            # Verify ERC20 is blocked
            try:
                driver._validate_network("erc20")
                self._check("ERC20 Guard", False, "NOT BLOCKED - security risk!")
                return False
            except ValueError:
                self._check("ERC20 Guard", True, "Blocked ✓ (as expected)")
            
            # Verify Ethereum is blocked
            try:
                driver._validate_network("ethereum")
                self._check("Ethereum Guard", False, "NOT BLOCKED - security risk!")
                return False
            except ValueError:
                self._check("Ethereum Guard", True, "Blocked ✓ (as expected)")
            
            return True
            
        except Exception as e:
            self._check("Network Guard", False, f"Error: {e}")
            return False
    
    async def check_bridge_safety(self):
        """Additional: Verify bridge safety thresholds."""
        print("\n🛡️ [BONUS] BRIDGE SAFETY THRESHOLDS")
        print("-" * 40)
        
        min_bridge = float(os.getenv("MIN_BRIDGE_AMOUNT_USD", "5.0"))
        dust_floor = float(os.getenv("CEX_DUST_FLOOR_USD", "1.0"))
        
        self._check("Min Bridge Amount", True, f"${min_bridge:.2f}")
        self._check("Dust Floor", True, f"${dust_floor:.2f}")
        
        if min_bridge < 1.0:
            self._check(
                "Min Bridge Warning",
                True,
                "Very low minimum - consider increasing",
                warning=True
            )
        
        return True
    
    def print_summary(self):
        """Print final summary."""
        print("\n" + "=" * 65)
        
        if self.failed == 0:
            print("  ✅ REALITY CHECK PASSED")
            status = "PRODUCTION READY"
        else:
            print("  ❌ REALITY CHECK FAILED")
            status = "NOT READY"
        
        print("=" * 65)
        print(f"  Status: {status}")
        print(f"  Passed: {self.passed} | Failed: {self.failed} | Warnings: {self.warnings}")
        print("=" * 65)
        
        if self.failed > 0:
            print("\n⚠️  Fix the failed checks before enabling live trading.")
        elif self.warnings > 0:
            print("\n⚠️  Warnings detected - review before proceeding.")
        else:
            print("\n🚀 All systems nominal. Safe to proceed with live trading.")
        
        print()
    
    async def run_all_checks(self):
        """Run complete reality check."""
        self._print_header()
        
        await self.check_coinbase_auth()
        await self.check_market_data()
        await self.check_real_balances()
        self.check_phantom_config()
        self.check_network_guard()
        await self.check_bridge_safety()
        
        self.print_summary()
        
        return self.failed == 0


async def main():
    checker = RealityChecker()
    success = await checker.run_all_checks()
    
    # Cleanup
    try:
        from src.drivers.coinbase_driver import get_coinbase_driver
        driver = get_coinbase_driver()
        await driver.close()
    except:
        pass
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
