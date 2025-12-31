"""
V5.7 Token Safety Validator
SRP: Validates token safety before trading.

Checks:
- Layer 1: Mint/Freeze Authority (Solana RPC)
- Layer 1: Honeypot Simulation (Jupiter API)
- Layer 2: Liquidity Validation (DexScreener API)
- Layer 2: Top 10 Holder Concentration (Solana RPC)
"""

import json
import os
import time
import requests
from dataclasses import dataclass, asdict
from typing import Tuple
from config.settings import Settings

# V83.0: Import from centralized token standards module
from src.shared.infrastructure.token_standards import TOKEN_2022_PROGRAM_ID


@dataclass
class ValidationResult:
    """Result of token validation."""

    is_safe: bool
    mint_authority_ok: bool
    freeze_authority_ok: bool
    honeypot_ok: bool
    liquidity_ok: bool
    liquidity_usd: float
    top_holders_ok: bool
    top10_pct: float
    reason: str


class TokenValidator:
    """
    V5.7: Validates token safety before allowing trades.
    V51.0: Added VERBOSE flag to silence noisy warnings.
    """

    # Rate limiting delays (seconds)
    RPC_DELAY = 0.5  # Between RPC calls
    JUPITER_DELAY = 0.2  # Between Jupiter calls (Optimized)
    DEXSCREENER_DELAY = 0.2  # DexScreener is generous (300/min)

    # V51.0: Set to False to silence validation warnings
    VERBOSE = False

    def __init__(self):
        self.cache_file = os.path.join(
            os.path.dirname(__file__), "validation_cache.json"
        )
        self.cache = self._load_cache()  # Load persisted cache
        self.cache_ttl = 900  # 15 minutes

    def _load_cache(self):
        """Load validation cache from disk."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    # Restore ValidationResult objects
                    restored = {}
                    for mint, item in data.items():
                        ts = item.get("timestamp", 0)
                        res_dict = item.get("result", {})
                        if res_dict:
                            restored[mint] = (ts, ValidationResult(**res_dict))
                    return restored
            except Exception as e:
                print(f"⚠️ Failed to load validation cache: {e}")
        return {}

    def _save_cache(self):
        """Save validation cache to disk."""
        try:
            data = {}
            for mint, (ts, result) in self.cache.items():
                data[mint] = {"timestamp": ts, "result": asdict(result)}
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def validate(self, mint: str, symbol: str = "UNKNOWN") -> ValidationResult:
        """Run all safety checks on a token."""
        # Check cache first
        if mint in self.cache:
            cached_time, cached_result = self.cache[mint]
            if time.time() - cached_time < self.cache_ttl:
                return cached_result

        # V89.14: Enable verbose logging in paper aggressive mode for diagnostics
        is_paper_diagnostic = not Settings.ENABLE_TRADING and getattr(
            Settings, "PAPER_AGGRESSIVE_MODE", False
        )

        # Diagnostic logging removed

        # Layer 1: Authority Checks
        mint_ok = self.check_mint_authority(mint)
        # Diagnostic logging removed
        time.sleep(self.RPC_DELAY)

        freeze_ok = self.check_freeze_authority(mint)
        # Diagnostic logging removed
        time.sleep(self.RPC_DELAY)

        # Layer 1: Honeypot Check
        honeypot_ok = self.check_honeypot(mint)
        # Diagnostic logging removed
        time.sleep(self.JUPITER_DELAY)

        # Layer 2: Liquidity Check
        liquidity_ok, liquidity_usd = self.check_liquidity(mint)
        # Diagnostic logging removed
        time.sleep(self.RPC_DELAY)

        # Layer 2: Top Holder Check
        top_holders_ok, top10_pct = self.check_top_holders(mint)
        # Diagnostic logging removed

        # Determine overall safety
        is_safe = (
            mint_ok and freeze_ok and honeypot_ok and liquidity_ok and top_holders_ok
        )

        # Build reason string
        reasons = []
        if not mint_ok:
            reasons.append("Mint Authority ACTIVE")
        if not freeze_ok:
            reasons.append("Freeze Authority ACTIVE")
        if not honeypot_ok:
            reasons.append("Honeypot DETECTED")
        if not liquidity_ok:
            reasons.append(f"Low Liquidity (${liquidity_usd:,.0f})")
        if not top_holders_ok:
            reasons.append(
                f"Top 10 hold {top10_pct * 100:.1f}% (> {Settings.MAX_TOP10_HOLDER_PCT * 100:.0f}%)"
            )

        reason = "; ".join(reasons) if reasons else "All checks passed"

        # V89.14: Show final validation result in paper mode
        # Diagnostic logging removed

        result = ValidationResult(
            is_safe=is_safe,
            mint_authority_ok=mint_ok,
            freeze_authority_ok=freeze_ok,
            honeypot_ok=honeypot_ok,
            liquidity_ok=liquidity_ok,
            liquidity_usd=liquidity_usd,
            top_holders_ok=top_holders_ok,
            top10_pct=top10_pct,
            reason=reason,
        )

        # Cache result
        self.cache[mint] = (time.time(), result)
        self._save_cache()  # Persist to disk

        # Log result
        if self.VERBOSE:
            status = "✅ SAFE" if is_safe else "⛔ UNSAFE"
            print(f"   {status} {symbol}: {reason}")

        return result

    def check_mint_authority(self, mint: str) -> bool:
        """
        Check if token's Mint Authority is revoked (NULL).

        A non-null mint authority means the developer can print
        unlimited tokens, crashing the price.

        Returns:
            True if mint authority is revoked (safe)
            False if mint authority is active (unsafe)
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [mint, {"encoding": "jsonParsed"}],
            }

            resp = requests.post(
                Settings.RPC_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = resp.json()

            if "result" in data and data["result"] and "value" in data["result"]:
                value = data["result"]["value"]
                if value and "data" in value:
                    parsed = value["data"].get("parsed", {})
                    info = parsed.get("info", {})

                    # Check mintAuthority - should be None/null for safety
                    mint_authority = info.get("mintAuthority")

                    if mint_authority is None:
                        return True  # Revoked = Safe
                    else:
                        if self.VERBOSE:
                            print(f"      ⚠️ Mint Authority: {mint_authority[:8]}...")
                        return False  # Active = Unsafe

            # If we can't determine, assume safe (established tokens)
            if self.VERBOSE:
                print("      ⚠️ Could not verify mint authority")
            return True

        except Exception as e:
            if self.VERBOSE:
                print(f"      ❌ Mint authority check failed: {e}")
            return True  # Fail open for established tokens

    def check_freeze_authority(self, mint: str) -> bool:
        """
        Check if token's Freeze Authority is revoked.

        An active freeze authority means the developer can
        freeze all wallets, preventing sales.

        Returns:
            True if freeze authority is revoked (safe)
            False if freeze authority is active (unsafe)
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [mint, {"encoding": "jsonParsed"}],
            }

            resp = requests.post(
                Settings.RPC_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = resp.json()

            if "result" in data and data["result"] and "value" in data["result"]:
                value = data["result"]["value"]
                if value and "data" in value:
                    parsed = value["data"].get("parsed", {})
                    info = parsed.get("info", {})

                    # Check freezeAuthority - should be None/null for safety
                    freeze_authority = info.get("freezeAuthority")

                    if freeze_authority is None:
                        return True  # Revoked = Safe
                    else:
                        if self.VERBOSE:
                            print(
                                f"      ⚠️ Freeze Authority: {freeze_authority[:8]}..."
                            )
                        return False  # Active = Unsafe

            if self.VERBOSE:
                print("      ⚠️ Could not verify freeze authority")
            return True

        except Exception as e:
            if self.VERBOSE:
                print(f"      ❌ Freeze authority check failed: {e}")
            return True

    def check_honeypot(self, mint: str) -> bool:
        """
        Simulate a sell to detect honeypot tokens.

        A honeypot allows buys but blocks sells. We test by
        requesting a Jupiter quote to sell a small amount.
        Uses fallback endpoint if primary fails.

        Returns:
            True if token is sellable (safe)
            False if sell is blocked (honeypot)
        """
        # Simulate selling 1 token worth
        test_amount = Settings.HONEYPOT_TEST_AMOUNT

        params = {
            "inputMint": mint,
            "outputMint": Settings.USDC_MINT,
            "amount": str(test_amount),
            "slippageBps": Settings.HONEYPOT_SLIPPAGE_BPS,
        }

        # Try primary, then fallback
        endpoints = [
            "https://quote-api.jup.ag/v6/quote",
            "https://public.jupiterapi.com/quote",
        ]

        for endpoint in endpoints:
            try:
                resp = requests.get(endpoint, params=params, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()

                    # Check if we got a valid quote
                    if "outAmount" in data:
                        out_amount = int(data["outAmount"])
                        if out_amount > 0:
                            return True  # Can sell = Safe
                        else:
                            if self.VERBOSE:
                                print("      ⚠️ Honeypot: Sell returns $0")
                            return False

                    # Check for error response
                    if "error" in data:
                        if self.VERBOSE:
                            print(f"      ⚠️ Honeypot: {data['error']}")
                        return False

                # No route found could mean low liquidity, not necessarily honeypot
                if resp.status_code == 400:
                    if self.VERBOSE:
                        print("      ⚠️ No sell route found (low liquidity?)")
                    return True  # Give benefit of doubt

            except Exception:
                # Try next endpoint
                continue

        # All endpoints failed - fail open for established tokens
        if self.VERBOSE:
            print("      ⚠️ Honeypot check skipped (API unavailable)")
        return True

    def check_liquidity(self, mint: str) -> Tuple[bool, float]:
        """
        Check token liquidity using DexScreener API.

        Returns:
            Tuple of (is_sufficient, liquidity_usd)
        """
        try:
            time.sleep(self.DEXSCREENER_DELAY)

            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])

                if not pairs:
                    if self.VERBOSE:
                        print("      ⚠️ No trading pairs found")
                    return False, 0.0

                # Get the pair with highest liquidity
                max_liquidity = 0.0
                for pair in pairs:
                    liquidity = pair.get("liquidity", {})
                    usd = liquidity.get("usd", 0) or 0
                    max_liquidity = max(max_liquidity, float(usd))

                # V89.4: Use Paper Liquidity settings if in Paper Mode
                if not Settings.ENABLE_TRADING and hasattr(
                    Settings, "PAPER_MIN_LIQUIDITY"
                ):
                    threshold = Settings.PAPER_MIN_LIQUIDITY
                else:
                    threshold = Settings.MIN_LIQUIDITY_USD

                is_sufficient = max_liquidity >= threshold

                if not is_sufficient:
                    if self.VERBOSE:
                        print(
                            f"      ⚠️ Low liquidity: ${max_liquidity:,.0f} < ${threshold:,.0f}"
                        )

                return is_sufficient, max_liquidity

            if self.VERBOSE:
                print(f"      ⚠️ DexScreener API error: {resp.status_code}")
            return True, 0.0  # Fail open

        except Exception as e:
            if self.VERBOSE:
                print(f"      ❌ Liquidity check failed: {e}")
            return True, 0.0

    def check_top_holders(self, mint: str) -> Tuple[bool, float]:
        """
        Check concentration of Top 10 holders using Solana RPC.

        Prevents "Rug Pulls" where a few wallets hold most of the supply.

        Returns:
            Tuple of (is_safe, top10_percentage)
        """
        try:
            # Get total supply first
            supply_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [mint],
            }
            resp_supply = requests.post(
                Settings.RPC_URL,
                json=supply_payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data_supply = resp_supply.json()
            total_supply = 0.0
            if "result" in data_supply and "value" in data_supply["result"]:
                total_supply = float(data_supply["result"]["value"]["uiAmount"] or 0)

            if total_supply <= 0:
                if self.VERBOSE:
                    print("      ⚠️ Could not fetch total supply")
                return True, 0.0  # Fail open

            # Get Largest Accounts (Top 20 by default)
            holders_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenLargestAccounts",
                "params": [mint],
            }
            resp_holders = requests.post(
                Settings.RPC_URL,
                json=holders_payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data_holders = resp_holders.json()

            top10_sum = 0.0
            if "result" in data_holders and "value" in data_holders["result"]:
                holders = data_holders["result"]["value"]
                # Sum top 10
                for i, holder in enumerate(holders[:10]):
                    top10_sum += float(holder["uiAmount"] or 0)

            concentration = top10_sum / total_supply
            is_safe = concentration <= Settings.MAX_TOP10_HOLDER_PCT

            if not is_safe:
                if self.VERBOSE:
                    print(
                        f"      ⚠️ High Concentration: Top 10 hold {concentration * 100:.1f}%"
                    )

            return is_safe, concentration

        except requests.exceptions.Timeout:
            if self.VERBOSE:
                print("      ⚠️ RPC Timeout - skipping holder check")
            return True, 0.0  # Fail open
        except requests.exceptions.ConnectionError:
            if self.VERBOSE:
                print("      ⚠️ RPC Connection Error - skipping holder check")
            return True, 0.0  # Fail open
        except Exception as e:
            if self.VERBOSE:
                print(f"      ⚠️ Holder check failed: {str(e)[:50]}")
            return True, 0.0  # Fail open

    def quick_validate(self, mint: str) -> bool:
        """
        Quick validation for pre-trade checks.
        Only runs honeypot simulation (fastest check).

        Returns:
            True if token appears safe
        """
        return self.check_honeypot(mint)

    def is_token_2022(self, mint: str) -> bool:
        """
        V48.0: Check if token uses the Token-2022 program.

        Token-2022 tokens may have transfer fees, extensions, or other
        features that can cause swap failures. We block these for safety.

        Returns:
            True if token is Token-2022 (UNSAFE for trading)
            False if token is standard SPL Token (safe)
        """
        # Check cache first (use same cache structure)
        cache_key = f"t22_{mint}"
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_result

        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAccountInfo",
                "params": [mint, {"encoding": "jsonParsed"}],
            }

            resp = requests.post(
                Settings.RPC_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            data = resp.json()

            if "result" in data and data["result"] and "value" in data["result"]:
                value = data["result"]["value"]
                if value:
                    # The 'owner' field contains the program ID
                    owner = value.get("owner", "")

                    is_2022 = owner == TOKEN_2022_PROGRAM_ID

                    # Cache result
                    self.cache[cache_key] = (time.time(), is_2022)

                    if is_2022:
                        if self.VERBOSE:
                            print(f"      ⚠️ Token-2022 DETECTED: {mint[:8]}...")

                    return is_2022

            # Could not determine - fail open (assume standard token)
            return False

        except Exception as e:
            if self.VERBOSE:
                print(f"      ⚠️ Token-2022 check failed: {e}")
            return False  # Fail open
