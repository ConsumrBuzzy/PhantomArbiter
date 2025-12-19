"""
V49.0: Orca Whirlpools Adapter
==============================
Low-level integration with Orca's Concentrated Liquidity Market Maker (CLMM).

This adapter uses direct RPC calls to avoid SDK dependency issues on Windows.
It fetches pool state, calculates tick ranges, and builds transaction instructions.

References:
- Whirlpool Program: whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc
- Orca Docs: https://docs.orca.so/
"""

import struct
import math
import base64
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import asdict

from src.system.logging import Logger
from src.infrastructure.rpc_balancer import RPCBalancer
from src.liquidity.types import (
    WhirlpoolState, 
    PositionState, 
    LiquidityParams,
    WHIRLPOOL_PROGRAM_ID,
)

# Well-known token mints
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Common tick spacings on Orca (determines fee tier)
# 1 = 0.01% fee, 8 = 0.05% fee, 64 = 0.30% fee, 128 = 1.00% fee
TICK_SPACINGS = {
    1: "0.01%",
    8: "0.05%", 
    64: "0.30%",
    128: "1.00%",
}

# Verified pool addresses from Orca API (mainnet)
# Fetched from https://api.mainnet.orca.so/v1/whirlpool/list
KNOWN_POOLS = {
    # SOL/USDC pools (different fee tiers)
    "SOL-USDC-0.04%": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",  # TVL: $32.5M (MAIN)
    "SOL-USDC-0.02%": "FpCMFDFGYotvufJ7HrFHsWEiiQCGbkLCtwHiDnh7o28Q",  # TVL: $579K
    "SOL-USDC-0.05%": "7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm",  # TVL: $521K
}


class OrcaAdapter:
    """
    V49.0: Orca Whirlpools CLMM Integration.
    
    Provides read operations to fetch pool and position state.
    Uses PDA derivation to find Whirlpool addresses dynamically.
    
    Usage:
        adapter = OrcaAdapter()
        state = adapter.find_whirlpool(SOL_MINT, USDC_MINT)
        print(f"Current price: ${state.price:.4f}")
    """
    
    # Whirlpool account data layout offsets
    WHIRLPOOL_LAYOUT = {
        "discriminator": (0, 8),
        "whirlpools_config": (8, 40),
        "whirlpool_bump": (40, 41),
        "tick_spacing": (42, 44),
        "tick_spacing_seed": (44, 46),
        "fee_rate": (46, 48),
        "protocol_fee_rate": (48, 50),
        "liquidity": (50, 66),
        "sqrt_price": (66, 82),
        "tick_current_index": (82, 86),
        "protocol_fee_owed_a": (86, 94),
        "protocol_fee_owed_b": (94, 102),
        "token_mint_a": (102, 134),
        "token_vault_a": (134, 166),
        "fee_growth_global_a": (166, 182),
        "token_mint_b": (182, 214),
        "token_vault_b": (214, 246),
        "fee_growth_global_b": (246, 262),
        "reward_last_updated_timestamp": (262, 270),
    }
    
    def __init__(self):
        """Initialize Orca adapter with RPC connection."""
        self.rpc = RPCBalancer()
        self._cache: Dict[str, WhirlpoolState] = {}
        self._cache_ttl = 10  # seconds
        self._whirlpools_config = "2LecshUwdy9xi7meFgHtFJQNSKk4KdTrcpvaB56dP2NQ"  # Mainnet config
        Logger.info("   🐋 [ORCA] Whirlpools Adapter Initialized (PDA Mode)")
    
    # =========================================================================
    # PDA DERIVATION
    # =========================================================================
    
    def derive_whirlpool_address(self, token_a: str, token_b: str, tick_spacing: int) -> str:
        """
        Derive the PDA address for a Whirlpool.
        
        Seeds: ["whirlpool", whirlpools_config, token_mint_a, token_mint_b, tick_spacing]
        
        Note: Token mints must be sorted (token_a < token_b lexicographically)
        """
        try:
            from solders.pubkey import Pubkey
            
            # Sort token mints (Orca convention)
            if token_a > token_b:
                token_a, token_b = token_b, token_a
            
            # Build seeds
            seeds = [
                b"whirlpool",
                bytes(Pubkey.from_string(self._whirlpools_config)),
                bytes(Pubkey.from_string(token_a)),
                bytes(Pubkey.from_string(token_b)),
                tick_spacing.to_bytes(2, "little"),
            ]
            
            # Derive PDA
            program_id = Pubkey.from_string(WHIRLPOOL_PROGRAM_ID)
            pda, bump = Pubkey.find_program_address(seeds, program_id)
            
            return str(pda)
            
        except Exception as e:
            Logger.error(f"   🐋 [ORCA] PDA derivation failed: {e}")
            return ""
    
    def find_whirlpool(self, token_a: str, token_b: str) -> Optional[WhirlpoolState]:
        """
        Find the most liquid Whirlpool for a token pair.
        
        Tries common tick spacings (64, 8, 128, 1) and returns the first active pool.
        
        Args:
            token_a: First token mint address
            token_b: Second token mint address
            
        Returns:
            WhirlpoolState for the most liquid pool, or None if not found
        """
        # Try tick spacings in order of typical liquidity (64 is most common)
        for tick_spacing in [64, 8, 128, 1]:
            pda = self.derive_whirlpool_address(token_a, token_b, tick_spacing)
            
            if not pda:
                continue
            
            Logger.debug(f"   🐋 [ORCA] Trying ts={tick_spacing} → {pda[:16]}...")
            
            state = self.get_whirlpool_state(pda)
            if state:
                Logger.success(f"   🐋 [ORCA] Found pool: ts={tick_spacing} ({TICK_SPACINGS.get(tick_spacing, '?')} fee)")
                return state
        
        Logger.warning(f"   🐋 [ORCA] No active pool found for {token_a[:8]}.../{token_b[:8]}...")
        return None
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def get_whirlpool_state(self, pool_address: str) -> Optional[WhirlpoolState]:
        """
        Fetch current state of a Whirlpool.
        
        Args:
            pool_address: Base58 address of the Whirlpool account
            
        Returns:
            WhirlpoolState with current tick, price, liquidity, fees
            None if fetch fails
        """
        try:
            # Fetch account data via RPC using generic call
            response, error = self.rpc.call(
                "getAccountInfo",
                [pool_address, {"encoding": "base64"}]
            )
            
            if error:
                Logger.warning(f"   🐋 [ORCA] RPC error: {error}")
                return None
            
            # RPCBalancer returns full JSON-RPC response: {jsonrpc, id, result}
            # Extract the actual result
            result = response.get("result") if response else None
            
            if not result or result.get("value") is None:
                Logger.warning(f"   🐋 [ORCA] Pool not found: {pool_address[:8]}...")
                return None
            
            value = result["value"]
            
            # Decode base64 data
            data_b64 = value["data"][0]
            data = base64.b64decode(data_b64)
            
            if len(data) < 270:
                Logger.error(f"   🐋 [ORCA] Invalid pool data length: {len(data)}")
                return None
            
            # Parse Whirlpool account data
            state = self._parse_whirlpool_data(pool_address, data)
            
            # Cache for quick access
            self._cache[pool_address] = state
            
            return state
            
        except Exception as e:
            Logger.error(f"   🐋 [ORCA] Failed to fetch pool state: {e}")
            return None
    
    def _parse_whirlpool_data(self, address: str, data: bytes) -> WhirlpoolState:
        """Parse raw Whirlpool account data into WhirlpoolState."""
        
        # Extract fields using layout offsets
        tick_spacing = struct.unpack_from("<H", data, 42)[0]
        fee_rate = struct.unpack_from("<H", data, 46)[0]
        protocol_fee_rate = struct.unpack_from("<H", data, 48)[0]
        liquidity = struct.unpack_from("<Q", data, 50)[0]  # u128, read low 64 bits
        sqrt_price = struct.unpack_from("<Q", data, 66)[0]  # u128, read low 64 bits
        tick_current = struct.unpack_from("<i", data, 82)[0]  # i32 signed
        
        # Extract mint addresses (32 bytes each)
        token_mint_a = self._bytes_to_base58(data[102:134])
        token_mint_b = self._bytes_to_base58(data[182:214])
        
        # Fee growth globals (u128)
        fee_growth_a = struct.unpack_from("<Q", data, 166)[0]
        fee_growth_b = struct.unpack_from("<Q", data, 246)[0]
        
        # Get token decimals for accurate price calculation
        decimals_a = self._get_token_decimals(token_mint_a)
        decimals_b = self._get_token_decimals(token_mint_b)
        
        # Calculate human-readable price from sqrt_price
        # Formula: price = (sqrt_price / 2^64)^2 × 10^(decimals_a - decimals_b)
        price = self._sqrt_price_to_price(sqrt_price, decimals_a, decimals_b)
        
        return WhirlpoolState(
            address=address,
            token_mint_a=token_mint_a,
            token_mint_b=token_mint_b,
            tick_spacing=tick_spacing,
            tick_current=tick_current,
            sqrt_price=sqrt_price,
            liquidity=liquidity,
            fee_rate=fee_rate,
            protocol_fee_rate=protocol_fee_rate,
            fee_growth_global_a=fee_growth_a,
            fee_growth_global_b=fee_growth_b,
            price=price,
        )
    
    def get_pool_by_name(self, name: str) -> Optional[WhirlpoolState]:
        """
        Fetch pool state by friendly name (e.g., "SOL-USDC-1%").
        
        Args:
            name: Pool name from KNOWN_POOLS
            
        Returns:
            WhirlpoolState or None
        """
        if name not in KNOWN_POOLS:
            Logger.error(f"   🐋 [ORCA] Unknown pool: {name}")
            Logger.info(f"   🐋 [ORCA] Available pools: {list(KNOWN_POOLS.keys())}")
            return None
        
        return self.get_whirlpool_state(KNOWN_POOLS[name])
    
    # =========================================================================
    # TICK MATH UTILITIES
    # =========================================================================
    
    def price_to_tick(self, price: float, tick_spacing: int = 64) -> int:
        """
        Convert a price to the nearest valid tick index.
        
        Formula: tick = log(price) / log(1.0001)
        
        Args:
            price: Price of token B per token A
            tick_spacing: Pool's tick spacing (rounds to valid tick)
            
        Returns:
            Tick index (signed integer)
        """
        if price <= 0:
            return -443636  # MIN_TICK
        
        tick = int(math.log(price) / math.log(1.0001))
        
        # Round to nearest valid tick
        tick = (tick // tick_spacing) * tick_spacing
        
        return tick
    
    def tick_to_price(self, tick: int) -> float:
        """
        Convert a tick index to price.
        
        Formula: price = 1.0001^tick
        
        Args:
            tick: Tick index
            
        Returns:
            Price of token B per token A
        """
        return 1.0001 ** tick
    
    def calculate_range_ticks(
        self, 
        current_price: float, 
        range_pct: float, 
        tick_spacing: int = 64
    ) -> Tuple[int, int]:
        """
        Calculate tick bounds for a symmetric range around current price.
        
        Args:
            current_price: Current pool price
            range_pct: Range width as percentage (e.g., 1.0 = ±1%)
            tick_spacing: Pool's tick spacing
            
        Returns:
            (tick_lower, tick_upper) tuple
        """
        price_lower = current_price * (1 - range_pct / 100)
        price_upper = current_price * (1 + range_pct / 100)
        
        tick_lower = self.price_to_tick(price_lower, tick_spacing)
        tick_upper = self.price_to_tick(price_upper, tick_spacing)
        
        # Ensure valid range
        if tick_lower >= tick_upper:
            tick_upper = tick_lower + tick_spacing
        
        return (tick_lower, tick_upper)
    
    # =========================================================================
    # PRIVATE UTILITIES
    # =========================================================================
    
    # Token decimals lookup
    TOKEN_DECIMALS = {
        "So11111111111111111111111111111111111111112": 9,   # SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,  # USDT
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": 9,   # mSOL
        "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": 9,  # stSOL
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": 5,  # BONK
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": 6,   # JUP
    }
    
    def _sqrt_price_to_price(
        self, 
        sqrt_price: int, 
        decimals_a: int = 9, 
        decimals_b: int = 6
    ) -> float:
        """
        Convert Whirlpool sqrt_price (Q64.64) to human-readable price.
        
        Formula: price = (sqrt_price / 2^64)^2 × 10^(decimals_a - decimals_b)
        
        Args:
            sqrt_price: Q64.64 fixed-point sqrt of price
            decimals_a: Token A decimals (default: SOL = 9)
            decimals_b: Token B decimals (default: USDC = 6)
            
        Returns:
            Human-readable price (Token B per Token A, e.g., USDC per SOL)
        """
        if sqrt_price == 0:
            return 0.0
        
        # Convert from Q64.64 to float
        # sqrt_price is stored as sqrt(price) * 2^64
        sqrt_price_float = sqrt_price / (2 ** 64)
        
        # Square to get raw price
        raw_price = sqrt_price_float ** 2
        
        # Adjust for token decimals
        # price = raw_price × 10^(decimals_a - decimals_b)
        decimal_adjustment = 10 ** (decimals_a - decimals_b)
        price = raw_price * decimal_adjustment
        
        return price
    
    def _get_token_decimals(self, mint: str) -> int:
        """Get decimals for a token mint address."""
        return self.TOKEN_DECIMALS.get(mint, 6)  # Default to 6 if unknown
    
    def _bytes_to_base58(self, data: bytes) -> str:
        """Convert 32 bytes to base58 string (Solana address format)."""
        try:
            import base58
            return base58.b58encode(data).decode('utf-8')
        except ImportError:
            # Fallback: return hex if base58 not available
            return data.hex()
    
    # =========================================================================
    # TICK ARRAY & POSITION HELPERS (Phase C)
    # =========================================================================
    
    def get_tick_array_start_index(self, tick: int, tick_spacing: int) -> int:
        """
        Calculate the start index of the Tick Array containing a given tick.
        
        Tick Arrays are fixed-size storage units in the Whirlpool program.
        Each array holds TICK_ARRAY_SIZE (88) tick entries.
        
        Args:
            tick: The tick index to find
            tick_spacing: The pool's tick spacing
            
        Returns:
            The starting tick index of the containing array
        """
        TICK_ARRAY_SIZE = 88
        ticks_per_array = TICK_ARRAY_SIZE * tick_spacing
        
        # Floor division to get array start
        array_index = tick // ticks_per_array
        if tick < 0 and tick % ticks_per_array != 0:
            array_index -= 1
        
        return array_index * ticks_per_array
    
    def derive_tick_array_pda(self, pool_address: str, start_tick_index: int) -> str:
        """
        Derive the PDA for a Tick Array.
        
        Seeds: ["tick_array", whirlpool, start_tick_index]
        
        Args:
            pool_address: The Whirlpool address
            start_tick_index: Starting tick of the array
            
        Returns:
            Tick Array PDA address (base58)
        """
        try:
            from solders.pubkey import Pubkey
            
            # Convert start_tick_index to i32 bytes (signed)
            tick_bytes = start_tick_index.to_bytes(4, "little", signed=True)
            
            seeds = [
                b"tick_array",
                bytes(Pubkey.from_string(pool_address)),
                tick_bytes,
            ]
            
            program_id = Pubkey.from_string(WHIRLPOOL_PROGRAM_ID)
            pda, bump = Pubkey.find_program_address(seeds, program_id)
            
            return str(pda)
            
        except Exception as e:
            Logger.error(f"   🐋 [ORCA] Tick Array PDA failed: {e}")
            return ""
    
    def get_tick_array_pdas(
        self, 
        pool_address: str, 
        tick_lower: int, 
        tick_upper: int, 
        tick_spacing: int
    ) -> Tuple[str, str, str]:
        """
        Get all Tick Array PDAs needed for a position.
        
        A position typically needs 3 tick arrays:
        1. Array containing tick_lower
        2. Array containing tick_upper
        3. Array containing current_tick (for swaps)
        
        Args:
            pool_address: Whirlpool address
            tick_lower: Lower bound tick
            tick_upper: Upper bound tick
            tick_spacing: Pool's tick spacing
            
        Returns:
            (lower_array_pda, upper_array_pda, current_array_pda)
        """
        # Get Tick Array start indices
        lower_start = self.get_tick_array_start_index(tick_lower, tick_spacing)
        upper_start = self.get_tick_array_start_index(tick_upper, tick_spacing)
        
        # Derive PDAs
        lower_pda = self.derive_tick_array_pda(pool_address, lower_start)
        upper_pda = self.derive_tick_array_pda(pool_address, upper_start)
        
        # For current tick, we'll use lower as placeholder (should fetch actual current tick)
        current_pda = lower_pda
        
        Logger.debug(f"   🐋 [ORCA] Tick Arrays: lower={lower_start}, upper={upper_start}")
        
        return (lower_pda, upper_pda, current_pda)
    
    def generate_position_mint(self) -> Tuple[str, bytes]:
        """
        Generate a new keypair for a Position NFT mint.
        
        Each CLMM position is an NFT. This creates the mint account keypair.
        
        Returns:
            (public_key_base58, secret_key_bytes)
        """
        try:
            from solders.keypair import Keypair
            
            # Generate new keypair for position mint
            mint_keypair = Keypair()
            
            pubkey = str(mint_keypair.pubkey())
            secret = bytes(mint_keypair)
            
            Logger.info(f"   🐋 [ORCA] Generated position mint: {pubkey[:16]}...")
            
            return (pubkey, secret)
            
        except Exception as e:
            Logger.error(f"   🐋 [ORCA] Keypair generation failed: {e}")
            return ("", b"")
    
    def derive_position_pda(self, position_mint: str) -> str:
        """
        Derive the Position account PDA from the mint.
        
        Seeds: ["position", position_mint]
        
        Args:
            position_mint: The Position NFT mint address
            
        Returns:
            Position account PDA address
        """
        try:
            from solders.pubkey import Pubkey
            
            seeds = [
                b"position",
                bytes(Pubkey.from_string(position_mint)),
            ]
            
            program_id = Pubkey.from_string(WHIRLPOOL_PROGRAM_ID)
            pda, bump = Pubkey.find_program_address(seeds, program_id)
            
            return str(pda)
            
        except Exception as e:
            Logger.error(f"   🐋 [ORCA] Position PDA failed: {e}")
            return ""
    
    # =========================================================================
    # TRANSACTION BUILDERS (Phase B.2)
    # =========================================================================
    
    def build_open_position_ix(
        self,
        pool_address: str,
        tick_lower: int,
        tick_upper: int,
        owner_pubkey: str,
        tick_spacing: int = 64
    ) -> Optional[Dict[str, Any]]:
        """
        Build instruction to open a new CLMM position.
        
        Creates a Position NFT that represents the liquidity range.
        Now includes all required account derivations.
        
        Args:
            pool_address: Target Whirlpool address
            tick_lower: Lower tick bound
            tick_upper: Upper tick bound
            owner_pubkey: Owner's wallet public key
            tick_spacing: Pool's tick spacing (default 64)
            
        Returns:
            Instruction dict with all required accounts, ready for signing
        """
        Logger.info(f"   🐋 [ORCA] Building open_position for {pool_address[:16]}...")
        Logger.info(f"   🐋 [ORCA] Range: tick [{tick_lower}, {tick_upper}]")
        
        # 1. Compute Tick Array PDAs
        tick_array_lower_pda, tick_array_upper_pda, _ = self.get_tick_array_pdas(
            pool_address, tick_lower, tick_upper, tick_spacing
        )
        
        # 2. Generate Position NFT Mint
        position_mint, position_mint_secret = self.generate_position_mint()
        
        # 3. Derive Position account PDA
        position_pda = self.derive_position_pda(position_mint) if position_mint else ""
        
        if not all([tick_array_lower_pda, tick_array_upper_pda, position_mint, position_pda]):
            Logger.error("   🐋 [ORCA] Failed to derive required accounts")
            return None
        
        Logger.success(f"   🐋 [ORCA] Accounts ready for open_position")
        
        return {
            "program_id": WHIRLPOOL_PROGRAM_ID,
            "instruction": "open_position",
            "pool": pool_address,
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "owner": owner_pubkey,
            # Derived accounts
            "position_mint": position_mint,
            "position_mint_secret": position_mint_secret.hex() if position_mint_secret else "",
            "position_pda": position_pda,
            "tick_array_lower": tick_array_lower_pda,
            "tick_array_upper": tick_array_upper_pda,
            # Status
            "status": "READY_FOR_SIGNING",
            "note": "Requires transaction signing with wallet private key",
        }
    
    def build_add_liquidity_ix(
        self,
        position_address: str,
        liquidity_amount: int,
        token_max_a: int,
        token_max_b: int
    ) -> Optional[Dict[str, Any]]:
        """
        Build instruction to add liquidity to an existing position.
        
        Transfers tokens into the pool to start earning fees.
        
        Args:
            position_address: Position NFT address
            liquidity_amount: Liquidity units to add
            token_max_a: Max token A to deposit
            token_max_b: Max token B to deposit
            
        Returns:
            Instruction dict for signing, or None on error
        """
        Logger.info(f"   🐋 [ORCA] Building increase_liquidity for {position_address[:16]}...")
        
        return {
            "program_id": WHIRLPOOL_PROGRAM_ID,
            "instruction": "increase_liquidity",
            "position": position_address,
            "liquidity_amount": liquidity_amount,
            "token_max_a": token_max_a,
            "token_max_b": token_max_b,
            "status": "STUB_NOT_EXECUTABLE",
        }
    
    def build_update_fees_and_rewards_ix(
        self,
        pool_address: str,
        position_address: str,
        tick_lower: int,
        tick_upper: int,
        tick_spacing: int = 64
    ) -> Optional[Dict[str, Any]]:
        """
        Build instruction to update fee and reward counters.
        
        CRITICAL: This MUST be called before collect_fees!
        Without this, the on-chain counters won't be updated and 
        collect_fees will return zero tokens.
        
        Args:
            pool_address: Whirlpool address
            position_address: Position NFT address
            tick_lower: Position's lower tick
            tick_upper: Position's upper tick
            tick_spacing: Pool's tick spacing
            
        Returns:
            Instruction dict for signing
        """
        Logger.info(f"   🐋 [ORCA] Building update_fees_and_rewards for {position_address[:16]}...")
        
        # Get Tick Array PDAs
        tick_arrays = self.get_tick_array_pdas(
            pool_address, tick_lower, tick_upper, tick_spacing
        )
        
        return {
            "program_id": WHIRLPOOL_PROGRAM_ID,
            "instruction": "update_fees_and_rewards",
            "pool": pool_address,
            "position": position_address,
            "tick_array_lower": tick_arrays[0],
            "tick_array_upper": tick_arrays[1],
            "status": "READY_FOR_SIGNING",
            "note": "MUST be called before collect_fees",
        }
    
    def build_collect_fees_ix(
        self,
        position_address: str,
        owner_pubkey: str,
        pool_address: str = "",
        tick_lower: int = 0,
        tick_upper: int = 0,
        tick_spacing: int = 64,
        include_update: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Build instruction to collect accumulated fees.
        
        Harvests fees without closing the position.
        
        IMPORTANT: By default, this includes the update_fees_and_rewards
        instruction which MUST be executed first.
        
        Args:
            position_address: Position NFT address
            owner_pubkey: Owner's wallet public key
            pool_address: Whirlpool address (needed if include_update=True)
            tick_lower: Position's lower tick (needed if include_update=True)
            tick_upper: Position's upper tick (needed if include_update=True)
            tick_spacing: Pool's tick spacing
            include_update: Whether to include update_fees prereq
            
        Returns:
            Instruction dict(s) for signing, or None on error
        """
        Logger.info(f"   🐋 [ORCA] Building collect_fees for {position_address[:16]}...")
        
        result = {
            "program_id": WHIRLPOOL_PROGRAM_ID,
            "instruction": "collect_fees",
            "position": position_address,
            "owner": owner_pubkey,
            "status": "READY_FOR_SIGNING" if include_update and pool_address else "STUB_NOT_EXECUTABLE",
        }
        
        # Include prerequisite instruction
        if include_update and pool_address:
            update_ix = self.build_update_fees_and_rewards_ix(
                pool_address, position_address, tick_lower, tick_upper, tick_spacing
            )
            result["prerequisite"] = update_ix
            result["note"] = "Execute prerequisite.instruction BEFORE this instruction"
        
        return result
    
    def build_close_position_ix(
        self,
        position_address: str,
        owner_pubkey: str
    ) -> Optional[Dict[str, Any]]:
        """
        Build instruction to close position and withdraw all capital.
        
        Steps:
        1. Decrease liquidity to 0
        2. Collect final fees
        3. Close position account (reclaim rent)
        
        Args:
            position_address: Position NFT address
            owner_pubkey: Owner's wallet public key
            
        Returns:
            List of instruction dicts for signing, or None on error
        """
        Logger.info(f"   🐋 [ORCA] Building close_position for {position_address[:16]}...")
        
        return {
            "program_id": WHIRLPOOL_PROGRAM_ID,
            "instruction": "close_position",
            "position": position_address,
            "owner": owner_pubkey,
            "status": "STUB_NOT_EXECUTABLE",
            "note": "Includes: decrease_liquidity + collect_fees + close_account",
        }
    
    # =========================================================================
    # STATUS & DEBUGGING
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get adapter status for monitoring."""
        return {
            "cached_pools": len(self._cache),
            "known_pools": list(KNOWN_POOLS.keys()),
            "rpc_status": "connected" if self.rpc else "disconnected",
        }
    
    def display_pool_info(self, pool_address: str) -> None:
        """Print formatted pool information."""
        state = self.get_whirlpool_state(pool_address)
        
        if not state:
            print(f"❌ Failed to fetch pool: {pool_address}")
            return
        
        print("\n" + "=" * 50)
        print(f"🐋 ORCA WHIRLPOOL: {pool_address[:16]}...")
        print("=" * 50)
        print(f"   Token A: {state.token_mint_a[:16]}...")
        print(f"   Token B: {state.token_mint_b[:16]}...")
        print(f"   Current Price: ${state.price:.6f}")
        print(f"   Current Tick: {state.tick_current}")
        print(f"   Tick Spacing: {state.tick_spacing}")
        print(f"   Fee Rate: {state.fee_rate / 10000:.2f}%")
        print(f"   Liquidity: {state.liquidity:,}")
        print("=" * 50 + "\n")


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_adapter_instance: Optional[OrcaAdapter] = None


def get_orca_adapter() -> OrcaAdapter:
    """Get or create the singleton OrcaAdapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = OrcaAdapter()
    return _adapter_instance


# =============================================================================
# QUICK TEST
# =============================================================================

if __name__ == "__main__":
    print("\n🐋 Orca Adapter Test")
    print("=" * 40)
    
    adapter = get_orca_adapter()
    
    # Test fetching SOL-USDC 1% pool
    pool_address = KNOWN_POOLS["SOL-USDC-1%"]
    print(f"\nFetching pool: {pool_address}")
    
    state = adapter.get_whirlpool_state(pool_address)
    
    if state:
        adapter.display_pool_info(pool_address)
        
        # Test tick calculations
        print("Tick Calculations:")
        print(f"   Current Price: ${state.price:.4f}")
        
        lower, upper = adapter.calculate_range_ticks(state.price, 1.0, state.tick_spacing)
        print(f"   ±1% Range: tick [{lower}, {upper}]")
        print(f"   Price Range: [${adapter.tick_to_price(lower):.4f}, ${adapter.tick_to_price(upper):.4f}]")
    else:
        print("❌ Failed to fetch pool state")
