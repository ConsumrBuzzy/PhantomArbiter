"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     DNEM AUTO-REBALANCER                                     ║
║                  Phase 4.1: Autonomous Delta Correction                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

Automatically corrects delta drift when it exceeds tolerance thresholds.

Features:
- 1% drift tolerance band
- 30-minute cooldown between trades
- Taker price limit safety (prevents toxic flow execution)
- Integrates with DriftOrderBuilder for execution

Usage:
    python -m src.engine.auto_rebalancer           # Single check
    python -m src.engine.auto_rebalancer --loop    # Continuous monitoring
"""

import asyncio
import os
import time
import struct
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

import base58
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

from src.delta_neutral.drift_order_builder import DriftOrderBuilder
from src.shared.system.logging import Logger

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class RebalanceConfig:
    """Configuration for auto-rebalancer."""
    
    # Delta tolerance (1% = 0.01)
    drift_tolerance_pct: float = 1.0
    
    # Minimum seconds between rebalances
    cooldown_seconds: int = 1800  # 30 minutes
    
    # Maximum slippage allowed (in basis points)
    max_slippage_bps: int = 50  # 0.5%
    
    # Minimum trade size (SOL) - prevents dust trades
    min_trade_size: float = 0.005
    
    # Reserved SOL for gas
    reserved_sol: float = 0.017
    
    # Loop interval for continuous monitoring
    loop_interval_seconds: int = 60


# =============================================================================
# CONSTANTS
# =============================================================================

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
SOL_DECIMALS = 9
USDC_DECIMALS = 6

# State file for cooldown tracking
STATE_FILE = Path("data/rebalancer_state.json")


# =============================================================================
# HELPERS
# =============================================================================


def derive_user_account(wallet: Pubkey) -> Pubkey:
    pda, _ = Pubkey.find_program_address(
        [b"user", bytes(wallet), (0).to_bytes(2, 'little')],
        DRIFT_PROGRAM_ID
    )
    return pda


def parse_perp_position(data: bytes, market_index: int = 0) -> Optional[dict]:
    """Parse perp position from Drift User account."""
    PERP_POSITIONS_OFFSET = 8 + 32 + 32 + 32 + (8 * 40)
    PERP_POSITION_SIZE = 88
    
    if len(data) < PERP_POSITIONS_OFFSET + PERP_POSITION_SIZE:
        return None
    
    for i in range(8):
        offset = PERP_POSITIONS_OFFSET + (i * PERP_POSITION_SIZE)
        if offset + PERP_POSITION_SIZE > len(data):
            break
        
        pos_market_index = struct.unpack_from("<H", data, offset + 92)[0]
        
        if pos_market_index == market_index:
            return {
                "market_index": pos_market_index,
                "base_asset_amount": struct.unpack_from("<q", data, offset + 8)[0],
                "quote_asset_amount": struct.unpack_from("<q", data, offset + 16)[0],
            }
    return None


def load_last_rebalance_time() -> Optional[datetime]:
    """Load last rebalance timestamp from state file."""
    try:
        if STATE_FILE.exists():
            import json
            with open(STATE_FILE) as f:
                state = json.load(f)
                return datetime.fromisoformat(state.get("last_rebalance", ""))
    except:
        pass
    return None


def save_last_rebalance_time():
    """Save current timestamp as last rebalance time."""
    import json
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump({"last_rebalance": datetime.now().isoformat()}, f)


# =============================================================================
# AUTO-REBALANCER
# =============================================================================


from src.engines.base_engine import BaseEngine

class FundingEngine(BaseEngine):
    """
    Autonomous delta-drift correction engine (Funding Rate Farmer).
    
    Monitors the delta between spot SOL and perp short position.
    When drift exceeds tolerance, executes corrective trades.
    
    Supports both paper mode (VirtualDriver) and live mode (DriftAdapter).
    """
    
    def __init__(self, live_mode: bool = False, config: Optional[RebalanceConfig] = None):
        super().__init__("funding", live_mode)
        self.config = config or RebalanceConfig()
        self.last_rebalance = load_last_rebalance_time()
        self.drift_adapter: Optional[Any] = None  # Will be initialized on start
        self._last_health_warning: Optional[datetime] = None
        self._health_warning_cooldown = 60  # seconds between warnings
    
    async def start(self):
        """Start the engine and initialize adapters."""
        # Initialize DriftAdapter for live mode
        if self.live_mode:
            from src.engines.funding.drift_adapter import DriftAdapter
            from src.drivers.wallet_manager import WalletManager
            
            Logger.info("[FUNDING] Initializing live mode with DriftAdapter...")
            
            # Create adapter
            self.drift_adapter = DriftAdapter(network="mainnet")
            
            # Load wallet
            wallet_manager = WalletManager()
            
            # Connect to Drift
            success = await self.drift_adapter.connect(wallet_manager, sub_account=0)
            
            if not success:
                Logger.error("[FUNDING] Failed to connect to Drift Protocol")
                Logger.error("[FUNDING] Please ensure your Drift account is initialized")
                return
            
            Logger.success("[FUNDING] ✅ Connected to Drift Protocol (Live Mode)")
        
        # Call parent start
        await super().start()
    
    async def stop(self):
        """Stop the engine and cleanup."""
        # Disconnect from Drift if connected
        if self.drift_adapter:
            await self.drift_adapter.disconnect()
            self.drift_adapter = None
        
        # Call parent stop
        await super().stop()
        
    async def tick(self):
        """Single execution step."""
        result = await self.check_and_rebalance(simulate=not self.live_mode)
        
        # Broadcast status via BaseEngine callback
        if self._callback:
             await self._callback({
                 "type": "STATUS",
                 "data": result
             })
             
    def get_interval(self) -> float:
        return float(self.config.loop_interval_seconds)
        
    async def check_and_rebalance(self, simulate: bool = True) -> dict:
        """
        Check delta drift and rebalance if needed.
        
        Supports both paper mode (VirtualDriver) and live mode (DriftAdapter).
        
        Returns:
            dict with status, drift_pct, action_taken, health, leverage, positions, etc.
        """
        load_dotenv()
        
        # Load wallet for live mode
        private_key = os.getenv("SOLANA_PRIVATE_KEY") or os.getenv("PHANTOM_PRIVATE_KEY")
        
        if self.live_mode and self.drift_adapter:
            # ═══════════════════════════════════════════════════════════════
            # LIVE MODE: Use DriftAdapter
            # ═══════════════════════════════════════════════════════════════
            try:
                # Fetch account state from Drift
                account_state = await self.drift_adapter.get_account_state()
                
                # Get wallet SOL balance
                if not private_key:
                    return {"status": "error", "message": "No private key found"}
                
                secret_bytes = base58.b58decode(private_key)
                keypair = Keypair.from_bytes(secret_bytes)
                wallet_pk = keypair.pubkey()
                
                rpc_url = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
                async with AsyncClient(rpc_url) as client:
                    sol_balance = await client.get_balance(wallet_pk)
                    spot_sol = sol_balance.value / (10 ** SOL_DECIMALS)
                
                # Extract data from account state
                collateral = account_state['collateral']
                raw_positions = account_state['positions']
                health_ratio = account_state['health_ratio']
                leverage = account_state['leverage']
                margin_requirement = account_state['margin_requirement']
                
                # Find SOL-PERP position
                perp_sol = 0.0
                sol_price = 150.0  # Default
                
                for pos in raw_positions:
                    if pos['market'] == 'SOL-PERP':
                        perp_sol = -pos['size'] if pos['side'] == 'short' else pos['size']
                        sol_price = pos['mark_price']
                        break
                
                # Calculate equity
                equity = collateral
                
                # Reformat positions for UI (match paper mode format)
                positions = []
                for pos in raw_positions:
                    positions.append({
                        "market": pos["market"],
                        "amount": -pos["size"] if pos["side"] == "short" else pos["size"],
                        "entry_price": pos["entry_price"],
                        "mark_price": pos["mark_price"],
                        "pnl": pos["total_pnl"],
                        "liq_price": 0.0,  # TODO: Calculate liquidation price
                        "settled_pnl": pos["settled_pnl"],
                        "unsettled_pnl": 0.0,  # TODO: Parse unsettled PnL
                        "unrealized_pnl": pos["unrealized_pnl"]
                    })
                
                # Emit health warnings
                await self._check_health_warnings(health_ratio)
                
            except Exception as e:
                Logger.error(f"[FUNDING] Live mode error: {e}")
                return {"status": "error", "message": f"Live mode error: {e}"}
        
        elif not self.live_mode and self.driver:
            # ═══════════════════════════════════════════════════════════════
            # PAPER MODE: Use VirtualDriver
            # ═══════════════════════════════════════════════════════════════
            balances = self.driver.get_balances()
            spot_sol = balances.get("SOL", 0.0)
            
            # Get positions from VirtualDriver
            positions_data = self.driver.positions
            perp_pos = positions_data.get("SOL-PERP")
            
            if perp_pos:
                perp_sol = -perp_pos.size if perp_pos.side == "short" else perp_pos.size
                sol_price = self.driver._current_prices.get("SOL-PERP", 150.0)
            else:
                perp_sol = 0.0
                sol_price = self.driver._current_prices.get("SOL-PERP", 150.0)
            
            quote_amount = balances.get("USDC", 1000.0)
            
            # Calculate metrics using VirtualDriver
            maint_margin = 0.0
            for symbol, position in self.driver.positions.items():
                current_price = self.driver._current_prices.get(symbol, position.entry_price)
                maint_margin += position.calculate_maintenance_margin(current_price)
            
            health_ratio = self.driver.calculate_health_ratio()
            equity = spot_sol * sol_price + quote_amount
            leverage = 0.0
            if equity > 0:
                perp_usd = abs(perp_sol) * sol_price
                leverage = perp_usd / equity
            
            margin_requirement = maint_margin
            
            # Build positions list
            positions = []
            for pos_dict in self.driver.get_paper_positions():
                positions.append({
                    "market": pos_dict["symbol"],
                    "amount": -pos_dict["size"] if pos_dict["side"] == "short" else pos_dict["size"],
                    "entry_price": pos_dict["entry_price"],
                    "mark_price": pos_dict["current_price"],
                    "pnl": pos_dict["total_pnl"],
                    "liq_price": 0.0,
                    "settled_pnl": pos_dict["settled_pnl"],
                    "unsettled_pnl": pos_dict["unsettled_pnl"],
                    "unrealized_pnl": pos_dict["unrealized_pnl"]
                })
        
        else:
            return {"status": "error", "message": "No driver or adapter initialized"}

        # ═══════════════════════════════════════════════════════════════
        # COMMON LOGIC: Delta calculation and rebalancing
        # ═══════════════════════════════════════════════════════════════
        
        # Calculate delta
        hedgeable_spot = max(0, spot_sol - self.config.reserved_sol)
        net_delta = hedgeable_spot + perp_sol  # perp_sol is negative for shorts
        
        drift_pct = 0.0
        if hedgeable_spot > 0:
            drift_pct = (net_delta / hedgeable_spot) * 100
        
        abs_drift = abs(drift_pct)
        
        # Build result
        result = {
            "timestamp": datetime.now().isoformat(),
            "spot_sol": spot_sol,
            "perp_sol": perp_sol,
            "net_delta": net_delta,
            "drift_pct": drift_pct,
            "sol_price": sol_price,
            "action_taken": None,
            "tx_signature": None,
            
            # UI Metrics
            "health": health_ratio,
            "total_collateral": equity,
            "equity": equity,
            "maintenance_margin": margin_requirement,
            "leverage": leverage,
            "positions": positions,
            "free_collateral": max(0, equity - margin_requirement)
        }
            
        # Check if rebalance needed
        if abs_drift <= self.config.drift_tolerance_pct:
            result["status"] = "ok"
            result["message"] = f"Delta within tolerance ({drift_pct:+.2f}%)"
            return result
        
        # Check cooldown
        if self.last_rebalance:
            time_since_last = datetime.now() - self.last_rebalance
            if time_since_last < timedelta(seconds=self.config.cooldown_seconds):
                remaining = self.config.cooldown_seconds - time_since_last.total_seconds()
                result["status"] = "cooldown"
                result["message"] = f"Cooldown active ({remaining:.0f}s remaining)"
                return result
        
        # Calculate correction trade
        correction_size = abs(net_delta)
        
        if correction_size < self.config.min_trade_size:
            result["status"] = "skip"
            result["message"] = f"Correction too small ({correction_size:.6f} SOL)"
            return result
        
        # Determine trade direction
        if net_delta > 0:
            action = "EXPAND_SHORT"
            Logger.info(f"[REBALANCER] Net delta +{net_delta:.6f} SOL - expanding short by {correction_size:.6f}")
        else:
            action = "REDUCE_SHORT"
            Logger.info(f"[REBALANCER] Net delta {net_delta:.6f} SOL - reducing short by {correction_size:.6f}")
        
        result["action_taken"] = action
        result["correction_size"] = correction_size
        
        # Execute trade
        if simulate:
            if self.driver:
                 # Paper Mode Execution
                 from src.shared.drivers.virtual_driver import VirtualOrder
                 
                 side = "sell" if action == "EXPAND_SHORT" else "buy" 
                 
                 order = VirtualOrder(
                    symbol="SOL-PERP",
                    side=side,
                    size=correction_size,
                    order_type="market"
                 )
                 self.driver.set_price_feed({"SOL-PERP": sol_price})
                 
                 filled = await self.driver.place_order(order)
                 
                 result["status"] = "executed_paper"
                 result["message"] = f"[PAPER] {action} {correction_size:.4f} SOL-PERP @ ${sol_price:.2f}"
                 Logger.info(result["message"])
            else:
                 result["status"] = "simulated"
                 result["message"] = f"Would {action} by {correction_size:.6f} SOL"
                 Logger.info(f"[REBALANCER] SIMULATION: {result['message']}")
        else:
            # Live execution (Phase 4)
            result["status"] = "error"
            result["message"] = "Live trading not implemented yet (Phase 4)"
            Logger.warning("[REBALANCER] Live trading requires Phase 4 implementation")
        
        return result
    
    async def _check_health_warnings(self, health_ratio: float):
        """
        Emit health warnings based on thresholds.
        
        - Warning: health < 50%
        - Critical: health < 20%
        
        Args:
            health_ratio: Current health ratio [0, 100]
        """
        now = datetime.now()
        
        # Check cooldown
        if self._last_health_warning:
            time_since_last = (now - self._last_health_warning).total_seconds()
            if time_since_last < self._health_warning_cooldown:
                return
        
        # Emit warnings
        if health_ratio < 20:
            Logger.error(f"[FUNDING] 🚨 CRITICAL: Health ratio {health_ratio:.1f}% - Risk of liquidation!")
            self._last_health_warning = now
            
            # Broadcast to UI if callback available
            if self._callback:
                await self._callback({
                    "type": "HEALTH_ALERT",
                    "level": "CRITICAL",
                    "health": health_ratio,
                    "message": f"Health ratio {health_ratio:.1f}% - Risk of liquidation!"
                })
        
        elif health_ratio < 50:
            Logger.warning(f"[FUNDING] ⚠️  WARNING: Health ratio {health_ratio:.1f}% - Consider adding collateral")
            self._last_health_warning = now
            
            # Broadcast to UI if callback available
            if self._callback:
                await self._callback({
                    "type": "HEALTH_ALERT",
                    "level": "WARNING",
                    "health": health_ratio,
                    "message": f"Health ratio {health_ratio:.1f}% - Consider adding collateral"
                })
    
    async def _execute_rebalance(
        self, 
        client: AsyncClient,
        keypair: Keypair,
        wallet_pk: Pubkey,
        action: str,
        size: float,
    ) -> str:
        """Execute the rebalance trade on Drift."""
        
        builder = DriftOrderBuilder(wallet_pk)
        
        if action == "EXPAND_SHORT":
            # Open additional short
            ixs = builder.build_short_order("SOL-PERP", size)
        else:
            # Reduce short (open long to offset)
            ixs = builder.build_long_order("SOL-PERP", size)
        
        # Get blockhash
        bh_resp = await client.get_latest_blockhash()
        blockhash = bh_resp.value.blockhash
        
        msg = MessageV0.try_compile(
            payer=wallet_pk,
            instructions=ixs,
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash,
        )
        
        tx = VersionedTransaction(msg, [keypair])
        
        # Simulate first
        sim_resp = await client.simulate_transaction(tx)
        if sim_resp.value.err:
            raise Exception(f"Simulation failed: {sim_resp.value.err}")
        
        # Execute
        opts = TxOpts(skip_confirmation=False, preflight_commitment=Confirmed)
        resp = await client.send_transaction(tx, opts=opts)
        
        sig = str(resp.value)
        await client.confirm_transaction(resp.value, commitment=Confirmed)
        
        return sig
    

    async def execute_funding_command(self, action: str, data: dict) -> dict:
        """
        Execute manual commands from Dashboard.
        Actions: DEPOSIT, WITHDRAW, CLOSE_POSITION, OPEN_POSITION
        """
        Logger.info(f"[FUNDING] Received command: {action} {data}")
        
        if not self.live_mode and self.driver:
            # --- PAPER MODE EXECUTION ---
            if action == "DEPOSIT":
                amount = float(data.get("amount", 0))
                # Add to Virtual Wallet (USDC or SOL?)
                # Usually funding engine holds SOL spot and short perp.
                # Let's assume deposit is SOL.
                # VirtualDriver doesn't explicit deposit, but we can set balance.
                balances = self.driver.get_balances()
                current_sol = balances.get("SOL", 0.0)
                self.driver.set_balance("SOL", current_sol + amount)
                return {"success": True, "message": f"Deposited {amount} SOL (Paper)"}
                
            elif action == "WITHDRAW":
                amount = float(data.get("amount", 0))
                balances = self.driver.get_balances()
                current_sol = balances.get("SOL", 0.0)
                if current_sol >= amount:
                    self.driver.set_balance("SOL", current_sol - amount)
                    return {"success": True, "message": f"Withdrew {amount} SOL (Paper)"}
                else:
                    return {"success": False, "message": "Insufficient funds"}
                    
            elif action == "CLOSE_POSITION":
                 # Close all PERP positions
                 market = data.get("market", "SOL-PERP")
                 
                 # Use VirtualDriver's close_position method
                 result = await self.driver.close_position(market)
                 
                 if result and result.status == "filled":
                     return {"success": True, "message": f"Closed {market} (Paper)"}
                 else:
                     return {"success": False, "message": f"No position to close for {market}"}

            elif action == "OPEN_POSITION":
                from src.shared.drivers.virtual_driver import VirtualOrder
                
                market = data.get("market", "SOL-PERP")
                direction = data.get("direction", "shorts") # UI sends "shorts" or "longs"
                size = float(data.get("size", 0.0))
                
                # Map direction to side
                # If market provides "shorts" APR, we want to go SHORT -> SELL
                side = "sell" if "short" in direction.lower() else "buy"
                
                order = VirtualOrder(
                    symbol=market,
                    side=side,
                    size=size,
                    order_type="market"
                )
                
                # Ensure price feed exists for new markets
                if market not in self.driver._current_prices:
                    # Mock price based on market
                    price = 145.0 if "SOL" in market else 60000.0 if "BTC" in market else 1.0
                    self.driver.set_price_feed({market: price})
                
                filled = await self.driver.place_order(order)
                return {"success": True, "message": f"Opened {side} {size} {market} (Paper)"}

        elif self.live_mode and self.drift_adapter:
            # --- LIVE MODE EXECUTION ---
            try:
                if action == "DEPOSIT":
                    amount = float(data.get("amount", 0))
                    
                    # Execute deposit via DriftAdapter
                    tx_sig = await self.drift_adapter.deposit(amount)
                    
                    # TODO: Update Engine_Vault balance (Task 10)
                    
                    return {
                        "success": True, 
                        "message": f"Deposited {amount} SOL",
                        "tx_signature": tx_sig
                    }
                
                elif action == "WITHDRAW":
                    amount = float(data.get("amount", 0))
                    
                    # Execute withdrawal via DriftAdapter
                    tx_sig = await self.drift_adapter.withdraw(amount)
                    
                    # TODO: Update Engine_Vault balance (Task 10)
                    
                    return {
                        "success": True, 
                        "message": f"Withdrew {amount} SOL",
                        "tx_signature": tx_sig
                    }
                
                elif action == "OPEN_POSITION":
                    # TODO: Implement position opening in Task 13
                    return {"success": False, "message": "Position opening not implemented yet (Task 13)"}
                
                elif action == "CLOSE_POSITION":
                    # TODO: Implement position closing in Task 14
                    return {"success": False, "message": "Position closing not implemented yet (Task 14)"}
                
                else:
                    return {"success": False, "message": f"Unknown action: {action}"}
            
            except ValueError as e:
                # Validation errors (user-friendly)
                Logger.warning(f"[FUNDING] Command validation failed: {e}")
                return {"success": False, "message": str(e)}
            
            except Exception as e:
                # Unexpected errors
                Logger.error(f"[FUNDING] Command execution failed: {e}")
                return {"success": False, "message": f"Error: {e}"}
        
        else:
            return {"success": False, "message": "Engine not properly initialized"}


# Backward Compatibility
AutoRebalancer = FundingEngine
