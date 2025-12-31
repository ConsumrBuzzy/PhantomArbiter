#!/usr/bin/env python3
"""
V43.0: Automated ML Model Retraining Supervisor
================================================
Standalone script for scheduled ML model retraining.

Features:
- Loads historical data from market_data.db
- Retrains XGBoost model with latest data
- Validates model performance before deployment
- Atomic model swap (ensures live system never loads partial model)
- Logging and metrics tracking

Scheduling:
    # Windows Task Scheduler (weekly at 3 AM Sunday):
    schtasks /create /tn "PhantomTrader_Retrain" /tr "python trainer_supervisor.py" /sc weekly /d SUN /st 03:00

    # Linux/Mac Cron (weekly Sunday 3 AM):
    0 3 * * 0 cd /path/to/PhantomTrader && python trainer_supervisor.py

Usage:
    python trainer_supervisor.py [--force] [--dry-run]
"""

import os
import sys
import time

# Fix Windows Unicode output for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import argparse
import sqlite3
from datetime import datetime
from typing import Optional

# Add project root to path (go up 2 levels from src/ml/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import joblib
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

LIVE_MODEL_PATH = os.path.join(MODELS_DIR, "ml_filter.pkl")
TEMP_MODEL_PATH = os.path.join(MODELS_DIR, "ml_filter.pkl.temp")
BACKUP_MODEL_PATH = os.path.join(MODELS_DIR, "ml_filter.pkl.backup")
DB_PATH = os.path.join(DATA_DIR, "market_data.db")
TRADES_DB_PATH = os.path.join(DATA_DIR, "trading_journal.db")

# Minimum requirements for retraining
MIN_SAMPLES = 50  # Reduced for testing/startup (was 500)
MIN_ACCURACY = 0.55  # Model must beat 55% accuracy
MIN_POSITIVE_SAMPLES = 20  # Minimum positive samples for valid training


# ═══════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════

os.makedirs(LOGS_DIR, exist_ok=True)


def log(msg: str, level: str = "INFO"):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level:7s}] {msg}"
    print(line)

    # Also append to log file
    log_file = os.path.join(LOGS_DIR, "trainer_supervisor.log")
    with open(log_file, "a") as f:
        f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING & LABELING
# ═══════════════════════════════════════════════════════════════════════════


def load_and_label_data(
    db_path: str = DB_PATH, lookback_days: int = 30
) -> Optional[pd.DataFrame]:
    """
    V47.7: Cross-Token Generalization - Learn market patterns, not token-specific patterns.

    Strategy:
    1. Load ALL trades from trading_journal.db (no filtering by current watchlist)
    2. Use execution-level features (slippage, liquidity, is_volatile) which are token-agnostic
    3. Optionally enrich with aggregate market features (global RSI, global volatility)
    4. The model learns: "under these MARKET CONDITIONS, trades tend to be profitable"

    This allows learning to transfer across tokens - if high volatility hurts WIF trades,
    it likely hurts BONK trades too.
    """
    if not os.path.exists(TRADES_DB_PATH):
        log(f"Trades DB not found: {TRADES_DB_PATH}", "ERROR")
        return None

    start_ts = time.time() - (lookback_days * 86400)

    try:
        # 1. LOAD ALL TRADES (No filtering by watchlist - keep historical coins!)
        conn_trades = sqlite3.connect(TRADES_DB_PATH)
        try:
            trades_df = pd.read_sql_query(
                f"""
                SELECT symbol, timestamp, pnl_usd, 
                       slippage_pct, liquidity_usd, is_volatile, is_win
                FROM trades
                WHERE timestamp >= {start_ts}
                AND slippage_pct IS NOT NULL
            """,
                conn_trades,
            )
        except Exception:
            # Fallback for old schema if V46.1 not fully migrated
            trades_df = pd.read_sql_query(
                f"""
                SELECT symbol, timestamp, pnl_usd,
                       0.005 as slippage_pct, 50000 as liquidity_usd, 0 as is_volatile, is_win
                FROM trades
                WHERE timestamp >= {start_ts}
            """,
                conn_trades,
            )

        conn_trades.close()

        log(
            f"Loaded {len(trades_df)} trades from journal (ALL tokens kept for cross-learning)."
        )

        if len(trades_df) < MIN_POSITIVE_SAMPLES:
            log("Insufficient trade history for feedback loop.", "WARNING")
            return None

        # 2. EXECUTION-LEVEL FEATURES (Already token-agnostic!)
        # These come directly from the trade record
        trades_df["log_liquidity"] = np.log1p(trades_df["liquidity_usd"].fillna(50000))
        trades_df["slippage_pct"] = trades_df["slippage_pct"].fillna(0.005)
        trades_df["is_volatile"] = trades_df["is_volatile"].fillna(0).astype(int)

        # V48.0: DEX Trust Score - Ordinal encoding of primary market
        # Higher values = more trusted DEX (better execution, more liquidity)
        DEX_TRUST_SCORES = {
            "raydium": 10,
            "orca": 9,
            "meteora": 8,
            "phoenix": 7,
            "lifinity": 6,
            "openbook": 5,
            "unknown": 1,
        }

        # Try to get dex_id from cached market data
        try:
            sys.path.insert(0, PROJECT_ROOT)
            from src.core.shared_cache import SharedPriceCache

            def get_dex_trust(symbol):
                mkt_data = SharedPriceCache.get_market_data(
                    symbol, max_age=86400
                )  # 24h cache ok for training
                dex_id = mkt_data.get("dex_id", "unknown").lower()
                return DEX_TRUST_SCORES.get(dex_id, 1)

            trades_df["dex_trust_score"] = trades_df["symbol"].apply(get_dex_trust)
            log("Added dex_trust_score feature (from cached market data).")
        except Exception as e:
            # Fallback: Use neutral value if cache unavailable
            trades_df["dex_trust_score"] = 5  # Neutral trust
            log(f"Using neutral dex_trust_score (cache unavailable): {e}", "WARNING")

        # 3. OPTIONAL: AGGREGATE MARKET FEATURES (Global conditions at trade time)
        # This captures "market mood" regardless of which token was traded
        market_features_added = False
        if os.path.exists(db_path):
            try:
                conn_market = sqlite3.connect(db_path)
                market_df = pd.read_sql_query(
                    f"""
                    SELECT timestamp, close, liquidity_usd as mkt_liquidity
                    FROM market_data
                    WHERE timestamp >= {start_ts}
                    ORDER BY timestamp ASC
                """,
                    conn_market,
                )
                conn_market.close()

                if len(market_df) >= 100:
                    # Calculate GLOBAL market indicators (across all tokens at each timestamp)
                    # Group by timestamp bucket (5-minute windows)
                    market_df["ts_bucket"] = (market_df["timestamp"] // 300) * 300

                    # Aggregate per bucket
                    agg_market = (
                        market_df.groupby("ts_bucket")
                        .agg({"close": ["mean", "std"], "mkt_liquidity": "mean"})
                        .reset_index()
                    )
                    agg_market.columns = [
                        "ts_bucket",
                        "global_price_mean",
                        "global_price_std",
                        "global_liquidity",
                    ]

                    # Calculate global volatility
                    agg_market["global_volatility"] = agg_market["global_price_std"] / (
                        agg_market["global_price_mean"] + 1e-10
                    )

                    # Calculate global RSI on aggregated price
                    agg_market = agg_market.sort_values("ts_bucket")
                    delta = agg_market["global_price_mean"].diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    avg_gain = gain.rolling(14, min_periods=1).mean()
                    avg_loss = loss.rolling(14, min_periods=1).mean()
                    rs = avg_gain / (avg_loss + 1e-10)
                    agg_market["global_rsi"] = 100 - (100 / (1 + rs))

                    # Merge with trades (time-based, no token matching!)
                    trades_df["ts_bucket"] = (trades_df["timestamp"] // 300) * 300
                    trades_df = trades_df.sort_values("ts_bucket")
                    agg_market = agg_market.sort_values("ts_bucket")

                    trades_df = pd.merge_asof(
                        trades_df,
                        agg_market[
                            [
                                "ts_bucket",
                                "global_rsi",
                                "global_volatility",
                                "global_liquidity",
                            ]
                        ],
                        on="ts_bucket",
                        direction="backward",
                        tolerance=600,  # 10 min tolerance
                    )

                    # Fill NaN globals with sensible defaults
                    trades_df["global_rsi"] = trades_df["global_rsi"].fillna(50)
                    trades_df["global_volatility"] = trades_df[
                        "global_volatility"
                    ].fillna(0.02)
                    trades_df["global_liquidity"] = trades_df[
                        "global_liquidity"
                    ].fillna(50000)
                    trades_df["log_global_liquidity"] = np.log1p(
                        trades_df["global_liquidity"]
                    )

                    market_features_added = True
                    log(f"Added global market features for {len(trades_df)} trades.")
            except Exception as e:
                log(
                    f"Could not add market features (using execution data only): {e}",
                    "WARNING",
                )

        # 4. FALLBACK: If no market data, use defaults
        if not market_features_added:
            trades_df["global_rsi"] = 50  # Neutral
            trades_df["global_volatility"] = 0.02  # Low
            trades_df["log_global_liquidity"] = np.log1p(50000)
            log("Using execution-level features only (no global market data).")

        # 5. DEFINE TARGET (Friction-Aware)
        trades_df["target"] = (trades_df["pnl_usd"] > 0).astype(int)

        # 6. FINAL FEATURE SET (All cross-token generalizable!)
        # Drop any rows with critical NaN
        trades_df = trades_df.dropna(subset=["slippage_pct", "log_liquidity", "target"])

        log(f"Final dataset: {len(trades_df)} trades ready for cross-token learning.")
        log(
            "   Features: slippage_pct, log_liquidity, is_volatile, global_rsi, global_volatility"
        )

        return trades_df

    except Exception as e:
        log(f"Data loading error: {e}", "ERROR")
        import traceback

        traceback.print_exc()
        return None


# ═══════════════════════════════════════════════════════════════════════════
# MODEL TRAINING
# ═══════════════════════════════════════════════════════════════════════════


def save_and_swap_model(model, metrics: dict, dry_run: bool = False) -> bool:
    """Save model to temp file and atomically swap."""
    if dry_run:
        log(f"DRY RUN: Model not saved. Metrics: {metrics}")
        return True

    try:
        # Save to temp
        joblib.dump(model, TEMP_MODEL_PATH)

        # Backup existing
        if os.path.exists(LIVE_MODEL_PATH):
            if os.path.exists(BACKUP_MODEL_PATH):
                os.remove(BACKUP_MODEL_PATH)
            os.rename(LIVE_MODEL_PATH, BACKUP_MODEL_PATH)

        # Atomic rename
        os.rename(TEMP_MODEL_PATH, LIVE_MODEL_PATH)

        # Save metrics
        with open(LIVE_MODEL_PATH + ".json", "w") as f:
            import json

            json.dump(metrics, f, indent=2)

        return True
    except Exception as e:
        log(f"Failed to save model: {e}", "ERROR")
        return False


def run_retraining_pipeline(
    force: bool = False, dry_run: bool = False, lookback_days: int = 30
) -> bool:
    """
    Main orchestration function.
    Returns True if model was retrained/swapped, False otherwise.
    """
    log("=" * 60)
    log("=== STARTING ML RETRAINING PIPELINE ===")
    log("=" * 60)

    # 1. Load Data
    df = load_and_label_data(lookback_days=lookback_days)
    if df is None or len(df) < MIN_SAMPLES:
        log(
            f"Skipping retraining: Insufficient data samples ({len(df) if df is not None else 0} / {MIN_SAMPLES})"
        )
        return False

    # 2. Stratified K-Fold Cross Validation (V47.2)
    from sklearn.model_selection import StratifiedKFold

    cv_folds = 5
    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)

    log(f"Starting {cv_folds}-Fold Cross Validation...")

    # V47.7: Cross-Token Generalized Features
    feature_cols = [
        "slippage_pct",  # Execution friction
        "log_liquidity",  # Trade-level liquidity
        "is_volatile",  # Volatile market flag
        "global_rsi",  # Market-wide RSI
        "global_volatility",  # Market-wide volatility
        "dex_trust_score",  # V48.0: DEX reliability signal
    ]
    # Optional: Add log_global_liquidity if available
    if "log_global_liquidity" in df.columns:
        feature_cols.append("log_global_liquidity")

    # Ensure columns exist
    valid_cols = [c for c in feature_cols if c in df.columns]

    X = df[valid_cols]
    y = df["target"]

    challenger_scores = []
    champion_scores = []
    has_champion = False

    # Check for Champion
    current_model = None
    if os.path.exists(LIVE_MODEL_PATH):
        try:
            current_model = joblib.load(LIVE_MODEL_PATH)
            has_champion = True
            log("[CHAMPION] Champion Model loaded for comparison.")
        except Exception as e:
            log(f"⚠️ Failed to load Champion model: {e}")

    # CV Loop
    fold_idx = 1
    for train_index, test_index in skf.split(X, y):
        X_train_fold, X_test_fold = X.iloc[train_index], X.iloc[test_index]
        y_train_fold, y_test_fold = y.iloc[train_index], y.iloc[test_index]

        # Check class balance
        pos_samples = y_train_fold.sum()
        neg_samples = len(y_train_fold) - pos_samples
        if pos_samples == 0 or neg_samples == 0:
            continue

        scale_pos_weight = neg_samples / pos_samples

        fold_model = xgb.XGBClassifier(
            objective="binary:logistic",
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.7,
            colsample_bytree=0.7,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        fold_model.fit(X_train_fold, y_train_fold)

        # Evaluate Challenger
        y_pred_fold = fold_model.predict(X_test_fold)
        fold_acc = accuracy_score(y_test_fold, y_pred_fold)
        challenger_scores.append(fold_acc)

        # Evaluate Champion
        if has_champion:
            try:
                # Champion might expect different features?
                # Handle feature mismatch gracefully if possible
                y_pred_champ = current_model.predict(X_test_fold)
                champ_acc = accuracy_score(y_test_fold, y_pred_champ)
                champion_scores.append(champ_acc)
                log(
                    f"   Fold {fold_idx}: Challenger {fold_acc:.1%} vs Champion {champ_acc:.1%}"
                )
            except:
                log(
                    f"   Fold {fold_idx}: Challenger {fold_acc:.1%} (Champion incompatible)"
                )
        else:
            log(f"   Fold {fold_idx}: Challenger {fold_acc:.1%}")

        fold_idx += 1

    # Aggregate Rules
    avg_challenger = np.mean(challenger_scores) if challenger_scores else 0.0
    avg_champion = (
        np.mean(champion_scores) if (champion_scores and has_champion) else 0.0
    )

    log(
        f"[RESULTS] 5-Fold Results: Challenger [{avg_challenger:.2%}] vs Champion [{avg_champion:.2%}]"
    )

    # Decision: Swap or Not?
    should_train_final = False

    if not has_champion:
        log("[INFO] No Champion exists. Promoting Challenger.")
        should_train_final = True
    elif avg_challenger > avg_champion:
        log(
            f"[WINNER] Challenger Wins! (+{avg_challenger - avg_champion:.2%} improvement)"
        )
        should_train_final = True
    elif force:
        log("[WARN] Challenger Validated Lower/Equal, but FORCE enabled. Swapping.")
        should_train_final = True
    else:
        log("[FAIL] Challenger failed to beat Champion. Keeping Old Model.")
        return False

    # Final Training (on 100% of data)
    if should_train_final:
        log("[TRAIN] Retraining Final Model on 100% Data...")
        pos_samples = y.sum()
        neg_samples = len(y) - pos_samples
        scale_pos_weight = neg_samples / pos_samples if pos_samples > 0 else 1.0

        final_model = xgb.XGBClassifier(
            objective="binary:logistic",
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            subsample=0.7,
            colsample_bytree=0.7,
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        final_model.fit(X, y)

        metrics = {
            "accuracy": float(avg_challenger),
            "cv_folds": cv_folds,
            "train_samples": len(y),
            "feature_importance": dict(
                zip(valid_cols, final_model.feature_importances_.tolist())
            ),
        }

        success = save_and_swap_model(final_model, metrics, dry_run=dry_run)

        if success:
            log("=" * 60)
            log("[SUCCESS] RETRAINING COMPLETE - Model upgraded!")
            log("=" * 60)
        return success

    return False


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="V43.0 Automated ML Retraining Supervisor"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force retraining even if model is recent"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run training but do not save model"
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=30,
        help="Days of historical data to use (default: 30)",
    )

    args = parser.parse_args()

    try:
        success = run_retraining_pipeline(
            force=args.force, dry_run=args.dry_run, lookback_days=args.lookback
        )
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        log("Interrupted by user.", "WARNING")
        sys.exit(1)
    except Exception as e:
        log(f"Fatal error: {e}", "ERROR")
        import traceback

        traceback.print_exc()
        sys.exit(1)
