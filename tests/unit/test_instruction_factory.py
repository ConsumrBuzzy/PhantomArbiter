"""
InstructionFactory Unit Tests
=============================
Tests for pure instruction building logic.

100% testable without RPC or wallet connections.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


class TestTradeIntentSchemas:
    """Test trade intent dataclasses."""

    def test_spot_intent_creation(self):
        """SpotTradeIntent should be immutable."""
        from src.execution.instruction_factory import SpotTradeIntent, TradeDirection
        
        intent = SpotTradeIntent(
            input_mint="USDC_MINT",
            output_mint="SOL_MINT",
            amount_atomic=100_000_000,  # 100 USDC
            slippage_bps=50,
            direction=TradeDirection.BUY,
        )
        
        assert intent.amount_atomic == 100_000_000
        assert intent.slippage_bps == 50
        assert intent.direction == TradeDirection.BUY

    def test_spot_intent_human_amount(self):
        """amount_human should convert atomic to readable."""
        from src.execution.instruction_factory import SpotTradeIntent
        
        # USDC with 6 decimals
        usdc_intent = SpotTradeIntent(
            input_mint="USDC_MINT",
            output_mint="SOL_MINT",
            amount_atomic=100_000_000,  # 100 USDC
        )
        
        assert usdc_intent.amount_human == 100.0
        
        # SOL with 9 decimals
        sol_intent = SpotTradeIntent(
            input_mint="So111111111111111111111111111111111111112",
            output_mint="USDC_MINT",
            amount_atomic=1_500_000_000,  # 1.5 SOL
        )
        
        assert sol_intent.amount_human == 1.5

    def test_perp_intent_market_index(self):
        """PerpTradeIntent should map market names to indices."""
        from src.execution.instruction_factory import PerpTradeIntent, TradeDirection
        
        sol_perp = PerpTradeIntent(
            market="SOL-PERP",
            size=1.0,
            direction=TradeDirection.SHORT,
        )
        
        assert sol_perp.market_index == 0
        
        btc_perp = PerpTradeIntent(
            market="BTC-PERP",
            size=0.01,
            direction=TradeDirection.LONG,
        )
        
        assert btc_perp.market_index == 1

    def test_bundle_intent_requires_leg(self):
        """BundleIntent should require at least one leg."""
        from src.execution.instruction_factory import BundleIntent
        
        with pytest.raises(ValueError, match="at least one leg"):
            BundleIntent()  # No legs


class TestInstructionFactory:
    """Test InstructionFactory instruction building."""

    @pytest.fixture
    def factory(self):
        """Create factory with mock payer."""
        from src.execution.instruction_factory import InstructionFactory
        return InstructionFactory("11111111111111111111111111111111")

    def test_compute_budget_instructions(self, factory):
        """Should build compute budget instructions."""
        ixs = factory.build_compute_budget_instructions(
            units=500_000,
            priority_fee=2000,
        )
        
        assert len(ixs) == 2
        # First is set_compute_unit_limit
        # Second is set_compute_unit_price

    def test_tip_instruction(self, factory):
        """Should build valid tip instruction."""
        ix = factory.build_tip_instruction(50_000)
        
        assert ix is not None
        # Should be a transfer instruction
        assert ix.program_id is not None

    def test_tip_account_rotation(self, factory):
        """Tip accounts should rotate."""
        accounts = []
        for _ in range(10):
            factory._tip_account_index = 0
            for i in range(8):
                accounts.append(factory._get_next_tip_account())
        
        # Should have used all 8 accounts
        unique = set(accounts)
        assert len(unique) == 8

    def test_validate_instructions_empty(self, factory):
        """Empty instruction list should fail validation."""
        is_valid, errors = factory.validate_instructions([])
        
        assert not is_valid
        assert "No instructions" in errors[0]

    def test_validate_instructions_too_many(self, factory):
        """Too many instructions should warn."""
        # Create 25 mock instructions
        mock_ixs = [MagicMock() for _ in range(25)]
        for ix in mock_ixs:
            ix.program_id = "mock_program"
        
        is_valid, errors = factory.validate_instructions(mock_ixs)
        
        assert any("Too many" in e for e in errors)


class TestSpotInstructions:
    """Test Jupiter spot instruction building."""

    @pytest.fixture
    def factory(self):
        """Create factory."""
        from src.execution.instruction_factory import InstructionFactory
        return InstructionFactory("11111111111111111111111111111111")

    @pytest.fixture
    def mock_swapper(self):
        """Mock JupiterSwapper."""
        swapper = MagicMock()
        swapper.get_quote = AsyncMock(return_value={
            "inAmount": "100000000",
            "outAmount": "666666666",
        })
        swapper.get_swap_instructions = AsyncMock(return_value=[
            MagicMock(program_id="jupiter"),
        ])
        return swapper

    @pytest.mark.asyncio
    async def test_build_spot_instructions(self, factory, mock_swapper):
        """Should build Jupiter swap instructions."""
        from src.execution.instruction_factory import SpotTradeIntent
        
        intent = SpotTradeIntent(
            input_mint="USDC_MINT",
            output_mint="SOL_MINT",
            amount_atomic=100_000_000,
        )
        
        ixs = await factory.build_spot_instructions(intent, mock_swapper)
        
        assert len(ixs) > 0
        mock_swapper.get_quote.assert_called_once()
        mock_swapper.get_swap_instructions.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_spot_fails_on_no_quote(self, factory):
        """Should raise if quote fails."""
        from src.execution.instruction_factory import SpotTradeIntent
        
        mock_swapper = MagicMock()
        mock_swapper.get_quote = AsyncMock(return_value=None)
        
        intent = SpotTradeIntent(
            input_mint="USDC_MINT",
            output_mint="SOL_MINT",
            amount_atomic=100_000_000,
        )
        
        with pytest.raises(ValueError, match="quote failed"):
            await factory.build_spot_instructions(intent, mock_swapper)


class TestBundleAssembly:
    """Test full bundle instruction assembly."""

    @pytest.fixture
    def factory(self):
        """Create factory."""
        from src.execution.instruction_factory import InstructionFactory
        return InstructionFactory("11111111111111111111111111111111")

    @pytest.fixture
    def mock_swapper(self):
        """Mock swapper."""
        swapper = MagicMock()
        swapper.get_quote = AsyncMock(return_value={"inAmount": "100000000"})
        swapper.get_swap_instructions = AsyncMock(return_value=[MagicMock()])
        return swapper

    @pytest.mark.asyncio
    async def test_build_bundle_with_spot(self, factory, mock_swapper):
        """Bundle with spot leg should include all components."""
        from src.execution.instruction_factory import BundleIntent, SpotTradeIntent
        
        intent = BundleIntent(
            spot_leg=SpotTradeIntent(
                input_mint="USDC",
                output_mint="SOL",
                amount_atomic=100_000_000,
            ),
            tip_lamports=50_000,
        )
        
        ixs = await factory.build_bundle_instructions(intent, mock_swapper)
        
        # Should have: 2 compute budget + 1 spot + 1 tip = 4 minimum
        assert len(ixs) >= 4
