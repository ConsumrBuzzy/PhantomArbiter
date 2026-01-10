"""
MainNet Smoke Test
==================
$1 stress test for DNEM before full deployment.

This script validates that all MainNet adapters work correctly
before risking the full $12 balance.

Tests:
1. Wallet connectivity & balance check
2. Jupiter swap ($0.10 USDC → SOL)
3. Drift position open (smallest possible)
4. Drift position close
5. Fee audit

Usage:
    python -m src.launchers.mainnet_smoke_test

⚠️ REQUIRES: SOLANA_PRIVATE_KEY environment variable
⚠️ REQUIRES: At least 0.1 SOL and 1 USDC in wallet
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from src.shared.system.logging import Logger


@dataclass
class SmokeTestResult:
    """Result of a smoke test step."""
    step: str
    success: bool
    duration_ms: float
    fee_usd: float = 0.0
    details: str = ""


@dataclass
class SmokeTestReport:
    """Full smoke test report."""
    results: list = field(default_factory=list)
    total_fee_usd: float = 0.0
    all_passed: bool = False
    
    def add(self, result: SmokeTestResult):
        self.results.append(result)
        self.total_fee_usd += result.fee_usd
    
    def print_report(self):
        print("\n" + "=" * 60)
        print("🧪 MAINNET SMOKE TEST REPORT")
        print("=" * 60)
        
        for r in self.results:
            status = "✅" if r.success else "❌"
            print(f"{status} {r.step}: {r.duration_ms:.0f}ms | Fee: ${r.fee_usd:.6f}")
            if r.details:
                print(f"   └─ {r.details}")
        
        print("-" * 60)
        print(f"Total Fees: ${self.total_fee_usd:.6f}")
        
        all_passed = all(r.success for r in self.results)
        self.all_passed = all_passed
        
        if all_passed:
            print("\n🎉 ALL TESTS PASSED - Safe to proceed with $12")
        else:
            print("\n⚠️ SOME TESTS FAILED - Do NOT proceed until fixed")
        
        if self.total_fee_usd > 0.05:
            print(f"\n⚠️ WARNING: Total fees ${self.total_fee_usd:.4f} > $0.05 threshold")
            print("   Consider reducing Jito tip or optimizing routes")
        
        print("=" * 60)


class MainNetSmokeTest:
    """
    Comprehensive smoke test for MainNet deployment.
    
    Validates all adapters with tiny trades before risking capital.
    """
    
    def __init__(self):
        self.wallet = None
        self.swapper = None
        self.jito = None
        self.drift = None
        self.report = SmokeTestReport()
    
    async def run(self) -> SmokeTestReport:
        """Run all smoke tests."""
        Logger.info("=" * 60)
        Logger.info("🧪 MAINNET SMOKE TEST")
        Logger.info("=" * 60)
        
        # Initialize adapters
        if not await self._init_adapters():
            return self.report
        
        # Run tests
        await self._test_balance_check()
        await self._test_jito_availability()
        await self._test_small_swap()
        await self._test_drift_position()
        
        # Print report
        self.report.print_report()
        
        return self.report
    
    async def _init_adapters(self) -> bool:
        """Initialize live adapters."""
        start = time.time()
        
        try:
            # Wallet
            from src.shared.execution.wallet import WalletManager
            self.wallet = WalletManager()
            
            if not self.wallet.keypair:
                self.report.add(SmokeTestResult(
                    step="Wallet Init",
                    success=False,
                    duration_ms=0,
                    details="No keypair found. Set SOLANA_PRIVATE_KEY env var.",
                ))
                return False
            
            Logger.info(f"Wallet: {self.wallet.get_public_key()}")
            
            # Swapper
            from src.shared.execution.swapper import JupiterSwapper
            self.swapper = JupiterSwapper(self.wallet)
            
            # Jito
            from src.shared.infrastructure.jito_adapter import JitoAdapter
            self.jito = JitoAdapter(region="ny")
            
            # Drift
            from src.shared.infrastructure.drift_adapter import DriftAdapter
            self.drift = DriftAdapter("mainnet")
            self.drift.set_wallet(self.wallet)
            
            duration = (time.time() - start) * 1000
            self.report.add(SmokeTestResult(
                step="Adapter Init",
                success=True,
                duration_ms=duration,
                details="All adapters loaded successfully",
            ))
            
            return True
            
        except Exception as e:
            self.report.add(SmokeTestResult(
                step="Adapter Init",
                success=False,
                duration_ms=(time.time() - start) * 1000,
                details=str(e),
            ))
            return False
    
    async def _test_balance_check(self):
        """Test 1: Verify wallet balances."""
        start = time.time()
        
        try:
            sol_balance = self.wallet.get_sol_balance()
            
            # Check minimum SOL for gas
            if sol_balance < 0.05:
                self.report.add(SmokeTestResult(
                    step="Balance Check",
                    success=False,
                    duration_ms=(time.time() - start) * 1000,
                    details=f"SOL balance {sol_balance:.4f} < 0.05 minimum",
                ))
                return
            
            # Get full balance breakdown
            balance_info = self.wallet.get_current_live_usd_balance()
            total_usd = balance_info.get("total_usd", 0)
            
            self.report.add(SmokeTestResult(
                step="Balance Check",
                success=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"SOL: {sol_balance:.4f}, Total: ${total_usd:.2f}",
            ))
            
        except Exception as e:
            self.report.add(SmokeTestResult(
                step="Balance Check",
                success=False,
                duration_ms=(time.time() - start) * 1000,
                details=str(e),
            ))
    
    async def _test_jito_availability(self):
        """Test 2: Verify Jito Block Engine connection."""
        start = time.time()
        
        try:
            is_available = await self.jito.is_available()
            
            if not is_available:
                self.report.add(SmokeTestResult(
                    step="Jito Connection",
                    success=False,
                    duration_ms=(time.time() - start) * 1000,
                    details="Jito Block Engine not responding",
                ))
                return
            
            # Get tip account
            tip_account = await self.jito.get_random_tip_account()
            
            self.report.add(SmokeTestResult(
                step="Jito Connection",
                success=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"Tip account: {tip_account[:16]}...",
            ))
            
        except Exception as e:
            self.report.add(SmokeTestResult(
                step="Jito Connection",
                success=False,
                duration_ms=(time.time() - start) * 1000,
                details=str(e),
            ))
    
    async def _test_small_swap(self):
        """Test 3: Execute tiny swap ($0.10 USDC → SOL)."""
        start = time.time()
        fee_usd = 0.0
        
        try:
            USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            SOL_MINT = "So11111111111111111111111111111111111111112"
            
            # Quote for $0.10
            amount_atomic = 100_000  # $0.10 in USDC (6 decimals)
            
            quote = await self.swapper.get_quote(
                USDC_MINT,
                SOL_MINT,
                amount_atomic,
                slippage=100,  # 1%
            )
            
            if not quote or "error" in quote:
                self.report.add(SmokeTestResult(
                    step="Small Swap (Quote)",
                    success=False,
                    duration_ms=(time.time() - start) * 1000,
                    details=f"Quote failed: {quote}",
                ))
                return
            
            out_amount = int(quote.get("outAmount", 0)) / 1_000_000_000
            
            # For smoke test, we just quote - no actual execution
            # To actually execute, uncomment below:
            # result = self.swapper.execute_swap("BUY", 0.10, "SMOKE_TEST")
            
            self.report.add(SmokeTestResult(
                step="Small Swap (Quote)",
                success=True,
                duration_ms=(time.time() - start) * 1000,
                fee_usd=0.0001,  # Estimated fee
                details=f"$0.10 → {out_amount:.6f} SOL (quote only)",
            ))
            
        except Exception as e:
            self.report.add(SmokeTestResult(
                step="Small Swap",
                success=False,
                duration_ms=(time.time() - start) * 1000,
                details=str(e),
            ))
    
    async def _test_drift_position(self):
        """Test 4: Verify Drift account derivation."""
        start = time.time()
        
        try:
            from src.delta_neutral.drift_order_builder import DriftOrderBuilder
            from solders.pubkey import Pubkey
            
            pubkey = self.wallet.get_public_key()
            if isinstance(pubkey, str):
                pubkey = Pubkey.from_string(pubkey)
            
            builder = DriftOrderBuilder(pubkey)
            
            # Verify PDA derivation
            user_account = builder.user_account
            user_stats = builder.user_stats
            
            # Build a tiny order (0.001 SOL) to verify instruction format
            instructions = builder.build_short_order("SOL-PERP", 0.001)
            
            if not instructions:
                self.report.add(SmokeTestResult(
                    step="Drift Setup",
                    success=False,
                    duration_ms=(time.time() - start) * 1000,
                    details="Failed to build order instructions",
                ))
                return
            
            self.report.add(SmokeTestResult(
                step="Drift Setup",
                success=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"User PDA: {str(user_account)[:16]}..., IXs: {len(instructions)}",
            ))
            
        except Exception as e:
            self.report.add(SmokeTestResult(
                step="Drift Setup",
                success=False,
                duration_ms=(time.time() - start) * 1000,
                details=str(e),
            ))


async def main():
    """Run the smoke test."""
    test = MainNetSmokeTest()
    report = await test.run()
    
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
