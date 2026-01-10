"""
V60.0: Market Regime Detector
=============================
Classifies the "Market Weather" into actionable regimes.
Used by the MerchantEnsemble to adapt strategies dynamically.

Regimes:
- Volatility: QUIET, NORMAL, VOLATILE, CHAOTIC
- Trend: RANGING, TRENDING_UP, TRENDING_DOWN
"""

import numpy as np
import pandas as pd
from typing import List, Dict
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS & ENUMS
# ═══════════════════════════════════════════════════════════════════════════


class VolatilityRegime:
    QUIET = "QUIET"  # Size: Aggressive. Stops: Tight.
    NORMAL = "NORMAL"  # Size: Standard. Stops: Standard.
    VOLATILE = "VOLATILE"  # Size: Reduced. Stops: Wide.
    CHAOTIC = "CHAOTIC"  # Size: Defense/Cash. Stops: Very Wide.


class TrendRegime:
    RANGING = "RANGING"  # Best for Scalper/Keltner (Mean Reversion)
    TRENDING_UP = "TRENDING_UP"  # Best for VWAP/Momentum
    TRENDING_DOWN = "TRENDING_DOWN"  # Best for Shorting/Cash


@dataclass
class MarketRegime:
    symbol: str
    volatility: str  # VolatilityRegime
    trend: str  # TrendRegime
    quality_score: int  # 0-100 score of how "tradeable" the market is
    atr_pct: float  # Normalized Volatility
    adx: float  # Trend Strength (0-100)
    rsi: float  # Momentum (0-100)
    bb_width: float  # Bollinger Band Width (for consolidation check)


# ═══════════════════════════════════════════════════════════════════════════
# DETECTOR LOGIC
# ═══════════════════════════════════════════════════════════════════════════


class RegimeDetector:
    """
    Analyzes candle data to determine the current Market Regime.
    """

    # Configuration
    ATR_PERIOD = 14
    ADX_PERIOD = 14

    # Volatility Thresholds (ATR %)
    THRESH_VOL_QUIET = 0.005  # 0.5%
    THRESH_VOL_HIGH = 0.02  # 2.0%
    THRESH_VOL_CHAOS = 0.04  # 4.0%

    # Trend Thresholds (ADX)
    THRESH_TREND_WEAK = 20
    THRESH_TREND_STRONG = 35

    @staticmethod
    def detect(candles: List[Dict], symbol: str = "UNKNOWN") -> MarketRegime:
        """
        Detect regime from a list of OHLCV candles.
        """
        if not candles or len(candles) < 50:
            return MarketRegime(
                symbol=symbol,
                volatility=VolatilityRegime.NORMAL,
                trend=TrendRegime.RANGING,
                quality_score=50,
                atr_pct=0.01,
                adx=0.0,
                rsi=50.0,
                bb_width=0.0,
            )

        # Convert to Pandas DataFrame for efficient calc
        df = pd.DataFrame(candles)

        # Ensure numeric
        cols = ["open", "high", "low", "close", "volume"]
        for c in cols:
            df[c] = pd.to_numeric(df[c])

        # 1. Calculate Indicators
        atr_pct = RegimeDetector._calc_atr_pct(df)
        adx = RegimeDetector._calc_adx(df)
        rsi = RegimeDetector._calc_rsi(df)
        bb_width = RegimeDetector._calc_bb_width(df)

        # 2. Classify Volatility
        if atr_pct < RegimeDetector.THRESH_VOL_QUIET:
            vol_regime = VolatilityRegime.QUIET
            q_vol = 90
        elif atr_pct < RegimeDetector.THRESH_VOL_HIGH:
            vol_regime = VolatilityRegime.NORMAL
            q_vol = 100
        elif atr_pct < RegimeDetector.THRESH_VOL_CHAOS:
            vol_regime = VolatilityRegime.VOLATILE
            q_vol = 60
        else:
            vol_regime = VolatilityRegime.CHAOTIC
            q_vol = 20

        # 3. Classify Trend
        ma_short = df["close"].ewm(span=20).mean().iloc[-1]
        ma_long = df["close"].ewm(span=50).mean().iloc[-1]
        price = df["close"].iloc[-1]

        if adx < RegimeDetector.THRESH_TREND_WEAK:
            trend_regime = TrendRegime.RANGING
            q_trend = 80  # Easy to scalp ranges
        else:
            # Strong enough to be trending
            is_uptrend = price > ma_short > ma_long
            is_downtrend = price < ma_short < ma_long

            if is_uptrend:
                trend_regime = TrendRegime.TRENDING_UP
                q_trend = 100  # Best condition
            elif is_downtrend:
                trend_regime = TrendRegime.TRENDING_DOWN
                q_trend = 40  # Harder to trade spot
            else:
                trend_regime = TrendRegime.RANGING  # Choppy trend
                q_trend = 60

        # 4. Final Quality Score (Weighted)
        # 60% Volatility Health, 40% Trend Health
        quality = int((q_vol * 0.6) + (q_trend * 0.4))

        return MarketRegime(
            symbol=symbol,
            volatility=vol_regime,
            trend=trend_regime,
            quality_score=quality,
            atr_pct=atr_pct,
            adx=adx,
            rsi=rsi,
            bb_width=bb_width,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # MATH HELPERS (Vectorized)
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _calc_bb_width(df: pd.DataFrame, period=20, std_dev=2.0) -> float:
        close = df["close"]
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()

        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)

        # Avoid division by zero
        width = (upper - lower) / sma
        # Return last value (handle NaN)
        val = width.iloc[-1]
        return float(val) if not pd.isna(val) else 0.0

    @staticmethod
    def _calc_atr_pct(df: pd.DataFrame, period=14) -> float:
        # TR = max(H-L, |H-Cp|, |L-Cp|)
        h, l, c = df["high"], df["low"], df["close"]
        prev_c = c.shift(1)

        tr1 = h - l
        tr2 = (h - prev_c).abs()
        tr3 = (l - prev_c).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]

        price = c.iloc[-1]
        return (atr / price) if price > 0 else 0.0

    @staticmethod
    def _calc_adx(df: pd.DataFrame, period=14) -> float:
        # Standard ADX implementation
        high = df["high"]
        low = df["low"]
        close = df["close"]

        plus_dm = high.diff()
        minus_dm = low.diff().apply(lambda x: -x if x < 0 else 0)  # Logic flip check?
        # Correct logic:
        # UpMove = H - prevH
        # DownMove = prevL - L
        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        # +DM
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        # -DM
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # TR (reuse logic or simplifies to):
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Smooth
        tr_smooth = pd.Series(tr).rolling(period).sum()
        plus_dm_smooth = pd.Series(plus_dm).rolling(period).sum()
        minus_dm_smooth = pd.Series(minus_dm).rolling(period).sum()

        # DI
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)

        # DX
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))

        # ADX
        adx = dx.rolling(period).mean().iloc[-1]
        return float(adx) if not pd.isna(adx) else 0.0

    @staticmethod
    def _calc_rsi(df: pd.DataFrame, period=14) -> float:
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
