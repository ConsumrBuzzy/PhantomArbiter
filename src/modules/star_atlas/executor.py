"""
Star Atlas Transaction Executor
================================
Executes marketplace swaps and resource trades on z.ink SVM L1.

Instruction ID: STAR-ATLAS-0O3INWK3 (Marketplace Swap)
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.drivers.wallet_manager import WalletManager
from src.shared.infrastructure.rpc_manager import RpcConnectionManager
from src.shared.infrastructure.star_atlas_client import StarAtlasClient
from src.shared.system.logging import Logger

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction, AccountMeta
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solana.rpc.api import Client
from solana.rpc.types import TxOpts


@dataclass
class SwapResult:
    """Result of a Star Atlas marketplace swap."""
    success: bool
    asset_type: str
    quantity: int
    price_atlas: float
    tx_signature: Optional[str]
    zxp_earned: float  # Estimated zXP from transaction
    error_message: Optional[str]


class StarAtlasExecutor:
    """
    Execute Star Atlas marketplace trades on z.ink chain.

    Features:
    - Marketplace swaps (buy/sell resources)
    - zXP generation tracking
    - 6% fee accounting
    - z.ink RPC integration (99% lower fees than Solana)
    """

    # Star Atlas Program IDs (Verified Feb 2026)
    GALACTIC_MARKETPLACE_PROGRAM = "traderDnaR5w6Tcoi3NFm53i48FTDNbGjBSZwWXDRrg"
    ATLAS_TOKEN_MINT = "ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx"  # Real $ATLAS mint

    def __init__(
        self,
        network: str = "zink",  # "zink" or "solana"
        dry_run: bool = True
    ):
        """
        Initialize Star Atlas executor.

        Args:
            network: "zink" for z.ink L1, "solana" for Solana mainnet
            dry_run: If True, simulates transactions without executing
        """
        self.network = network
        self.dry_run = dry_run

        self.wallet_manager = WalletManager()
        self.wallet_pubkey = self.wallet_manager.keypair.pubkey()

        # Use z.ink RPC if specified
        if network == "zink":
            self.rpc_url = "https://rpc-gel.inkonchain.com"
        else:
            self.rpc_url = "https://api.mainnet-beta.solana.com"

        self.client = Client(self.rpc_url)
        self.sa_client = StarAtlasClient(rpc_url=self.rpc_url)

        # zXP tracking (1 transaction ≈ 1-5 zXP depending on value)
        self.total_zxp_earned = 0.0

        Logger.info(f"[SA-EXEC] Initialized on {network} ({'DRY-RUN' if dry_run else 'LIVE'})")

    def buy_resource(
        self,
        resource_type: str,
        quantity: int,
        max_price_atlas: float,
        starbase_id: Optional[str] = None
    ) -> SwapResult:
        """
        Buy resources from Galactic Marketplace.

        Args:
            resource_type: Resource name (e.g., "Fuel", "SDU")
            quantity: Amount to buy
            max_price_atlas: Maximum price willing to pay per unit
            starbase_id: Optional starbase to buy from

        Returns:
            SwapResult with transaction details
        """
        Logger.info(f"[SA-BUY] Buying {quantity}x {resource_type} (max: {max_price_atlas} ATLAS/unit)")

        try:
            # Get current listings
            listings = self.sa_client.get_resource_listings(
                resource_name=resource_type,
                starbase_id=starbase_id,
                limit=1  # Get cheapest listing
            )

            if not listings:
                return SwapResult(
                    success=False,
                    asset_type=resource_type,
                    quantity=quantity,
                    price_atlas=0.0,
                    tx_signature=None,
                    zxp_earned=0.0,
                    error_message="No listings found"
                )

            cheapest = listings[0]
            unit_price = cheapest.get('pricePerUnit', 999999)

            # Check price
            if unit_price > max_price_atlas:
                Logger.warning(f"   [!] Price too high: {unit_price} ATLAS > {max_price_atlas} ATLAS")
                return SwapResult(
                    success=False,
                    asset_type=resource_type,
                    quantity=quantity,
                    price_atlas=unit_price,
                    tx_signature=None,
                    zxp_earned=0.0,
                    error_message=f"Price exceeds max ({unit_price} > {max_price_atlas})"
                )

            if self.dry_run:
                # Simulate
                total_cost = unit_price * quantity
                zxp = self._estimate_zxp(total_cost)

                Logger.success(f"   [DRY-RUN] Would buy {quantity}x {resource_type} for {unit_price} ATLAS/unit")
                Logger.info(f"      Total Cost: {total_cost} ATLAS")
                Logger.info(f"      Est. zXP: +{zxp:.2f}")

                return SwapResult(
                    success=True,
                    asset_type=resource_type,
                    quantity=quantity,
                    price_atlas=unit_price,
                    tx_signature=None,
                    zxp_earned=zxp,
                    error_message=None
                )

            # LIVE EXECUTION
            # Build marketplace swap instruction
            swap_ix = self._build_marketplace_swap_instruction(
                listing_id=cheapest.get('id'),
                quantity=quantity,
                max_price=unit_price
            )

            # Send transaction
            signature = self._send_transaction([swap_ix])

            if signature:
                total_cost = unit_price * quantity
                zxp = self._estimate_zxp(total_cost)
                self.total_zxp_earned += zxp

                Logger.success(f"   [OK] Purchased {quantity}x {resource_type}!")
                Logger.info(f"      Signature: {signature}")
                Logger.info(f"      zXP Earned: +{zxp:.2f} (Total: {self.total_zxp_earned:.2f})")

                # Log to arbitrage CSV
                self.sa_client.log_arbitrage_opportunity(
                    asset_type=resource_type,
                    buy_starbase=cheapest.get('starbase', {}).get('name', 'Unknown'),
                    sell_starbase="N/A",  # Will be filled on sell
                    profit_data={
                        'buy_price': unit_price,
                        'sell_price': 0,  # TBD
                        'quantity': quantity,
                        'gross_profit': 0,
                        'marketplace_fee': 0,
                        'net_profit': 0,
                        'spread_percent': 0,
                        'is_profitable': False
                    }
                )

                return SwapResult(
                    success=True,
                    asset_type=resource_type,
                    quantity=quantity,
                    price_atlas=unit_price,
                    tx_signature=str(signature),
                    zxp_earned=zxp,
                    error_message=None
                )
            else:
                return SwapResult(
                    success=False,
                    asset_type=resource_type,
                    quantity=quantity,
                    price_atlas=unit_price,
                    tx_signature=None,
                    zxp_earned=0.0,
                    error_message="Transaction failed"
                )

        except Exception as e:
            Logger.error(f"   [X] Buy failed: {e}")
            return SwapResult(
                success=False,
                asset_type=resource_type,
                quantity=quantity,
                price_atlas=0.0,
                tx_signature=None,
                zxp_earned=0.0,
                error_message=str(e)
            )

    def sell_resource(
        self,
        resource_type: str,
        quantity: int,
        min_price_atlas: float,
        starbase_id: Optional[str] = None
    ) -> SwapResult:
        """
        Sell resources on Galactic Marketplace.

        Args:
            resource_type: Resource name
            quantity: Amount to sell
            min_price_atlas: Minimum price per unit
            starbase_id: Optional starbase to sell at

        Returns:
            SwapResult with transaction details
        """
        Logger.info(f"[SA-SELL] Selling {quantity}x {resource_type} (min: {min_price_atlas} ATLAS/unit)")

        # Calculate expected proceeds after 6% fee
        gross_proceeds = min_price_atlas * quantity
        marketplace_fee = gross_proceeds * 0.06
        net_proceeds = gross_proceeds - marketplace_fee

        if self.dry_run:
            zxp = self._estimate_zxp(gross_proceeds)

            Logger.success(f"   [DRY-RUN] Would sell {quantity}x {resource_type} for {min_price_atlas} ATLAS/unit")
            Logger.info(f"      Gross Proceeds: {gross_proceeds} ATLAS")
            Logger.info(f"      Marketplace Fee (6%): -{marketplace_fee} ATLAS")
            Logger.info(f"      Net Proceeds: {net_proceeds} ATLAS")
            Logger.info(f"      Est. zXP: +{zxp:.2f}")

            return SwapResult(
                success=True,
                asset_type=resource_type,
                quantity=quantity,
                price_atlas=min_price_atlas,
                tx_signature=None,
                zxp_earned=zxp,
                error_message=None
            )

        # TODO: Implement live sell execution
        Logger.warning("   [!] Live sell not yet implemented")

        return SwapResult(
            success=False,
            asset_type=resource_type,
            quantity=quantity,
            price_atlas=min_price_atlas,
            tx_signature=None,
            zxp_earned=0.0,
            error_message="Live sell not yet implemented"
        )

    def _build_marketplace_swap_instruction(
        self,
        listing_id: str,
        quantity: int,
        max_price: float
    ) -> Instruction:
        """
        Build Star Atlas marketplace swap instruction.

        Args:
            listing_id: Marketplace listing ID
            quantity: Amount to purchase
            max_price: Maximum price per unit

        Returns:
            Solana instruction for marketplace swap

        NOTE: This is a placeholder - needs actual Star Atlas program structure.
        """
        # Program address (placeholder - needs verification)
        program_id = Pubkey.from_string(self.GALACTIC_MARKETPLACE_PROGRAM)

        # Build instruction data (placeholder - needs actual encoding)
        # Real implementation would encode listing_id, quantity, max_price
        instruction_data = bytes([])  # TODO: Proper encoding

        # Accounts (placeholder - needs actual account structure)
        accounts = [
            AccountMeta(pubkey=self.wallet_pubkey, is_signer=True, is_writable=True),
            # TODO: Add marketplace accounts, listing account, etc.
        ]

        return Instruction(
            program_id=program_id,
            accounts=accounts,
            data=instruction_data
        )

    def _send_transaction(self, instructions: list[Instruction]) -> Optional[str]:
        """
        Send transaction to z.ink or Solana.

        Args:
            instructions: List of instructions to execute

        Returns:
            Transaction signature or None if failed
        """
        try:
            # Add compute budget for priority
            compute_budget_ixs = [
                set_compute_unit_limit(200_000),
                set_compute_unit_price(10_000)  # z.ink fees are 99% lower!
            ]

            all_instructions = compute_budget_ixs + instructions

            # Get recent blockhash
            latest_blockhash = self.client.get_latest_blockhash().value.blockhash

            # Compile message
            msg = MessageV0.try_compile(
                payer=self.wallet_pubkey,
                instructions=all_instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=latest_blockhash,
            )

            # Create and sign transaction
            tx = VersionedTransaction(msg, [self.wallet_manager.keypair])

            # Send
            response = self.client.send_transaction(
                tx,
                opts=TxOpts(skip_preflight=False, preflight_commitment="confirmed")
            )

            return response.value

        except Exception as e:
            Logger.error(f"   [X] Transaction failed: {e}")
            return None

    def _estimate_zxp(self, transaction_value_atlas: float) -> float:
        """
        Estimate zXP earned from transaction.

        zXP Formula (estimated):
        - Base: 1 zXP per transaction
        - Bonus: +0.01 zXP per 100 ATLAS value

        Args:
            transaction_value_atlas: Transaction value in $ATLAS

        Returns:
            Estimated zXP earned
        """
        base_zxp = 1.0
        value_bonus = (transaction_value_atlas / 100) * 0.01
        return base_zxp + value_bonus

    def get_zxp_summary(self) -> Dict[str, Any]:
        """
        Get zXP earning summary.

        Returns:
            {
                'total_zxp': float,
                'transactions': int,
                'network': str
            }
        """
        return {
            'total_zxp': self.total_zxp_earned,
            'network': self.network,
            'wallet': str(self.wallet_pubkey)
        }
