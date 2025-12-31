import os
from dotenv import load_dotenv

# Load Environment Variables from project root .env
env_path = os.path.join(os.path.dirname(__file__), "../.env")
load_dotenv(env_path)


class Settings:
    # ═══════════════════════════════════════════════════════════════════
    # V5.3 PHANTOM TRADER CONFIGURATION (JSON-Based)
    # ═══════════════════════════════════════════════════════════════════

    # --- V10.1 Production Mode ---
    SILENT_MODE = True  # Set to False for debugging, True for live trading

    # V45.0: Engine Configuration
    ENGINE_MODE = "SCALPER"  # Default Mode: SCALPER, KELTNER, LONGTAIL, VWAP
    ENGINE_NAME = "PRIMARY"  # Default Identifier

    # Paths
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))

    @staticmethod
    def load_assets():
        """Load asset configuration from assets.json."""
        import json
        import os

        # V9.0: Load from data/watchlist.json for dynamic updates
        assets_file = os.path.join(Settings.DATA_DIR, "watchlist.json")

        active = {}
        volatile = {}
        watch = {}
        scout = {}
        watcher_pairs = []  # V101
        all_assets = {}

        try:
            with open(assets_file, "r") as f:
                data = json.load(f)

            for symbol, info in data.get("assets", {}).items():
                mint = info.get("mint", "")
                category = info.get("category", "WATCH")
                trading_enabled = info.get("trading_enabled", False)
                all_assets[symbol] = mint

                # V101: Support WATCHER category for high-priority rotation
                if category == "WATCHER":
                    # For pair rotation, we need the "NAME/QUOTE" format.
                    # Usually "NAME/USDC" or "NAME/SOL".
                    # We'll added the base symbols and the scanner will split them.
                    watcher_pairs.append(f"{symbol}/USDC")  # Default to USDC pod
                    watcher_pairs.append(f"{symbol}/SOL")  # Also SOL pod

                # Only add to ACTIVE if trading is enabled
                if category == "ACTIVE" and trading_enabled:
                    active[symbol] = mint
                elif category == "SCOUT":
                    scout[symbol] = mint
                elif category == "VOLATILE":
                    volatile[symbol] = mint
                else:
                    watch[symbol] = mint

            return (
                active,
                volatile,
                watch,
                scout,
                all_assets,
                data.get("assets", {}),
                watcher_pairs,
            )
        except Exception as e:
            print(f"⚠️ Failed to load assets.json: {e}")
            return {}, {}, {}, {}, {}, {}, []

    # Loaded at runtime
    ACTIVE_ASSETS = {}
    VOLATILE_ASSETS = {}
    WATCH_ASSETS = {}
    SCOUT_ASSETS = {}
    ASSETS = {}
    ASSET_METADATA = {}  # Store full info (e.g. coingecko_id)

    # Rate Limiting

    # Rate Limiting
    INIT_DELAY_SECONDS = 5  # Delay between CoinGecko calls

    # V11.0: CoinGecko API Key Support
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

    # V64.0: Bitquery API Key
    BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY", "")

    # V6.1.1: WebSocket Cache Settings
    CACHE_TIMEOUT_S = 15  # Cache data older than 15s triggers HTTP fallback

    # Stale Price Guard (V5.2)
    MAX_PRICE_DEVIATION = 0.20  # 20% - if price deviates >20% from avg, assume bad data

    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    TARGET_MINT = ""  # Set during init

    # Shared Capital Pool
    POOL_CAPITAL = 15.0  # Total portfolio cap
    BUY_SIZE = 4.0  # Max allocation per trade
    MAX_POSITIONS = 3  # Max simultaneous positions (ACTIVE only)
    CASH_RESERVE = 3.0  # Minimum cash buffer

    # ═══════════════════════════════════════════════════════════════════
    # V5.5 ATR-BASED POSITION SIZING (Risk Parity)
    # ═══════════════════════════════════════════════════════════════════
    FLAGS = 0  # Dummy line to keep offsets stable

    # ═══════════════════════════════════════════════════════════════════
    # V27.0 RISK-BASED POSITION SIZING
    # ═══════════════════════════════════════════════════════════════════
    RISK_PER_TRADE_PCT = 0.02  # Risk 2.0% of Total Account Equity per trade

    # Legacy (Deprecated by V27.0)
    FIXED_DOLLAR_RISK = 0.15  # Deprecated
    ATR_MULTIPLIER = 2.0  # Stop-loss distance = ATR × 2.0
    MIN_BUY_SIZE = 3.00  # Floor: Prevent micro-transactions
    MAX_BUY_SIZE = 5.00  # Ceiling: Cap single position exposure

    # ═══════════════════════════════════════════════════════════════════
    # V28.0 AUTOMATED RISK CONTROLS (Circuit Breakers)
    # ═══════════════════════════════════════════════════════════════════
    MAX_DRAWDOWN_PER_STRATEGY_PCT = 0.15  # 15% Max Drawdown -> Auto-Disable Strategy
    DAILY_DRAWDOWN_LIMIT_PCT = 0.05  # 5% Daily Loss -> Auto-Pause Strategy for 24h

    # Global Lock Thresholds
    DISTRESSED_THRESHOLD = -0.005  # -0.5% triggers global lock

    # Legacy compatibility
    TOTAL_CAPITAL_USDC = POOL_CAPITAL
    SCALPER_BUDGET = BUY_SIZE
    SENTINEL_BUDGET = BUY_SIZE

    # Strategy Toggles
    ENABLE_SCALPER = True
    ENABLE_SENTINEL = True

    # Global Kill Switch
    MAX_DAILY_DRAWDOWN = 0.10  # Stop if portfolio drops > 10%

    # ═══════════════════════════════════════════════════════════════════
    # V39.0: ISOLATED PAPER TRADING ENVIRONMENT
    # ═══════════════════════════════════════════════════════════════════
    CAPITAL_SPLIT_STRATEGIES = 1  # Unified Engine gets 100% of capital (was 3)
    MAX_POSITIONS_PER_ENGINE = 5  # Increased for single engine (was 3)

    # RPC
    RPC_URL = "https://api.mainnet-beta.solana.com"
    HELIUS_WS_URL = os.getenv("HELIUS_WS_URL", "wss://api.mainnet-beta.solana.com")

    # Execution Settings
    SLIPPAGE_BPS = 750  # 7.5% (Increased for low-liquidity memecoins)
    ENABLE_TRADING = False

    # Gas Management
    GAS_CRITICAL_SOL = 0.01  # ~1.50 USD (Increased buffer to prevent dust lock)
    GAS_FLOOR_SOL = 0.05  # ~$7.50
    GAS_REPLENISH_USD = 5.0  # Buy $5 SOL (more robust refill)

    # V7.0: Swing Trading Thresholds
    TAKE_PROFIT_PCT = 0.04  # +4.0% - Swing Trading Target
    STOP_LOSS_PCT = -0.03  # -3.0% - Net Stop-Loss

    # Legacy thresholds (fallback)
    BREAKEVEN_FLOOR_PCT = 0.00325  # 0.325% - Nuclear Exit
    FAST_SCALP_PCT = 0.005  # 0.500% - Fast Scalp
    RECOVERY_TARGET_PCT = 0.00825  # 0.825% - Recovery Exit
    SCALPER_STOP_LOSS = -0.10  # Legacy
    SENTINEL_STOP_LOSS = -0.01  # Legacy

    # Anti-Cascade Guard
    HIBERNATION_SECONDS = 1800  # 30 minutes after Stop-Loss
    EXTREME_OVERSOLD_RSI = 20  # RSI < 20 required for re-entry after SL

    # Safety Guards (from live_bot.py parity)
    MIN_PRICE_THRESHOLD = 0.000000001  # V6: Supports memecoins (was 0.0001)
    MIN_VALID_PRICES = 15  # Require 15+ prices before trading
    MAX_TRADES_PER_HOUR = 3  # Hourly trade limit per asset

    # ═══════════════════════════════════════════════════════════════════
    # V5.7 TOKEN SAFETY VALIDATOR THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════
    MIN_LIQUIDITY_USD = 100_000  # Minimum $100K liquidity (relaxed for memecoins)
    MAX_TOP10_HOLDER_PCT = 0.30  # Max 30% supply held by top 10 wallets (anti-dump)
    REQUIRE_MINT_REVOKED = True  # Block if mint authority is active
    REQUIRE_FREEZE_REVOKED = True  # Block if freeze authority is active
    ENABLE_HONEYPOT_CHECK = True  # Run honeypot simulation before trades
    HONEYPOT_TEST_AMOUNT = 1_000_000  # 1 Token (Atomic Units @ 6 decimals)
    HONEYPOT_SLIPPAGE_BPS = 1000  # 10% Slippage for simulation

    # Phase 3: Adaptive Slippage Tiers (BPS)
    # Start low for stable trades, escalate as needed
    ADAPTIVE_SLIPPAGE_TIERS = [100, 300, 500, 1000]  # 1% → 3% → 5% → 10%

    # Phase 3: Priority Fee for faster transactions
    PRIORITY_FEE_MICRO_LAMPORTS = 50000  # ~0.00005 SOL per compute unit

    # ═══════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════
    # V10.3 AGGRESSIVE FINANCIAL EFFICIENCY (Prioritize Liquidity)
    # ═══════════════════════════════════════════════════════════════════
    GAS_FLOOR_SOL = 0.06  # ~$10.00 (Hard limit for Paper/Real)
    GAS_CRITICAL_SOL = 0.002  # ~0.26 USD (Auto-Refuel trigger)
    GAS_REPLENISH_USD = 1.00  # Buy min SOL to restore safety

    CASH_FLOOR_USD = 2.00  # Emergency buffer only

    # Legacy V9.7 Constants (Overridden above)
    # GAS_FLOOR_SOL = 0.05
    # GAS_CRITICAL_SOL = 0.015
    # GAS_REPLENISH_USD = 5.00

    # ═══════════════════════════════════════════════════════════════════
    # V8.2 TRAILING STOP LOSS (TSL) CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════
    TSL_ENABLED = True
    TSL_ACTIVATION_PCT = 0.020  # +2.0% Profit triggers TSL
    TSL_TRAIL_PCT = 0.015  # 1.5% Trail distance

    # V8.5 GATEKEEPER
    ENABLE_VALIDATION = True  # Check win rate before buyinggle for all safety checks

    # V14.0/V15.0 REMOTE CONTROL & SYNC
    ENABLE_TRADING = False  # DISABLED for safety (Monitor/Paper by default)
    POSITION_SIZE_USD = 15.0  # V79.0: Base size for HIGH confidence trades
    MAX_TOTAL_EXPOSURE_USD = 50.0  # V79.0: $50 Budget ceiling

    # V79.0: Confidence-Based Position Sizing (Ranged Buy-Ins)
    # Adjusts trade size based on signal confidence score
    POSITION_SIZE_HIGH_PCT = 0.30  # 30% of cash for HIGH confidence (>0.75)
    POSITION_SIZE_MED_PCT = 0.10  # 10% of cash for MEDIUM confidence (0.5-0.75)
    POSITION_SIZE_LOW_PCT = 0.05  # 5% of cash for LOW confidence (<0.5)

    # V20.0: Fractional Position Sizing (Prevents "All-In" trades)
    MAX_CAPITAL_PER_TRADE_PCT = 0.30  # 30% of available cash per trade max

    # V85.0: Aggressive Paper Mode (Learn from failures)
    # When True, loosens thresholds to generate more trades for learning
    PAPER_AGGRESSIVE_MODE = True  # Enable permissive thresholds for paper trading
    PAPER_ML_THRESHOLD = 0.35  # Lower ML threshold (was 0.65, then 0.45)
    PAPER_RSI_THRESHOLD = 55  # Higher RSI ceiling (was 35, then 50)
    PAPER_MIN_LIQUIDITY = 2500  # Lower liquidity gate to $2.5k (was $10k)
    PAPER_ALLOW_TOKEN_2022 = True  # Allow Token-2022 trades

    # V85.1: Agent Cross-Talk & Intelligence
    # PAPER_AGGRESSION_LEVEL controls how much agents "trust" each other
    PAPER_AGGRESSION_LEVEL = "HIGH"  # CONSERVATIVE, BALANCED, HIGH
    LIVE_MIN_CONFIDENCE = 0.85  # Live trading requires 85% consensus
    PAPER_MIN_CONFIDENCE = 0.35  # Paper trades at 35% consensus (Brave Mode)
    WHALE_FOLLOW_THRESHOLD = 5.0  # Min SOL swap to trigger whale alert
    WHALE_VOUCH_BONUS = 0.15  # +15% confidence if whale vouches

    # V86.3: ML On-Demand
    ML_AUTO_RETRAIN = (
        False  # False = Passive Mode (Alert Only), True = Active Retraining
    )

    # V16.1: Paper Wallet Simulation Settings
    SIMULATION_SWAP_FEE_SOL = 0.0002  # Realistic DEX fee (~$0.03) for small capital

    # V46.0: Dynamic Slippage Modeling
    SLIPPAGE_BASE_PCT = 0.003  # 0.3% Base Slippage (Spread + Latency)
    SLIPPAGE_VOLATILITY_MULTIPLIER = 3.0  # 3x Slippage in Volatile Markets
    SLIPPAGE_IMPACT_MULTIPLIER = 0.05  # Size Impact Factor (0.05 * Size/Liq)

    # V21.0: Simulation Realism Suite
    TRANSACTION_FAILURE_RATE_PCT = 0.05  # 5% of transactions fail (network/RPC/JITO)
    LOW_LIQUIDITY_THRESHOLD_USD = 100000  # Below $100K TVL = low liquidity
    LOW_LIQUIDITY_EXTRA_SLIPPAGE_MAX = 0.02  # Up to 2% extra slippage on low-liq tokens

    # V47.6: Position Reconciliation - Zombie Bag Sweep
    MAX_HOLD_TIME_MINUTES = (
        15  # Force-sell positions held longer than this (Scalping Mode)
    )

    # V48.0: Capital Discipline
    MAX_CAPITAL_DRAWDOWN_PCT = (
        0.75  # Reset wallet if Equity drops 75% below Start Capital (25% Remaining)
    )
    CLONE_WALLET_ON_FIRST_RUN = (
        True  # If True, Paper Wallet starts with exact Real Wallet balance
    )

    # V81.0: Smart Thread Manager (Resource Kindness)
    THREAD_POOL_MAX_WORKERS = 4  # Max concurrent I/O tasks (kind to work PC)
    THREAD_POOL_LOW_PRIORITY = True  # Lower OS priority for bot process

    # V22.0: Execution Delay Simulation
    EXECUTION_DELAY_MIN_MS = 200  # Min latency (ms)
    EXECUTION_DELAY_MAX_MS = 500  # Max latency (ms)

    # V23.0: Partial Fills Simulation
    PARTIAL_FILL_RATE_PCT = 0.10  # 10% chance of partial fill
    MIN_FILL_PCT = 0.80  # Minimum 80% of order fills

    # V24.0: SOL Balance Gate (Prevents trades if SOL too low for gas)
    MIN_SOL_RESERVE = 0.01  # Minimum SOL to keep for gas (2 trades buffer)

    # V26.0: Hyper-Realism Suite
    # MEV (Sandwich Attacks)
    MEV_RISK_RATE_PCT = (
        0.15  # 15% chance of being sandwiched on high-value/visible trades
    )
    MEV_PENALTY_MAX_PCT = 0.03  # Up to 3% price impact penalty

    # Dynamic Network Congestion
    HIGH_VOLATILITY_THRESHOLD_PCT = 0.10  # 10% price change in 5m triggers congestion
    CONGESTION_FAILURE_RATE_PCT = 0.15  # 15% failure rate during congestion
    CONGESTION_DELAY_MAX_MS = 1000  # Up to 1s delay during congestion

    # V40.0: Unified Alert Policies
    ALERT_POLICIES = {
        "DEX_VOLATILITY_HIGH_ATR_PCT": 0.04,  # 4% ATR triggers volatility alert
        "DEX_TREND_BREAKOUT_ADX": 30.0,  # ADX > 30 triggers trend alert
        "DYDX_MARGIN_LOW_RATIO": 0.30,  # 30% margin remaining trigger
        "ALERT_COOLDOWN_SECONDS": 300,  # 5 minutes between same-type alerts
    }

    # ═══════════════════════════════════════════════════════════════════
    # V63.0: SIMULATION (DRY RUN)
    # ═══════════════════════════════════════════════════════════════════
    DRY_RUN = False  # V89.14: Disabled to allow paper trades (was blocking with silent simulation)
    SIMULATION_LOG_FILE = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../data")),
        "simulated_trades.csv",
    )

    # ═══════════════════════════════════════════════════════════════════
    # V52.0: PUMP.FUN ADAPTER
    # ═══════════════════════════════════════════════════════════════════
    DYDX_ENABLED = (
        os.getenv("DYDX_ENABLED", "false").lower() == "true"
    )  # Read from .env
    DYDX_MNEMONIC = os.getenv("DYDX_MNEMONIC", "")  # Wallet seed phrase (from .env)
    DYDX_NETWORK = os.getenv("DYDX_NETWORK", "testnet")  # "mainnet" or "testnet"
    EXECUTION_MODE = os.getenv(
        "EXECUTION_MODE", "DEX"
    )  # "DEX" (Solana) or "DYDX" (Perpetuals)

    # ═══════════════════════════════════════════════════════════════════
    # V40.0: ALERT POLICIES (Proactive Notification Thresholds)
    # ═══════════════════════════════════════════════════════════════════
    ALERT_POLICIES = {
        # DEX Market Volatility (Alert if ATR % exceeds threshold)
        "DEX_VOLATILITY_HIGH_ATR_PCT": 0.04,  # 4% ATR = HIGH volatility
        # DEX Trend Strength (Alert when ADX crosses into strong trend)
        "DEX_TREND_BREAKOUT_ADX": 30.0,  # ADX > 30 = Strong trend
        # dYdX Risk Metrics (Alert if margin ratio drops below threshold)
        "DYDX_MARGIN_LOW_RATIO": 0.30,  # 30% margin available = warning
        # Engine Risk (Alert on drawdown breach)
        "ENGINE_DRAWDOWN_BREACH_PCT": 0.05,  # 5% drawdown = alert
        # Alert cooldown (seconds) - prevents spam
        "ALERT_COOLDOWN_SECONDS": 300,  # 5 minutes between same alerts
    }

    # State tracking (to prevent duplicate alerts)
    LAST_ALERT_STATE = {}

    # ═══════════════════════════════════════════════════════════════════
    # V49.0: ORCA CLMM (MARKET MAKING) CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════
    ORCA_ENABLED = True  # V49.0: Orca CLMM Market Maker ENABLED
    ORCA_DEFAULT_POOL = (
        "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"  # SOL/USDC $32.5M TVL
    )
    ORCA_TIGHT_RANGE_PCT = 1.0  # ±1% range for sideways markets
    ORCA_WIDE_RANGE_PCT = 5.0  # ±5% range for neutral regime
    ORCA_HARVEST_INTERVAL_HOURS = 4  # Collect fees every 4 hours
    ORCA_MIN_LIQUIDITY_USD = 100  # Minimum capital to deploy
    ORCA_MAX_LIQUIDITY_PCT = 0.20  # Max 20% of capital in CLMM

    # ═══════════════════════════════════════════════════════════════════
    # V50.0: MULTI-PAD DISCOVERY CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════
    MULTIPAD_ENABLED = True  # V50.1: Enabled for multi-market monitoring

    # Launchpad Program IDs (Solana mainnet)
    LAUNCHPAD_PROGRAMS = {
        "PUMPFUN": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
        "RAYDIUM_LAUNCHLAB": "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
        "BONKFUN": "BAGSB9TpGrZxQbEsrEznv5jXXdwyP6AXerN8aVRiAmcv",
        "BAGS_FM": "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN",
        "METEORA_DLMM": "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    }

    # Migration Sniping
    MIGRATION_SNIPE_ENABLED = True  # V50.1: Enabled for paper trading test
    MIGRATION_MIN_LIQUIDITY_USD = 2500  # V86.3 Brave Mode: Lower threshold for sniping
    MIGRATION_MAX_ENTRY_USD = 50  # Max entry per opportunity

    # V50.1: Launchpad Trading Settings
    LAUNCHPAD_TRADE_SIZE = 5.0  # $5 per snipe (Brave Mode: smaller bets)
    LAUNCHPAD_MIN_CONFIDENCE = 0.5  # V86.3 Brave Mode: Lower confidence for snipes
    LAUNCHPAD_AUTO_TRADE = True  # Set True to enable auto paper trading

    # V52.0: PumpPortal Integration (Bonding Curve Trading)
    PUMP_PORTAL_ENABLED = True  # Enable direct bonding curve trading
    PUMP_PORTAL_API_URL = "https://pumpportal.fun/api/trade-local"

    # Social Signals (Bags.fm)
    SOCIAL_SIGNALS_ENABLED = False  # Requires API key
    BAGS_FM_API_KEY = ""  # Set in .env

    # ═══════════════════════════════════════════════════════════════════
    # V1.0: ARBITRAGE ENGINE CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════

    # Mode Selection: SPATIAL | TRIANGULAR | FUNDING | ALL
    ARBITRAGE_MODE = os.getenv("ARBITRAGE_MODE", "FUNDING")

    # Budget Configuration
    ARBITRAGE_BUDGET_USD = float(os.getenv("ARBITRAGE_BUDGET", "500.0"))
    MAX_TRADE_SIZE_USD = 100.0  # Max per trade to limit slippage
    DEFAULT_TRADE_SIZE_USD = 50.0  # Default test size

    # ─── Spatial Arbitrage (Cross-DEX) ───
    SPATIAL_MIN_SPREAD_PCT = 0.3  # Minimum spread to trigger (0.3%)
    SPATIAL_PAIRS = [  # Monitored pairs
        "SOL/USDC",
        "BONK/USDC",
        "WIF/USDC",
    ]

    # ─── Triangular Arbitrage (Intra-DEX Cycles) ───
    TRI_MIN_PROFIT_PCT = 0.02  # Minimum net profit (0.02% after fees)
    TRI_CYCLES = [  # Cycle definitions
        ["SOL", "USDC", "BONK"],  # SOL → USDC → BONK → SOL
        ["SOL", "USDC", "WIF"],
    ]

    # ─── Funding Rate Arbitrage (Cash & Carry via Drift) ───
    FUNDING_MIN_RATE_PCT = 0.01  # Min 8h funding rate to enter (0.01%)
    FUNDING_POSITION_SIZE = 250.0  # Half budget on spot, half on perp
    DRIFT_LEVERAGE = 1.0  # 1x leverage (delta neutral)

    # ─── Risk Parameters ───
    MAX_SLIPPAGE_PCT = 0.5  # Maximum acceptable slippage
    # Realistic fees on $100 trade: ~$0.90 (0.5% trading + $0.20 gas + 0.15% slip + $0.05 buffer)
    # Require $0.25 profit AFTER fees to be safe
    MIN_PROFIT_AFTER_FEES = 0.25  # Minimum USD profit per cycle
    GAS_BUFFER_SOL = 0.05  # Keep 0.05 SOL for gas
    MIN_SPREAD_PCT = 0.3  # Minimum spread (was 0.1, increased for safety)

    # ─── Monitoring ───
    DASHBOARD_REFRESH_SEC = 2.0  # Dashboard update interval
    TELEGRAM_ALERT_THRESHOLD = 0.3  # Alert on 0.3%+ spreads
    TELEGRAM_ENABLED = True  # Send Telegram alerts

    # ─── DEX Configuration ───
    JUPITER_API_URL = "https://quote-api.jup.ag/v6"
    RAYDIUM_ENABLED = True
    ORCA_ARB_ENABLED = True  # Enable Orca for arbitrage scanning

    # ─── V101 Priority Rotation ───
    # Pod Priorities (Lower = Higher Priority)
    POD_PRIORITIES = {
        "ACTIVE": 1,  # Core trading pairs
        "VOLATILE": 2,  # High movement pairs
        "WATCH": 3,  # Monitoring
        "SCOUT": 4,  # New discoveries
    }

    # Watcher Pairs (Always Priority 0 - Every Scan)
    # Format: ["SOL/USDC", "WIF/USDC"]
    WATCHER_PAIRS = []

    # ═══════════════════════════════════════════════════════════════════
    # V140: NARROW PATH CONFIGURATION (Multi-Hop Token Hopping)
    # ═══════════════════════════════════════════════════════════════════
    # Strategic Pivot: Disable Scalper/Intelligence, enable Graph Arb

    HOP_ENGINE_ENABLED = True  # Enable Multi-Hop Arbiter (disables Scalper agents)
    SCALPER_ENABLED = False  # Disable Token Scalper (latency war = losing battle)

    # ─── Graph Pathfinding Parameters ───
    HOP_MAX_LEGS = 4  # Maximum hops (3, 4, or 5)
    HOP_MIN_PROFIT_PCT = 0.20  # Minimum theoretical profit (0.2%)
    HOP_MIN_LIQUIDITY_USD = 5000  # Minimum pool liquidity for consideration
    HOP_SCAN_INTERVAL_SEC = 2.0  # Graph scan frequency

    # ─── Pool Matrix Config ───
    HOP_STALE_SLOT_THRESHOLD = 150  # Prune edges older than ~60s (150 slots)
    HOP_MAX_POOLS = 10000  # Memory guard: max pools in graph

    # ─── Jito Bundle Config ───
    HOP_TIP_LAMPORTS = 10000  # Default Jito tip for multi-hop bundles
    HOP_MAX_BUNDLE_SIZE = 5  # Max instructions per bundle (1 tip + 4 swaps)


try:
    a, v, w, s, all_a, meta, wp = Settings.load_assets()
    Settings.ACTIVE_ASSETS = a
    Settings.VOLATILE_ASSETS = v
    Settings.WATCH_ASSETS = w
    Settings.SCOUT_ASSETS = s
    Settings.ASSETS = all_a
    Settings.ASSET_METADATA = meta
    Settings.WATCHER_PAIRS = wp  # V101
    Settings.TARGET_MINT = a.get("WIF", "")
except Exception:
    pass
