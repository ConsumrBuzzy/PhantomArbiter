"""
Test: Whale-Pulse Confidence Boost Verification
================================================
Verifies that the Rust SignalScorer correctly applies the whale_confidence_bonus
from SharedTokenMetadata when computing confidence.

Run: python tests/test_whale_boost.py
"""
import sys
sys.path.insert(0, '.')

def test_whale_boost():
    """Test that whale bonus increases confidence in ValidatedSignal."""
    from phantom_core import SharedTokenMetadata, ScorerConfig, SignalScorer
    
    # Create config
    config = ScorerConfig(
        min_profit_usd=0.10,
        max_slippage_bps=500,
        gas_fee_usd=0.02,
        jito_tip_usd=0.001,
        dex_fee_bps=30,
        default_trade_size_usd=15.0
    )
    scorer = SignalScorer(config)
    
    # Create base metadata (profitable trade)
    metadata = SharedTokenMetadata("TestMint123")
    metadata.symbol = "WHALE_TEST"
    metadata.is_rug_safe = True
    metadata.lp_locked_pct = 0.9
    metadata.has_mint_auth = False
    metadata.liquidity_usd = 50000.0
    metadata.spread_bps = 300  # 3% spread (profitable)
    metadata.order_imbalance = 1.3
    metadata.velocity_1m = 0.03
    metadata.whale_confidence_bonus = 0.0  # No bonus initially
    
    # Score WITHOUT whale bonus
    result_no_bonus = scorer.score_trade(metadata, 15.0)
    
    if result_no_bonus is None:
        print("❌ Trade rejected (check spread/frictions)")
        return False
    
    confidence_no_bonus = result_no_bonus.confidence
    print(f"📊 Confidence WITHOUT whale bonus: {confidence_no_bonus:.2%}")
    
    # Now apply whale bonus
    metadata.whale_confidence_bonus = 0.25  # $25k+ whale
    
    # Score WITH whale bonus
    result_with_bonus = scorer.score_trade(metadata, 15.0)
    
    if result_with_bonus is None:
        print("❌ Trade rejected with bonus (unexpected)")
        return False
    
    confidence_with_bonus = result_with_bonus.confidence
    print(f"🐋 Confidence WITH whale bonus:    {confidence_with_bonus:.2%}")
    
    # Verify boost
    delta = confidence_with_bonus - confidence_no_bonus
    print(f"📈 Confidence Delta:               +{delta:.2%}")
    
    if delta >= 0.20:  # At least 20% boost (we set 0.25)
        print("\n✅ PASS: Whale-Pulse integration verified!")
        return True
    else:
        print(f"\n❌ FAIL: Expected +0.25, got +{delta:.2f}")
        return False


def test_tiered_bonuses():
    """Test different whale bonus tiers."""
    from phantom_core import SharedTokenMetadata, ScorerConfig, SignalScorer
    
    config = ScorerConfig(
        min_profit_usd=0.10,
        max_slippage_bps=500,
        gas_fee_usd=0.02,
        jito_tip_usd=0.001,
        dex_fee_bps=30,
        default_trade_size_usd=15.0
    )
    scorer = SignalScorer(config)
    
    print("\n🐋 Testing Tiered Whale Bonuses...")
    print("=" * 50)
    
    tiers = [
        (0.0, "No Whale"),
        (0.05, "$1k-5k"),
        (0.15, "$5k-25k"),
        (0.25, "$25k-100k"),
        (0.35, "$100k+"),
    ]
    
    base_metadata = SharedTokenMetadata("TierTest")
    base_metadata.symbol = "TIER"
    base_metadata.is_rug_safe = True
    base_metadata.lp_locked_pct = 0.9
    base_metadata.has_mint_auth = False
    base_metadata.liquidity_usd = 50000.0
    base_metadata.spread_bps = 300
    base_metadata.order_imbalance = 1.3
    base_metadata.velocity_1m = 0.03
    
    for bonus, tier_name in tiers:
        base_metadata.whale_confidence_bonus = bonus
        result = scorer.score_trade(base_metadata, 15.0)
        if result:
            print(f"  {tier_name:12} (+{bonus:.2f}) → Confidence: {result.confidence:.2%}")
        else:
            print(f"  {tier_name:12} (+{bonus:.2f}) → REJECTED")
    
    print("=" * 50)
    print("✅ Tiered bonus test complete")


if __name__ == "__main__":
    print("=" * 60)
    print("  WHALE-PULSE CONFIDENCE BOOST TEST")
    print("=" * 60)
    
    success = test_whale_boost()
    test_tiered_bonuses()
    
    sys.exit(0 if success else 1)
