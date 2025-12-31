"""
V5.8: Portfolio Manager
SRP: Manages Capital Pool, Cash Availability, and Global Risk State.
"""

from config.settings import Settings


class PortfolioManager:
    """Manages the shared capital pool and global risk state."""

    def __init__(self, wallet_manager, initial_capital=None):
        self.wallet = wallet_manager

        # V12.8: Live/Mocked Wallet Support
        # If initial_capital is provided (Monitor Mode), use it as fixed virtual pool.
        self.virtual_mode = initial_capital is not None

        if self.virtual_mode:
            self.cash_available = initial_capital
            print(
                f"   💼 Portfolio Initialized with VIRTUAL CAPITAL: ${self.cash_available:.2f}"
            )
        else:
            # Standard Real-Money Initialization
            # V10.11: Use Broker Cache for initial cash (Avoid Startup RPC)
            from src.core.shared_cache import SharedPriceCache, is_broker_alive

            self.cash_available = 0.0

            if is_broker_alive():
                wallet_state = SharedPriceCache.get_wallet_state(max_age=60)
                if wallet_state:
                    self.cash_available = wallet_state.get("usdc", 0)

            # Fallback only if cache missed
            if self.cash_available == 0.0:
                # Fetch actual USDC balance from wallet instead of hardcoded pool
                try:
                    self.cash_available = self.wallet.get_balance(Settings.USDC_MINT)
                except Exception:
                    self.cash_available = 0.0  # Fail safe

        self.global_locked = False
        self.global_hibernation = None
        self.held_assets = {}  # {symbol: balance}
        self.blocked_assets = (
            self._load_blocked_tokens()
        )  # V5.7 Blocked tokens (Persisted)

    def _load_blocked_tokens(self):
        """Load permanently blocked tokens from disk."""
        import os
        import json

        blocked_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../config/blocked_tokens.json")
        )
        if os.path.exists(blocked_file):
            try:
                with open(blocked_file, "r") as f:
                    return set(json.load(f))
            except Exception:
                return set()  # Failed to load blocked tokens
        return set()

    def block_token(self, symbol):
        """Block a token and persist it."""
        self.blocked_assets.add(symbol)
        import os
        import json

        blocked_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../config/blocked_tokens.json")
        )
        try:
            with open(blocked_file, "w") as f:
                json.dump(list(self.blocked_assets), f)
        except Exception as e:
            print(f"⚠️ Failed to save blocked tokens: {e}")

    def _fetch_token_symbol(self, mint):
        """Fetch symbol from DexScreener for untracked tokens."""
        # Check known system mints first
        if mint == Settings.USDC_MINT:
            return "USDC"
        if mint == "So11111111111111111111111111111111111111112":
            return "SOL"

        try:
            import requests
            import time

            time.sleep(0.1)  # Brief pause
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    sym = pairs[0].get("baseToken", {}).get("symbol", "")
                    if sym:
                        return sym
        except Exception:
            pass  # DexScreener lookup failed
        return "UNKNOWN"

    def scan_wallet(self):
        """
        Perform comprehensive wallet scan.
        V7.1.2: Reads from broker cache when available.
        """
        if self.virtual_mode:
            # V12.8: In Virtual Mode, do not scan real wallet updates
            return self.held_assets

        print("   🔍 SCANNING WALLET FOR POSITIONS...")

        # V7.1.2: Check broker cache first
        from src.core.shared_cache import SharedPriceCache, is_broker_alive

        if is_broker_alive():
            wallet_state = SharedPriceCache.get_wallet_state(max_age=120)
            if wallet_state and wallet_state.get("held_assets"):
                print("   📡 Using broker cached wallet state")
                self.held_assets = {}
                for symbol, data in wallet_state["held_assets"].items():
                    self.held_assets[symbol] = data.get("balance", 0)
                    category = self._get_category(symbol)
                    print(
                        f"      ✅ {symbol} ({category}): {data.get('balance', 0):.4f} tokens"
                    )

                self.cash_available = wallet_state.get("usdc", 0)
                return self.held_assets

        # Fallback: Direct RPC scan
        all_tokens = self.wallet.get_all_token_accounts()

        self.held_assets = {}

        mint_to_symbol = {v: k for k, v in Settings.ASSETS.items()}

        if not all_tokens:
            print("   📭 No live positions detected")
            return self.held_assets

        for mint, balance in all_tokens.items():
            if balance > 0.01:
                symbol = mint_to_symbol.get(mint, "UNTRACKED")

                if symbol != "UNTRACKED":
                    self.held_assets[symbol] = balance
                    category = self._get_category(symbol)
                    print(f"      ✅ {symbol} ({category}): {balance:.4f} tokens")
                else:
                    fetched_sym = self._fetch_token_symbol(mint)
                    print(
                        f"      ⚠️ UNTRACKED: {fetched_sym} ({mint[:8]}...): {balance:.4f}"
                    )

        if not self.held_assets:
            print("   📭 No live positions detected")

        return self.held_assets

    def _get_category(self, symbol: str) -> str:
        """Get category string for a symbol."""
        if symbol in Settings.ACTIVE_ASSETS:
            return "🟢 ACTIVE"
        if symbol in Settings.VOLATILE_ASSETS:
            return "🟡 VOLATILE"
        if symbol in Settings.WATCH_ASSETS:
            return "⚪ WATCH"
        if symbol in Settings.SCOUT_ASSETS:
            return "🔭 SCOUT"
        return "❓ UNKNOWN"

    def reconcile_position_files(self, held_assets: dict):
        """
        Phase 2: Sync position files with actual wallet holdings.
        Deletes orphan files for tokens no longer held.
        """
        if self.virtual_mode:
            return 0

        import os
        import glob

        strategy_dir = os.path.dirname(__file__)
        position_files = glob.glob(os.path.join(strategy_dir, "position_*.json"))

        orphans_removed = 0

        for filepath in position_files:
            filename = os.path.basename(filepath)
            # Extract symbol from filename (position_JUP.json -> JUP)
            symbol = filename.replace("position_", "").replace(".json", "")

            # Check if we actually hold this token
            if symbol not in held_assets:
                try:
                    os.remove(filepath)
                    print(f"   🗑️ Removed orphan position: {symbol}")
                    orphans_removed += 1
                except Exception as e:
                    print(f"   ⚠️ Failed to remove {symbol}: {e}")

        if orphans_removed > 0:
            print(f"   ✅ Cleaned up {orphans_removed} orphan position file(s)")

        return orphans_removed

    def reconcile(self, watchers):
        """
        Reconcile cash against actual positions held.
        V5.8: Explicitly tracks Liquid USDC vs Allocated Capital.
        """
        if self.virtual_mode:
            # V12.8: Minimal reconcile for Virtual Mode
            # We don't check watchers against real wallet.
            return

        print("   🔄 Reconciling portfolio...")
        locked_capital = 0.0

        # 1. Fetch Real USDC Balance (Liquid Cash)
        usdc_balance = self.wallet.get_balance(Settings.USDC_MINT)

        # 2. Calculate Allocated Value (Positions)
        allocated_value = 0.0

        for symbol, watcher in watchers.items():
            # Check if we hold this asset
            balance = 0.0

            # Use pre-scanned data first
            if symbol in self.held_assets and self.held_assets[symbol] > 0.01:
                balance = self.held_assets[symbol]
                # Update watcher logic
                watcher.in_position = True
                watcher.token_balance = balance  # V10.2: Inject balance
            else:
                watcher.token_balance = 0.0

            if balance > 0:
                # Calculate value (Cost basis if known, else current value)
                # V9.5: Pass balance to enable legacy entry price fix
                if watcher.load_persisted_entry(token_balance=balance):
                    cost_basis = watcher.entry_price * balance
                    locked_capital += cost_basis

                    # Current value for display
                    curr_price = watcher.get_price()
                    allocated_value += (
                        (balance * curr_price) if curr_price > 0 else cost_basis
                    )
                else:
                    # Estimate
                    price = watcher.get_price()
                    if price > 0:
                        val = price * balance
                        locked_capital += val
                        allocated_value += val
                        watcher.entry_price = price  # Auto-fix entry
            else:
                watcher.in_position = False

        # Update free cash state (Use real wallet balance if available, fallback to calc)
        if usdc_balance > 0 or locked_capital > 0:
            self.cash_available = usdc_balance
        else:
            # Fallback logic if RPC fails or wallet empty but supposed to have funds?
            self.cash_available = max(0.0, Settings.POOL_CAPITAL - locked_capital)

        # Total Portfolio Value
        total_portfolio_value = self.cash_available + allocated_value

        # Display V5.8 Metrics
        print("=" * 60)
        print(f"💰 TOTAL PORTFOLIO VALUE: ${total_portfolio_value:.2f}")
        print(f"💵 LIQUID USDC (CASH):    ${self.cash_available:.2f}")
        print(f"💼 ALLOCATED CAPITAL:     ${allocated_value:.2f}")
        print("=" * 60)

    def update_cash(self, watchers):
        """Fast update of available cash based on actual wallet balance (Runtime)."""
        if self.virtual_mode:
            return

        # V10.9: Use Broker Cache to avoid RPC spam
        from src.core.shared_cache import SharedPriceCache, is_broker_alive

        if is_broker_alive():
            wallet_state = SharedPriceCache.get_wallet_state(max_age=30)
            if wallet_state:
                self.cash_available = wallet_state.get("usdc", 0)
                return

        # Fallback: Fetch actual USDC balance from wallet (RPC)
        usdc_balance = self.wallet.get_balance(Settings.USDC_MINT)

        # Use actual balance, not hardcoded pool
        self.cash_available = usdc_balance

    def check_global_lock(self, watchers):
        """Check if any position is distressed and set global lock."""
        was_locked = self.global_locked
        self.global_locked = False
        distressed_asset = None

        for symbol, watcher in watchers.items():
            if watcher.is_distressed():
                self.global_locked = True
                distressed_asset = symbol
                break

        if self.global_locked and was_locked == False:
            print(f"   🔒 GLOBAL LOCK: {distressed_asset} is distressed")
        elif not self.global_locked and was_locked == True:
            print("   🔓 GLOBAL LOCK CLEARED")

        return self.global_locked

    def request_lock(self, symbol: str) -> bool:
        """
        Request a trade lock for a symbol.
        V17.0: Simple implementation - checks global lock status.
        Returns True if trade is allowed.
        """
        if self.global_locked:
            return False
        return True

    def release_lock(self):
        """
        Release trade lock after execution.
        V17.0: Placeholder for future atomic lock implementation.
        """
        pass

    # ═══════════════════════════════════════════════════════════════════
    # V14.0 Remote Control Methods
    # ═══════════════════════════════════════════════════════════════════

    def set_base_size(self, new_size_usd: float):
        """V14.1: Update base position size."""
        if new_size_usd < 0:
            return
        Settings.POSITION_SIZE_USD = float(new_size_usd)

    def set_max_exposure(self, new_cap_usd: float):
        """V14.2: Update total market risk budget."""
        if new_cap_usd < 0:
            return
        Settings.MAX_TOTAL_EXPOSURE_USD = float(new_cap_usd)

    def check_trade_budget(self, requested_size: float) -> bool:
        """
        V14.2: Check if new trade violates Total Exposure Cap.
        Returns True if trade is allowed.
        """
        if not hasattr(Settings, "MAX_TOTAL_EXPOSURE_USD"):
            Settings.MAX_TOTAL_EXPOSURE_USD = 1000.0

        # If budget is 0 or very small, assume trading halted manually
        if Settings.MAX_TOTAL_EXPOSURE_USD < 10.0:
            return False

        # NOTE: We rely on TradingCore to pass 'current_exposure' or we'd need
        # to sum held assets here. Since held_assets is updated by scan_wallet
        # (which runs frequently via DataBroker), we can try to estimate it here.

        # Estimate current exposure from held assets
        current_exposure = 0.0
        for symbol, balance in self.held_assets.items():
            if symbol == "USDC" or symbol == "SOL":
                continue
            # We don't have price here easily without shared cache.
            # Simpler: Let Trading Core handle the logic or bypass simple check
            # if we trust the cap against 'blocked' capital.
            pass

        # For V14.2, we will trust the Trading Core will check this explicitly
        # using its live watcher states. This method acts as a helper stub
        # or we implement full logic if we import SharedPriceCache.

        # Let's import SharedPriceCache to get live exposure estimate
        try:
            from src.core.shared_cache import SharedPriceCache

            wallet = SharedPriceCache.get_wallet_state(max_age=120)
            assets = wallet.get("assets", [])
            current_exposure = sum(a["usd_value"] for a in assets)
        except:
            current_exposure = 0.0

        if current_exposure + requested_size > Settings.MAX_TOTAL_EXPOSURE_USD:
            print(
                f"   ⚠️ EXPOSURE CAP: Current ${current_exposure:.0f} + ${requested_size:.0f} > ${Settings.MAX_TOTAL_EXPOSURE_USD:.0f}"
            )
            return False

        return True
