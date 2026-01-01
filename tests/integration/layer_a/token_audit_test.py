"""
V83.1: Token Standard Audit Test
=================================
Verifies that get_token_program_id correctly identifies SPL vs Token-2022.

Run: python tests/token_audit_test.py
"""

import sys

sys.path.insert(0, ".")

from src.core.token_standards import (
    detect_token_standard_rpc,
    TokenStandard,
    SPL_TOKEN_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
)


# Known test cases
TEST_TOKENS = {
    # SPL Token (Original) - Should return SPL_TOKEN
    "So11111111111111111111111111111111111111112": {
        "name": "Wrapped SOL",
        "expected": TokenStandard.SPL_TOKEN,
    },
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": {
        "name": "USDC",
        "expected": TokenStandard.SPL_TOKEN,
    },
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": {
        "name": "USDT",
        "expected": TokenStandard.SPL_TOKEN,
    },
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": {
        "name": "JUP",
        "expected": TokenStandard.SPL_TOKEN,
    },
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": {
        "name": "BONK",
        "expected": TokenStandard.SPL_TOKEN,
    },
    # Token-2022 - Should return TOKEN_2022
    # Add known Token-2022 mints here as you discover them
    # Example: Tax tokens, soulbound tokens, etc.
}


def run_audit():
    """Run the token standard audit."""
    print("=" * 60)
    print("🔍 V83.1: Token Standard Audit")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for mint, info in TEST_TOKENS.items():
        name = info["name"]
        expected = info["expected"]

        # Detect
        actual, account_info = detect_token_standard_rpc(mint)

        # Compare
        status = "✅" if actual == expected else "❌"

        if actual == expected:
            passed += 1
        else:
            failed += 1

        print(
            f"{status} {name:<15} | {mint[:8]}... | Expected: {expected.value:<10} | Got: {actual.value}"
        )

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print()
        print("⚠️  FAILURES DETECTED - Review token_standards.py")
        return 1
    else:
        print()
        print("✅ All token standards detected correctly!")
        return 0


def test_program_ids():
    """Verify program ID constants are correct."""
    print()
    print("📋 Program ID Verification:")
    print(f"   SPL Token: {SPL_TOKEN_PROGRAM_ID}")
    print(f"   Token-2022: {TOKEN_2022_PROGRAM_ID}")
    print()

    # Known correct values
    assert SPL_TOKEN_PROGRAM_ID == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", (
        "SPL Token ID mismatch!"
    )
    assert TOKEN_2022_PROGRAM_ID == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", (
        "Token-2022 ID mismatch!"
    )
    print("✅ Program IDs verified")


if __name__ == "__main__":
    test_program_ids()
    exit_code = run_audit()
    exit(exit_code)
