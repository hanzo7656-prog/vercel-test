# core/rule_engine/indicators.py
# ============================================================
# Indicators - محاسبه اندیکاتورهای موردنیاز قوانین
# نسخه ۱.۰
# ============================================================
# 
# این فایل مستقل از core/indicators.py کار می‌کنه
# و روی DataFrame کار می‌کنه (نه روی list).
# 
# چرا جدا؟
#   core/indicators.py روی list کار می‌کنه و برای Rule Engine
#   کند و نامناسبه. این نسخه vectorized و سریع‌تره.
# ============================================================

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# Individual Indicators
# ============================================================

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    محاسبه RSI به صورت vectorized
    
    Args:
        close: سری قیمت‌های Close
        period: دوره (پیش‌فرض ۱۴)
    
    Returns:
        سری RSI (۰-۱۰۰)
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # میانگین متحرک نمایی (Wilder's smoothing)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    return rsi


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """محاسبه SMA"""
    return series.rolling(window=period, min_periods=period).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """محاسبه EMA"""
    return series.ewm(span=period, adjust=False).mean()


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    محاسبه MACD
    
    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """محاسبه ATR"""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    
    return atr


# ============================================================
# Main Calculator
# ============================================================

def compute_indicators(
    df: pd.DataFrame,
    config: dict | None = None,
) -> pd.DataFrame:
    """
    محاسبه همه اندیکاتورهای موردنیاز Rule Engine
    
    Args:
        df: DataFrame با ستون‌های Open, High, Low, Close, Volume
        config: تنظیمات سفارشی برای دوره‌ها
    
    Returns:
        DataFrame با ستون‌های اضافه‌شده:
            - RSI
            - MA50, MA200
            - MACD, MACD_signal, MACD_hist
            - Volume_MA20, Volume_Ratio
            - ATR
    """
    if df is None or df.empty:
        return df
    
    # چک ستون‌های اجباری
    required = ["Close", "High", "Low", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.error(f"❌ Missing columns in df: {missing}")
        return df
    
    config = config or {}
    
    # کپی برای جلوگیری از mutation
    df = df.copy()
    
    # اطمینان از sort بر اساس index (زمان)
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    
    # ============================================================
    # RSI
    # ============================================================
    rsi_period = int(config.get("rsi_period", 14))
    df["RSI"] = compute_rsi(close, rsi_period)
    
    # ============================================================
    # Moving Averages
    # ============================================================
    ma_periods = config.get("ma_periods", [50, 200])
    for period in ma_periods:
        df[f"MA{period}"] = compute_sma(close, period)
    
    # ============================================================
    # MACD
    # ============================================================
    macd_fast = int(config.get("macd_fast", 12))
    macd_slow = int(config.get("macd_slow", 26))
    macd_signal = int(config.get("macd_signal", 9))
    
    macd_line, signal_line, histogram = compute_macd(
        close, fast=macd_fast, slow=macd_slow, signal=macd_signal
    )
    df["MACD"] = macd_line
    df["MACD_signal"] = signal_line
    df["MACD_hist"] = histogram
    
    # ============================================================
    # Volume
    # ============================================================
    vol_ma_period = int(config.get("volume_ma_period", 20))
    df["Volume_MA20"] = compute_sma(volume, vol_ma_period)
    df["Volume_Ratio"] = volume / (df["Volume_MA20"] + 1e-10)
    
    # ============================================================
    # ATR
    # ============================================================
    atr_period = int(config.get("atr_period", 14))
    df["ATR"] = compute_atr(high, low, close, atr_period)
    
    # ============================================================
    # Returns (برای context)
    # ============================================================
    df["Return_1"] = close.pct_change(1)
    df["Return_3"] = close.pct_change(3)
    df["Return_5"] = close.pct_change(5)
    
    return df


# ============================================================
# Helpers
# ============================================================

def get_indicator_columns() -> List[str]:
    """لیست اندیکاتورهای محاسبه‌شده"""
    return [
        "RSI",
        "MA50", "MA200",
        "MACD", "MACD_signal", "MACD_hist",
        "Volume_MA20", "Volume_Ratio",
        "ATR",
        "Return_1", "Return_3", "Return_5",
    ]


def validate_indicators(df: pd.DataFrame) -> tuple[bool, List[str]]:
    """
    بررسی اینکه اندیکاتورهای موردنیاز محاسبه شدن یا نه
    
    Returns:
        (is_valid, missing_columns)
    """
    required = ["RSI", "MACD_hist", "Volume_Ratio"]
    missing = [c for c in required if c not in df.columns]
    return len(missing) == 0, missing


__all__ = [
    "compute_rsi",
    "compute_sma",
    "compute_ema",
    "compute_macd",
    "compute_atr",
    "compute_indicators",
    "get_indicator_columns",
    "validate_indicators",
]
