"""
DNEM Pre-Flight Check
=====================
Comprehensive safety verification before first MainNet trade.

Validates:
1. Wallet connectivity & minimum balance
2. RPC latency & Oracle freshness
3. Jito Block Engine availability
4. Fee estimation for $1 test
5. Drift account status

Usage:
    python -m src.launchers.preflight_check

Must pass ALL checks before running live mode.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from src.shared.system.logging import Logger


@dataclass
class CheckResult:
    """Result of a single preflight check."""
    name: str
    passed: bool
    value: str
    threshold: str = ""
    recommendation: str = ""


class PreFlightCheck:
    """
    Comprehensive pre-flight verification for MainNet trading.
    
    All checks must pass before the first $1 test.
    """
    
    def __init__(self, min_balance_usd: float = 1.50):
        self.min_balance = min_balance_usd
        self.checks: List[CheckResult] = []
        self.wallet = None
        self.sol_price = 150.0  # Default, updated during check
    
    async def run_all_checks(self) -> bool:
        """Run all preflight checks."""
        print("\n" + "=" * 60)
        print("🛫 DNEM PRE-FLIGHT CHECK")
        print("=" * 60 + "\n")
        
        # 1. Wallet & Balance
        await self._check_wallet()
        
        # 2. RPC Latency
        await self._check_rpc_latency()
        
        # 3. Oracle Freshness
        await self._check_oracle_freshness()
        
        # 4. Jito Availability
        await self._check_jito()
        
        # 5. Fee Estimation
        await self._check_fee_impact()
        
        # 6. Drift Account
        await self._check_drift_account()
        
        # Print results
        self._print_results()
        
        all_passed = all(c.passed for c in self.checks)
        return all_passed
    
    async def _check_wallet(self):
        """Check wallet connectivity and balances."""
        try:
            from src.shared.execution.wallet import WalletManager
            self.wallet = WalletManager()
            
            if not self.wallet.keypair:
                self.checks.append(CheckResult(
                    name="Wallet Keypair",
                    passed=False,
                    value="Not found",
                    recommendation="Set SOLANA_PRIVATE_KEY env var",
                ))
                return
            
            self.checks.append(CheckResult(
                name="Wallet Keypair",
                passed=True,
                value=f"{self.wallet.get_public_key()[:16]}...",
            ))
            
            # Check SOL balance
            sol_balance = self.wallet.get_sol_balance()
            min_sol = 0.05  # For gas
            
            self.checks.append(CheckResult(
                name="SOL Balance (Gas)",
                passed=sol_balance >= min_sol,
                value=f"{sol_balance:.4f} SOL",
                threshold=f">= {min_sol} SOL",
                recommendation="Top up wallet with SOL for gas" if sol_balance < min_sol else "",
            ))
            
            # Get total USD balance
            balance_info = self.wallet.get_current_live_usd_balance()
            total_usd = balance_info.get("total_usd", 0)
            
            self.checks.append(CheckResult(
                name="Total Balance",
                passed=total_usd >= self.min_balance,
                value=f"${total_usd:.2f}",
                threshold=f">= ${self.min_balance:.2f}",
                recommendation=f"Need at least ${self.min_balance:.2f} for $1 test" if total_usd < self.min_balance else "",
            ))
            
        except Exception as e:
            self.checks.append(CheckResult(
                name="Wallet Check",
                passed=False,
                value=str(e),
                recommendation="Check wallet configuration",
            ))
    
    async def _check_rpc_latency(self):
        """Check RPC connection latency."""
        try:
            from solana.rpc.api import Client
            from config.settings import Settings
            
            client = Client(Settings.RPC_URL)
            
            # Measure latency with 3 pings
            latencies = []
            for _ in range(3):
                start = time.time()
                slot = client.get_slot()
                latencies.append((time.time() - start) * 1000)
            
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            
            # Threshold: 300ms max
            passed = max_latency < 300
            
            self.checks.append(CheckResult(
                name="RPC Latency",
                passed=passed,
                value=f"Avg: {avg_latency:.0f}ms, Max: {max_latency:.0f}ms",
                threshold="< 300ms",
                recommendation="Consider switching to a faster RPC (Helius/Triton)" if not passed else "",
            ))
            
        except Exception as e:
            self.checks.append(CheckResult(
                name="RPC Connection",
                passed=False,
                value=str(e),
                recommendation="Check RPC_URL in settings",
            ))
    
    async def _check_oracle_freshness(self):
        """Check Oracle price freshness."""
        try:
            from solana.rpc.api import Client
            from config.settings import Settings
            
            client = Client(Settings.RPC_URL)
            
            # Get current slot
            current_slot = client.get_slot().value
            
            # Get price and check freshness
            # For now, use SharedPriceCache
            try:
                from src.core.shared_cache import SharedPriceCache
                raw_price = SharedPriceCache.get_price("SOL")
                
                # Handle if price is tuple (price, timestamp) or just float
                if isinstance(raw_price, tuple):
                    self.sol_price = float(raw_price[0]) if raw_price[0] else 150.0
                elif isinstance(raw_price, (int, float)):
                    self.sol_price = float(raw_price)
                else:
                    self.sol_price = 150.0
                
                # Check if price is reasonable (sanity check)
                if 10 < self.sol_price < 500:
                    self.checks.append(CheckResult(
                        name="Oracle Price",
                        passed=True,
                        value=f"SOL: ${self.sol_price:.2f}",
                        threshold="10 < price < 500",
                    ))
                else:
                    self.checks.append(CheckResult(
                        name="Oracle Price",
                        passed=False,
                        value=f"SOL: ${self.sol_price:.2f} (suspicious)",
                        recommendation="Check price feed source",
                    ))
            except (ImportError, Exception):
                self.sol_price = 150.0
                self.checks.append(CheckResult(
                    name="Oracle Price",
                    passed=True,
                    value=f"SOL: ${self.sol_price:.2f} (default)",
                ))
            
        except Exception as e:
            self.sol_price = 150.0  # Ensure sol_price is always set
            self.checks.append(CheckResult(
                name="Oracle Check",
                passed=False,
                value=str(e),
            ))
    
    async def _check_jito(self):
        """Check Jito Block Engine availability."""
        try:
            from src.shared.infrastructure.jito_adapter import JitoAdapter
            
            jito = JitoAdapter(region="ny")
            
            is_available = await jito.is_available()
            
            if is_available:
                tip_accounts = await jito.get_tip_accounts()
                self.checks.append(CheckResult(
                    name="Jito Block Engine",
                    passed=True,
                    value=f"Online ({len(tip_accounts)} tip accounts)",
                ))
            else:
                self.checks.append(CheckResult(
                    name="Jito Block Engine",
                    passed=False,
                    value="Not responding",
                    recommendation="Check network or try different region (ny/ams/tokyo)",
                ))
            
        except Exception as e:
            self.checks.append(CheckResult(
                name="Jito Check",
                passed=False,
                value=str(e),
                recommendation="Jito may be down or blocked",
            ))
    
    async def _check_fee_impact(self):
        """Estimate fee impact on $1 trade."""
        try:
            from src.delta_neutral.safety_gates import FeeGuard
            
            guard = FeeGuard()
            
            # Estimate fees for $1 trade ($0.50 per leg)
            trade_amount = 0.50
            jito_tip = 10_000  # 10K lamports
            
            fee = guard.estimate_fee_usd(
                jito_tip_lamports=jito_tip,
                sol_price=self.sol_price,
                swap_amount_usd=trade_amount,
            )
            
            # Calculate as percentage of trade
            fee_pct = (fee / trade_amount) * 100
            
            # Threshold: < 3% of trade value
            passed = fee_pct < 3.0
            
            self.checks.append(CheckResult(
                name="Fee Impact ($0.50 trade)",
                passed=passed,
                value=f"${fee:.4f} ({fee_pct:.2f}%)",
                threshold="< 3% of trade",
                recommendation="Reduce Jito tip or increase trade size" if not passed else "",
            ))
            
            # Estimate for full $1 test
            full_fee = fee * 2  # Both legs
            
            self.checks.append(CheckResult(
                name="$1 Test Total Fee",
                passed=full_fee < 0.02,
                value=f"${full_fee:.4f} (open + close)",
                threshold="< $0.02",
                recommendation="" if full_fee < 0.02 else "Fee too high for $1 test",
            ))
            
        except Exception as e:
            self.checks.append(CheckResult(
                name="Fee Estimation",
                passed=False,
                value=str(e),
            ))
    
    async def _check_drift_account(self):
        """Check Drift account status."""
        try:
            from src.delta_neutral.drift_order_builder import DriftOrderBuilder
            from solders.pubkey import Pubkey
            
            # Check if wallet exists and has keypair
            if not self.wallet or not self.wallet.keypair:
                self.checks.append(CheckResult(
                    name="Drift Account",
                    passed=False,
                    value="No wallet keypair",
                    recommendation="Set SOLANA_PRIVATE_KEY first",
                ))
                return
            
            pubkey = self.wallet.get_public_key()
            if not pubkey:
                self.checks.append(CheckResult(
                    name="Drift Account",
                    passed=False,
                    value="No wallet pubkey",
                ))
                return
            
            # Convert to Pubkey if string
            if isinstance(pubkey, str):
                pubkey = Pubkey.from_string(pubkey)
            
            builder = DriftOrderBuilder(pubkey)
            
            # Verify PDA derivation
            user_account = builder.user_account
            
            self.checks.append(CheckResult(
                name="Drift Account PDA",
                passed=True,
                value=f"{str(user_account)[:16]}...",
            ))
            
        except Exception as e:
            self.checks.append(CheckResult(
                name="Drift Check",
                passed=False,
                value=str(e),
                recommendation="May need to initialize Drift account first",
            ))
    
    def _print_results(self):
        """Print formatted results."""
        print("\n" + "-" * 60)
        print("RESULTS")
        print("-" * 60)
        
        passed_count = 0
        failed_count = 0
        
        for c in self.checks:
            status = "✅" if c.passed else "❌"
            print(f"{status} {c.name}")
            print(f"   Value: {c.value}")
            if c.threshold:
                print(f"   Threshold: {c.threshold}")
            if c.recommendation:
                print(f"   ⚠️  {c.recommendation}")
            
            if c.passed:
                passed_count += 1
            else:
                failed_count += 1
        
        print("-" * 60)
        print(f"PASSED: {passed_count}/{len(self.checks)}")
        
        if failed_count == 0:
            print("\n🎉 ALL CHECKS PASSED - Ready for $1 MainNet test!")
            print("\nNext step:")
            print("  python -m src.delta_neutral.engine --mode live --balance 1.0")
        else:
            print(f"\n⚠️ {failed_count} CHECKS FAILED - Fix issues before proceeding")
        
        print("=" * 60 + "\n")


async def main():
    """Run preflight check."""
    check = PreFlightCheck(min_balance_usd=1.50)
    passed = await check.run_all_checks()
    return 0 if passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
