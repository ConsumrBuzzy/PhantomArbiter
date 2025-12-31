"""
V48.0: Performance Reporter
============================
Centralized performance monitoring for Model Health, Execution Quality, and Financial State.
Extracts key metrics from trading_journal.db, ml_filter.pkl, and CapitalManager.
"""

import os
import time
import sqlite3
from typing import Dict, Any, Optional
from datetime import datetime


# Paths
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TRADES_DB_PATH = os.path.join(PROJECT_ROOT, "data", "trading_journal.db")
MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "ml_filter.pkl")


class PerformanceReporter:
    """
    V48.0: Unified Performance Metrics Reporter.

    Extracts and formats three categories of metrics:
    1. Model Health - ML model accuracy, feature importance, freshness
    2. Execution Quality - Slippage, hold time, filter rate
    3. Financial State - Win rate, profit factor, PnL, drawdown
    """

    def __init__(self, lookback_hours: int = 24):
        """
        Initialize reporter with a configurable lookback window.

        Args:
            lookback_hours: Hours to look back for metrics (default: 24)
        """
        self.lookback_hours = lookback_hours
        self.lookback_seconds = lookback_hours * 3600

        # Runtime counters (updated by TradingCore)
        self.signals_total = 0
        self.signals_blocked = 0

    # ═══════════════════════════════════════════════════════════════════════
    # MODEL HEALTH METRICS
    # ═══════════════════════════════════════════════════════════════════════

    def get_model_health(self) -> Dict[str, Any]:
        """
        Extract ML model health metrics.

        Returns:
            Dict with champion_accuracy, feature_importance, model_age_hours, last_retrain
        """
        result = {
            "champion_accuracy": None,
            "feature_importance": {},
            "model_age_hours": None,
            "last_retrain": None,
            "model_exists": False,
        }

        if not os.path.exists(MODEL_PATH):
            return result

        result["model_exists"] = True

        try:
            import joblib

            model = joblib.load(MODEL_PATH)

            # Model Age
            mtime = os.path.getmtime(MODEL_PATH)
            result["last_retrain"] = datetime.fromtimestamp(mtime).strftime(
                "%Y-%m-%d %H:%M"
            )
            result["model_age_hours"] = round((time.time() - mtime) / 3600, 1)

            # Feature Importance
            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                # Get feature names if available
                feature_names = getattr(model, "feature_names_in_", None)
                if feature_names is None:
                    # Fallback to V47.7 feature set
                    feature_names = [
                        "slippage_pct",
                        "log_liquidity",
                        "is_volatile",
                        "global_rsi",
                        "global_volatility",
                        "log_global_liquidity",
                    ]

                # Build importance dict (top 5)
                importance_pairs = list(
                    zip(feature_names[: len(importances)], importances)
                )
                importance_pairs.sort(key=lambda x: x[1], reverse=True)

                result["feature_importance"] = {
                    name: round(float(imp) * 100, 1)
                    for name, imp in importance_pairs[:5]
                }

            # Try to get accuracy from model metadata (if stored)
            if hasattr(model, "_accuracy"):
                result["champion_accuracy"] = model._accuracy

        except Exception as e:
            result["error"] = str(e)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # EXECUTION QUALITY METRICS
    # ═══════════════════════════════════════════════════════════════════════

    def get_execution_quality(self) -> Dict[str, Any]:
        """
        Extract execution quality metrics from trading journal.

        Returns:
            Dict with avg_slippage_pct, avg_hold_time_min, filter_rate, avg_liquidity
        """
        result = {
            "avg_slippage_pct": None,
            "avg_hold_time_min": None,
            "filter_rate_pct": None,
            "signals_blocked": self.signals_blocked,
            "signals_total": self.signals_total,
            "avg_liquidity_usd": None,
            "trade_count": 0,
        }

        if not os.path.exists(TRADES_DB_PATH):
            return result

        start_ts = time.time() - self.lookback_seconds

        try:
            conn = sqlite3.connect(TRADES_DB_PATH)

            # Avg Slippage and Liquidity
            query = f"""
                SELECT 
                    AVG(slippage_pct) as avg_slippage,
                    AVG(liquidity_usd) as avg_liquidity,
                    COUNT(*) as trade_count
                FROM trades
                WHERE timestamp >= {start_ts}
                AND slippage_pct IS NOT NULL
            """
            cursor = conn.execute(query)
            row = cursor.fetchone()

            if row and row[2] > 0:
                result["avg_slippage_pct"] = round(row[0] * 100, 2) if row[0] else None
                result["avg_liquidity_usd"] = round(row[1], 0) if row[1] else None
                result["trade_count"] = row[2]

            # Avg Hold Time (requires entry_time and exit_time columns)
            try:
                hold_query = f"""
                    SELECT AVG(exit_time - entry_time) / 60.0 as avg_hold_min
                    FROM trades
                    WHERE timestamp >= {start_ts}
                    AND exit_time IS NOT NULL
                    AND entry_time IS NOT NULL
                """
                cursor = conn.execute(hold_query)
                hold_row = cursor.fetchone()
                if hold_row and hold_row[0]:
                    result["avg_hold_time_min"] = round(hold_row[0], 1)
            except:
                pass  # Columns may not exist

            conn.close()

            # Filter Rate (from runtime counters)
            if self.signals_total > 0:
                result["filter_rate_pct"] = round(
                    (self.signals_blocked / self.signals_total) * 100, 1
                )

        except Exception as e:
            result["error"] = str(e)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # FINANCIAL STATE METRICS
    # ═══════════════════════════════════════════════════════════════════════

    def get_financial_state(self) -> Dict[str, Any]:
        """
        Extract financial performance metrics.

        Returns:
            Dict with win_rate, profit_factor, total_pnl, max_drawdown
        """
        result = {
            "win_rate_pct": None,
            "profit_factor": None,
            "total_pnl_usd": None,
            "max_drawdown_pct": None,
            "wins": 0,
            "losses": 0,
            "trade_count": 0,
        }

        if not os.path.exists(TRADES_DB_PATH):
            return result

        start_ts = time.time() - self.lookback_seconds

        try:
            conn = sqlite3.connect(TRADES_DB_PATH)

            # Win Rate and PnL
            query = f"""
                SELECT 
                    SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(pnl_usd) as total_pnl,
                    SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd ELSE 0 END) as gross_profit,
                    SUM(CASE WHEN pnl_usd < 0 THEN ABS(pnl_usd) ELSE 0 END) as gross_loss,
                    COUNT(*) as trade_count
                FROM trades
                WHERE timestamp >= {start_ts}
            """
            cursor = conn.execute(query)
            row = cursor.fetchone()

            if row and row[5] > 0:
                wins = row[0] or 0
                losses = row[1] or 0
                total_pnl = row[2] or 0
                gross_profit = row[3] or 0
                gross_loss = row[4] or 0
                trade_count = row[5]

                result["wins"] = wins
                result["losses"] = losses
                result["trade_count"] = trade_count
                result["total_pnl_usd"] = round(total_pnl, 2)

                # Win Rate
                if trade_count > 0:
                    result["win_rate_pct"] = round((wins / trade_count) * 100, 1)

                # Profit Factor
                if gross_loss > 0:
                    result["profit_factor"] = round(gross_profit / gross_loss, 2)
                elif gross_profit > 0:
                    result["profit_factor"] = float("inf")

            conn.close()

            # Max Drawdown from CapitalManager
            try:
                from src.shared.system.capital_manager import get_capital_manager

                cm = get_capital_manager()
                # Get from engine stats if available
                for engine_name in cm.state.get("engines", {}):
                    engine = cm.get_engine_state(engine_name)
                    if engine:
                        stats = engine.get("stats", {})
                        peak = engine.get("peak_equity", 0)
                        current = engine.get("cash_balance", 0)
                        if peak > 0:
                            dd = ((peak - current) / peak) * 100
                            if (
                                result["max_drawdown_pct"] is None
                                or dd > result["max_drawdown_pct"]
                            ):
                                result["max_drawdown_pct"] = round(dd, 1)
            except:
                pass

        except Exception as e:
            result["error"] = str(e)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # REPORT GENERATION
    # ═══════════════════════════════════════════════════════════════════════

    def generate_report(self, include_header: bool = True) -> str:
        """
        Generate a formatted performance report.

        Returns:
            Markdown-formatted report string
        """
        model = self.get_model_health()
        execution = self.get_execution_quality()
        financial = self.get_financial_state()

        lines = []

        if include_header:
            lines.append("═" * 50)
            lines.append("📊 PHANTOM TRADER PERFORMANCE REPORT")
            lines.append(f"   Period: Last {self.lookback_hours}h")
            lines.append("═" * 50)
            lines.append("")

        # Model Health
        lines.append("🧠 MODEL HEALTH")
        if model["model_exists"]:
            if model["champion_accuracy"]:
                lines.append(
                    f"   • Champion Accuracy: {model['champion_accuracy']:.1f}%"
                )
            lines.append(f"   • Last Retrain: {model['model_age_hours']}h ago")
            if model["feature_importance"]:
                top_features = ", ".join(
                    [
                        f"{k} ({v}%)"
                        for k, v in list(model["feature_importance"].items())[:3]
                    ]
                )
                lines.append(f"   • Top Features: {top_features}")
        else:
            lines.append("   • No model loaded")
        lines.append("")

        # Execution Quality
        lines.append(f"⚡ EXECUTION QUALITY ({self.lookback_hours}h)")
        if execution["trade_count"] > 0:
            if execution["avg_slippage_pct"] is not None:
                lines.append(f"   • Avg Slippage: {execution['avg_slippage_pct']:.2f}%")
            if execution["avg_hold_time_min"] is not None:
                lines.append(
                    f"   • Avg Hold Time: {execution['avg_hold_time_min']:.1f} min"
                )
            if execution["filter_rate_pct"] is not None:
                lines.append(
                    f"   • Safety Gate Filter: {execution['filter_rate_pct']:.1f}% ({execution['signals_blocked']}/{execution['signals_total']})"
                )
            if execution["avg_liquidity_usd"]:
                lines.append(
                    f"   • Avg Liquidity: ${execution['avg_liquidity_usd']:,.0f}"
                )
        else:
            lines.append("   • No trades in period")
        lines.append("")

        # Financial State
        lines.append(f"💰 FINANCIAL STATE ({self.lookback_hours}h)")
        if financial["trade_count"] > 0:
            lines.append(
                f"   • Win Rate: {financial['win_rate_pct']:.1f}% ({financial['wins']}W/{financial['losses']}L)"
            )
            if financial["profit_factor"]:
                pf_str = (
                    f"{financial['profit_factor']:.2f}"
                    if financial["profit_factor"] != float("inf")
                    else "∞"
                )
                lines.append(f"   • Profit Factor: {pf_str}")
            pnl_sign = "+" if financial["total_pnl_usd"] >= 0 else ""
            lines.append(f"   • Total PnL: {pnl_sign}${financial['total_pnl_usd']:.2f}")
            if financial["max_drawdown_pct"] is not None:
                lines.append(
                    f"   • Max Drawdown: -{financial['max_drawdown_pct']:.1f}%"
                )
        else:
            lines.append("   • No trades in period")

        lines.append("")
        lines.append("═" * 50)

        return "\n".join(lines)

    def send_telegram_report(self) -> bool:
        """
        Send performance report via Telegram.

        Returns:
            True if sent successfully
        """
        try:
            from src.shared.notification.notifications import get_notifier

            notifier = get_notifier()

            report = self.generate_report()
            notifier.send_message(report, parse_mode=None)  # Plain text for reliability
            return True
        except Exception as e:
            print(f"Failed to send Telegram report: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════
    # RUNTIME TRACKING
    # ═══════════════════════════════════════════════════════════════════════

    def record_signal(self, was_blocked: bool = False):
        """
        Record a signal for filter rate tracking.
        Called by TradingCore when evaluating signals.
        """
        self.signals_total += 1
        if was_blocked:
            self.signals_blocked += 1

    def reset_counters(self):
        """Reset runtime counters (call at start of reporting period)."""
        self.signals_total = 0
        self.signals_blocked = 0


# Module-level instance
_reporter_instance: Optional[PerformanceReporter] = None


def get_performance_reporter() -> PerformanceReporter:
    """Get or create the singleton PerformanceReporter instance."""
    global _reporter_instance
    if _reporter_instance is None:
        _reporter_instance = PerformanceReporter()
    return _reporter_instance
