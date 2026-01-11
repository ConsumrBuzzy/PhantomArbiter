"""
DNEM Drift Order Builder
========================
Builds raw Drift Protocol instructions for Jito bundle integration.

This module provides the critical bridge between DNEM's SyncExecution
and Drift Protocol's perpetual futures. The key requirement is extracting
RAW INSTRUCTIONS (not signed transactions) that can be bundled with
Jupiter spot instructions.

Architecture:
1. DriftOrderBuilder produces Instruction objects
2. SyncExecution combines them with Jupiter instructions
3. Jito bundle submits both atomically

Drift Protocol uses a "Cranking" system:
- Market orders are filled by keepers
- For best execution, we use IOC (Immediate-or-Cancel) orders
- Position changes are immediate, no separate "crank" needed for taker orders

References:
- Drift SDK: https://github.com/drift-labs/protocol-v2
- Drift Program ID: dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH
"""

from __future__ import annotations

import base64
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey

from src.shared.system.logging import Logger


# =============================================================================
# CONSTANTS
# =============================================================================

# Drift Program ID (mainnet)
DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")

# Market indices (Drift uses numeric indices)
MARKET_INDICES = {
    "SOL-PERP": 0,
    "BTC-PERP": 1,
    "ETH-PERP": 2,
    "APT-PERP": 3,
    "1MBONK-PERP": 4,
    "POL-PERP": 5,
    "ARB-PERP": 6,
    "DOGE-PERP": 7,
    "BNB-PERP": 8,
}

# Oracle pubkeys for price feeds (from on-chain PerpMarket/SpotMarket offset 40)
ORACLES = {
    "SOL-PERP": Pubkey.from_string("3m6i4RFWEDw2Ft4tFHPJtYgmpPe21k56M3FHeWYrgGBz"),  # On-chain canonical
    "BTC-PERP": Pubkey.from_string("35MbvS1Juz2wf7GsyHrkCw8yfKciRLxVpEhfZDZFrB4R"),
    "ETH-PERP": Pubkey.from_string("93FG52TzNKCnMiasV14Ba34BYcHDb9p4zK4GjZnLwqWR"),
    "USDC-SPOT": Pubkey.from_string("9VCioxmni2gDLv11qufWzT3RDERhQE4iY5Gf7NTfYyAV"),  # On-chain canonical
}


# =============================================================================
# ENUMS & TYPES
# =============================================================================


class OracleSource(Enum):
    """Drift OracleSource Enum."""

    PYTH = 0
    SWITCHBOARD = 1
    QUOTE_ASSET = 2
    PYTH_1K = 3
    PYTH_1M = 4
    PYTH_STABLE_COIN = 5
    PRELAUNCH = 6
    PYTH_PULL = 7
    PYTH_1K_PULL = 8
    PYTH_1M_PULL = 9
    PYTH_STABLE_COIN_PULL = 10
    SWITCHBOARD_ON_DEMAND = 11
    PYTH_LAZER = 12
    PYTH_LAZER_1K = 13
    PYTH_LAZER_1M = 14
    PYTH_LAZER_STABLE_COIN = 15


class PositionDirection(Enum):
    """Direction of perp position."""
    LONG = 0
    SHORT = 1


class OrderType(Enum):
    """Drift order types."""
    MARKET = 0
    LIMIT = 1
    TRIGGER_MARKET = 2
    TRIGGER_LIMIT = 3
    ORACLE = 4


class MarketType(Enum):
    """Drift market types."""
    SPOT = 0
    PERP = 1


@dataclass(frozen=True, slots=True)
class DriftOrderParams:
    """Parameters for a Drift order."""
    
    market_index: int
    direction: PositionDirection
    base_asset_amount: int  # In base units (1e9 for SOL)
    order_type: OrderType = OrderType.MARKET
    market_type: MarketType = MarketType.PERP
    reduce_only: bool = False
    price: int = 0  # 0 for market orders (PRICE_PRECISION = 1e6)
    
    def to_bytes(self) -> bytes:
        """
        Serialize OrderParams to bytes matching Drift IDL v2.140.0 exactly.
        
        CRITICAL LAYOUT (17 fields, 37 bytes total):
        - Discriminator: 8 bytes
        - Fixed fields (1-10): 22 bytes
        - Option/Enum fields (11-17): 7 bytes (all None/default)
        
        Field 13 (triggerCondition) is a DIRECT enum u8, NOT an Option!
        This was the source of the 0x66 deserialization error.
        """
        import struct
        
        # place_perp_order discriminator = sha256("global:place_perp_order")[:8]
        data = bytearray([69, 161, 93, 202, 120, 126, 76, 185])
        
        # ===== FIXED FIELDS (1-10) = 22 bytes =====
        
        # 1. orderType (u8 enum): Market=0, Limit=1, TriggerMarket=2, TriggerLimit=3, Oracle=4
        data.append(self.order_type.value)
        
        # 2. marketType (u8 enum): Spot=0, Perp=1
        data.append(self.market_type.value)
        
        # 3. direction (u8 enum): Long=0, Short=1
        data.append(self.direction.value)
        
        # 4. userOrderId (u8)
        data.append(0)
        
        # 5. baseAssetAmount (u64) - little-endian
        data.extend(struct.pack("<Q", self.base_asset_amount))
        
        # 6. price (u64) - little-endian, 0 for market orders
        data.extend(struct.pack("<Q", self.price))
        
        # 7. marketIndex (u16) - little-endian
        data.extend(struct.pack("<H", self.market_index))
        
        # 8. reduceOnly (bool -> u8)
        data.append(1 if self.reduce_only else 0)
        
        # 9. postOnly (u8 enum): None=0, MustPostOnly=1, TryPostOnly=2, Slide=3
        data.append(0)
        
        # 10. bitFlags (u8) - reserved flags
        data.append(0)
        
        # ===== OPTION/ENUM FIELDS (11-17) = 7 bytes =====
        # Option<T> serialization: 0x00 = None, 0x01 + value = Some(value)
        
        # 11. maxTs (Option<i64>) -> None
        data.append(0)
        
        # 12. triggerPrice (Option<u64>) -> None
        data.append(0)
        
        # 13. triggerCondition (u8 enum, NOT an Option!): Above=0, Below=1, TriggeredAbove=2, TriggeredBelow=3
        data.append(0)  # Above
        
        # 14. oraclePriceOffset (Option<i32>) -> None
        data.append(0)
        
        # 15. auctionDuration (Option<u8>) -> None
        data.append(0)
        
        # 16. auctionStartPrice (Option<i64>) -> None
        data.append(0)
        
        # 17. auctionEndPrice (Option<i64>) -> None
        data.append(0)
        
        # Total: 8 + 22 + 7 = 37 bytes
        return bytes(data)



@dataclass
class DriftPosition:
    """Current position info from Drift."""
    
    market: str
    size: float  # Positive = long, Negative = short
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float = 1.0
    
    @property
    def is_short(self) -> bool:
        return self.size < 0
    
    @property
    def is_long(self) -> bool:
        return self.size > 0
    
    @property
    def notional_usd(self) -> float:
        return abs(self.size * self.mark_price)


# =============================================================================
# DRIFT ORDER BUILDER
# =============================================================================


class DriftOrderBuilder:
    """
    Builds raw Drift instructions for atomic Jito bundling.
    
    Key principle: We need INSTRUCTIONS, not transactions.
    The SyncExecution will bundle these with Jupiter instructions.
    
    Example:
        >>> builder = DriftOrderBuilder(wallet_pubkey, user_account)
        >>> instructions = await builder.build_short_order("SOL-PERP", 0.5)
        >>> # instructions can now be added to Jito bundle
    """
    
    # Base precision units
    BASE_PRECISION = 10**9  # 1 SOL = 1e9 base units
    PRICE_PRECISION = 10**6  # Drift uses 6 decimals for price
    
    def __init__(
        self,
        wallet_pubkey: Pubkey,
        user_account: Optional[Pubkey] = None,
        user_stats: Optional[Pubkey] = None,
        state: Optional[Pubkey] = None,
    ):
        # Convert string to Pubkey if needed
        if isinstance(wallet_pubkey, str):
            wallet_pubkey = Pubkey.from_string(wallet_pubkey)
            
        self.wallet = wallet_pubkey
        
        # Derive accounts if not provided
        self.user_account = user_account or self._derive_user_account()
        self.user_stats = user_stats or self._derive_user_stats()
        self.state = state or self._get_drift_state()
        
        # Cache for market accounts
        self._perp_markets: dict[int, Pubkey] = {}
        self._spot_markets: dict[int, Pubkey] = {}
    
    def _derive_user_account(self) -> Pubkey:
        """Derive the user's Drift account PDA."""
        # PDA: seeds = ["user", authority.pubkey(), subaccount_id(0)]
        user_pda, _ = Pubkey.find_program_address(
            [
                b"user",
                bytes(self.wallet),
                (0).to_bytes(2, 'little'),  # subaccount_id = 0
            ],
            DRIFT_PROGRAM_ID,
        )
        return user_pda
    
    def _derive_user_stats(self) -> Pubkey:
        """Derive the user stats account PDA."""
        stats_pda, _ = Pubkey.find_program_address(
            [
                b"user_stats",
                bytes(self.wallet),
            ],
            DRIFT_PROGRAM_ID,
        )
        return stats_pda
    
    def _get_drift_state(self) -> Pubkey:
        """Get the Drift state account (derived)."""
        state_pda, _ = Pubkey.find_program_address(
            [b"drift_state"],
            DRIFT_PROGRAM_ID,
        )
        return state_pda
    
    def _get_perp_market(self, market_index: int) -> Pubkey:
        """Get or derive perp market account."""
        if market_index not in self._perp_markets:
            pda, _ = Pubkey.find_program_address(
                [
                    b"perp_market",
                    market_index.to_bytes(2, 'little'),
                ],
                DRIFT_PROGRAM_ID,
            )
            self._perp_markets[market_index] = pda
        return self._perp_markets[market_index]
    
    def _get_oracle(self, market: str) -> Pubkey:
        """Get oracle pubkey for market."""
        return ORACLES.get(market, ORACLES["SOL-PERP"])
    
    # =========================================================================
    # ORDER BUILDERS
    # =========================================================================
    
    def build_initialize_user_instruction(self) -> Instruction:
        """Initialize User account (required before trading)."""
        # Discriminator (initialize_user): [111, 17, 185, 250, 60, 122, 38, 254]
        data = bytearray([111, 17, 185, 250, 60, 122, 38, 254])
        # sub_account_id (u16=0)
        data.extend((0).to_bytes(2, 'little'))
        # name (32 bytes empty)
        data.extend(bytes([0]*32))

        accounts = [
            AccountMeta(self.user_account, is_signer=False, is_writable=True),
            AccountMeta(self.user_stats, is_signer=False, is_writable=True),
            AccountMeta(self.state, is_signer=False, is_writable=False),
            AccountMeta(self.wallet, is_signer=True, is_writable=True), # Authority
            AccountMeta(self.wallet, is_signer=True, is_writable=True), # Payer
            AccountMeta(Pubkey.from_string("SysvarRent111111111111111111111111111111111"), is_signer=False, is_writable=False),
            AccountMeta(Pubkey.from_string("11111111111111111111111111111111"), is_signer=False, is_writable=False),
        ]
        return Instruction(DRIFT_PROGRAM_ID, bytes(data), accounts)

    def build_order_instruction(
        self,
        market: str,
        size: float,
        direction: PositionDirection,
        reduce_only: bool = False,
    ) -> Instruction:
        """
        Build a Drift perp order instruction.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            size: Size in base units (e.g., 0.5 = 0.5 SOL)
            direction: LONG or SHORT
            reduce_only: If True, only reduces existing position
        
        Returns:
            Instruction ready for Jito bundling
        """
        market_index = MARKET_INDICES.get(market, 0)
        base_amount = int(size * self.BASE_PRECISION)
        
        params = DriftOrderParams(
            market_index=market_index,
            direction=direction,
            base_asset_amount=base_amount,
            order_type=OrderType.MARKET,
            reduce_only=reduce_only,
        )
        
        # Build account metas
        accounts = self._build_order_accounts(market_index, market)
        
        return Instruction(
            program_id=DRIFT_PROGRAM_ID,
            accounts=accounts,
            data=params.to_bytes(),
        )
    
    def build_short_order(
        self,
        market: str,
        size: float,
        reduce_only: bool = False,
    ) -> List[Instruction]:
        """
        Build instructions to SHORT a perp market.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            size: Size in base units (positive, e.g., 0.5 for 0.5 SOL short)
            reduce_only: Only reduce existing long position
        
        Returns:
            List of instructions (may include health check)
        """
        Logger.info(f"[DRIFT] Building SHORT order: {size} {market}")
        
        order_ix = self.build_order_instruction(
            market=market,
            size=size,
            direction=PositionDirection.SHORT,
            reduce_only=reduce_only,
        )
        
        return [order_ix]
    
    def build_long_order(
        self,
        market: str,
        size: float,
        reduce_only: bool = False,
    ) -> List[Instruction]:
        """
        Build instructions to LONG a perp market.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            size: Size in base units (positive)
            reduce_only: Only reduce existing short position
        
        Returns:
            List of instructions
        """
        Logger.info(f"[DRIFT] Building LONG order: {size} {market}")
        
        order_ix = self.build_order_instruction(
            market=market,
            size=size,
            direction=PositionDirection.LONG,
            reduce_only=reduce_only,
        )
        
        return [order_ix]
    
    def build_close_position(self, market: str, current_size: float) -> List[Instruction]:
        """
        Build instructions to close an entire position.
        
        Args:
            market: Market symbol
            current_size: Current position size (negative = short)
        
        Returns:
            Instructions to reduce position to zero
        """
        if current_size == 0:
            return []
        
        # If currently short (negative), need to LONG to close
        # If currently long (positive), need to SHORT to close
        if current_size < 0:
            # Short position → Long to close
            return self.build_long_order(
                market=market,
                size=abs(current_size),
                reduce_only=True,
            )
        else:
            # Long position → Short to close
            return self.build_short_order(
                market=market,
                size=current_size,
                reduce_only=True,
            )
    
    # =========================================================================
    # ACCOUNT BUILDERS
    # =========================================================================
    
    def _build_order_accounts(self, market_index: int, market: str) -> List[AccountMeta]:
        """
        Builds the account list for place_perp_order.
        
        Account sequence per Drift SDK (getRemainingAccounts):
        Named accounts (3):
          1. state (read)
          2. user (write) 
          3. authority (signer)
        
        Remaining accounts ORDER (critical!):
          1. oracles first (perp oracle, quote oracle)
          2. spot markets second (quote spot market)
          3. perp markets third (perp market)
        """
        # Derive PDAs
        state_pda, _ = Pubkey.find_program_address(
            [b"drift_state"], DRIFT_PROGRAM_ID
        )
        
        perp_market_pda, _ = Pubkey.find_program_address(
            [b"perp_market", market_index.to_bytes(2, "little")], DRIFT_PROGRAM_ID
        )
        
        # Quote spot market (USDC = index 0)
        quote_spot_market_pda, _ = Pubkey.find_program_address(
            [b"spot_market", (0).to_bytes(2, "little")], DRIFT_PROGRAM_ID
        )

        perp_oracle = self._get_oracle(market)
        quote_oracle = ORACLES.get("USDC-SPOT", Pubkey.from_string("En8hkHLkRe9d9DraYmBTrus518BvmVH448YcvmrFM6Ce"))

        return [
            # Named Accounts (per IDL: state, user, authority)
            AccountMeta(state_pda, is_signer=False, is_writable=False),
            AccountMeta(self.user_account, is_signer=False, is_writable=True),
            AccountMeta(self.wallet, is_signer=True, is_writable=False),
            
            # Remaining Accounts - ORDER MATTERS! (oracles, spot markets, perp markets)
            # 1. Oracles first
            AccountMeta(perp_oracle, is_signer=False, is_writable=False),
            AccountMeta(quote_oracle, is_signer=False, is_writable=False),
            # 2. Spot markets second
            AccountMeta(quote_spot_market_pda, is_signer=False, is_writable=False),
            # 3. Perp markets third
            AccountMeta(perp_market_pda, is_signer=False, is_writable=True),
        ]
    
    # =========================================================================
    # POSITION HELPERS
    # =========================================================================
    
    async def get_position(self, market: str) -> Optional[DriftPosition]:
        """
        Fetch current position from Drift.
        
        TODO: Implement RPC call to fetch user's perp position.
        For now returns None (no position).
        """
        # Placeholder - requires Drift account deserialization
        Logger.debug(f"[DRIFT] Fetching position for {market}")
        return None
    
    def get_user_equity(self) -> float:
        """
        Fetch user equity (USDC collateral) from on-chain account.
        Uses cached valid endpoints via get_rpc_pool().
        """
        try:
            import struct
            from src.shared.system.rpc_pool import get_rpc_pool
            
            # Derive user account if not set
            if not self.user_account:
                self._derive_user_account()
            
            if not self.user_account:
                 return 0.0

            rpc = get_rpc_pool()
            endpoint = rpc.get_next_endpoint()
            
            # Manual request
            import requests
            import base64
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1, 
                "method": "getAccountInfo",
                "params": [
                    str(self.user_account),
                    {"encoding": "base64"}
                ]
            }
            
            try:
                # Short timeout to avoid blocking heartbeat
                resp = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=3).json()
            except:
                return 0.0
            
            if "result" in resp and resp["result"] and "value" in resp["result"] and resp["result"]["value"]:
                data_b64 = resp["result"]["value"]["data"][0]
                data = base64.b64decode(data_b64)
                
                # Metric confirmed offset 128 for USDC balance (i64)
                if len(data) > 130:
                    offset = 128
                    raw = struct.unpack('<q', data[offset:offset+8])[0]
                    if 0 < raw < 10**15:
                        return raw / 10**6
            
            return 0.0
            
        except Exception:
            return 0.0

    def calculate_required_collateral(

        self,
        size: float,
        price: float,
        leverage: float = 1.0,
    ) -> float:
        """
        Calculate USDC collateral required for a position.
        
        Drift allows up to 10x leverage on most markets.
        """
        notional = size * price
        return notional / leverage


# =============================================================================
# FACTORY
# =============================================================================


def create_drift_order_builder(wallet: Any) -> DriftOrderBuilder:
    """
    Factory to create a DriftOrderBuilder from a wallet manager.
    
    Args:
        wallet: WalletManager or similar with get_public_key() method
    
    Returns:
        Configured DriftOrderBuilder
    """
    pubkey = wallet.get_public_key() if hasattr(wallet, 'get_public_key') else wallet
    return DriftOrderBuilder(Pubkey.from_string(str(pubkey)))


# =============================================================================
# ADAPTER BRIDGE
# =============================================================================


class DriftAdapter:
    """
    Simplified adapter for DNEM integration.
    
    Wraps DriftOrderBuilder with async interface matching
    what SyncExecution expects.
    """
    
    def __init__(self, network: str = "mainnet"):
        self.network = network
        self._builder: Optional[DriftOrderBuilder] = None
        self._wallet: Optional[Any] = None
    
    def set_wallet(self, wallet: Any) -> None:
        """Set wallet and initialize builder."""
        self._wallet = wallet
        if hasattr(wallet, 'get_public_key'):
            pk = wallet.get_public_key()
            # Ensure Pubkey object
            if isinstance(pk, str):
                pk = Pubkey.from_string(pk)
            self._builder = DriftOrderBuilder(pk)
    
    async def get_short_instructions(
        self,
        market: str,
        size: float,
    ) -> List[Instruction]:
        """Get instructions to open/increase short position."""
        if not self._builder:
            raise RuntimeError("DriftAdapter: wallet not set")
        return self._builder.build_short_order(market, size)
    
    async def get_long_instructions(
        self,
        market: str,
        size: float,
    ) -> List[Instruction]:
        """Get instructions to open/increase long position."""
        if not self._builder:
            raise RuntimeError("DriftAdapter: wallet not set")
        return self._builder.build_long_order(market, size)
    
    async def get_close_instructions(
        self,
        market: str,
        current_size: float,
    ) -> List[Instruction]:
        """Get instructions to close a position."""
        if not self._builder:
            raise RuntimeError("DriftAdapter: wallet not set")
        return self._builder.build_close_position(market, current_size)
    
    async def get_position(self, market: str) -> Optional[DriftPosition]:
        """Get current position for market."""
        if not self._builder:
            return None
        return await self._builder.get_position(market)

    def get_user_equity(self) -> float:
        """Get total account equity (USDC)."""
        if not self._builder:
            return 0.0
        return self._builder.get_user_equity()
