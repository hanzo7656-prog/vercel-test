# core/indicators.py
# ============================================================
# محاسبه اندیکاتورهای تکنیکال
# ============================================================

from typing import List, Tuple, Optional


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    محاسبه شاخص قدرت نسبی (RSI)
    
    پارامترها:
        prices: لیست قیمت‌ها
        period: دوره محاسبه (پیش‌فرض: ۱۴)
    
    خروجی:
        لیست مقادیر RSI
    """
    if len(prices) < period + 1:
        return []
    
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_values = []
    
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        rsi_values.append(round(rsi, 2))
        
        if i < len(deltas) - 1:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    return rsi_values


def calculate_sma(prices: List[float], period: int = 20) -> List[Optional[float]]:
    """
    محاسبه میانگین متحرک ساده (SMA)
    
    پارامترها:
        prices: لیست قیمت‌ها
        period: دوره محاسبه (پیش‌فرض: ۲۰)
    
    خروجی:
        لیست مقادیر SMA (با None برای نقاطی که محاسبه نشده)
    """
    if len(prices) < period:
        return [None] * len(prices)
    
    sma_values = [None] * (period - 1)
    
    for i in range(period - 1, len(prices)):
        sma = sum(prices[i - period + 1:i + 1]) / period
        sma_values.append(round(sma, 2))
    
    return sma_values


def calculate_ema(prices: List[float], period: int = 20) -> List[Optional[float]]:
    """
    محاسبه میانگین متحرک نمایی (EMA)
    
    پارامترها:
        prices: لیست قیمت‌ها
        period: دوره محاسبه (پیش‌فرض: ۲۰)
    
    خروجی:
        لیست مقادیر EMA (با None برای نقاطی که محاسبه نشده)
    """
    if len(prices) < period:
        return [None] * len(prices)
    
    multiplier = 2 / (period + 1)
    ema_values = [None] * (period - 1)
    
    # اولین EMA = SMA
    first_sma = sum(prices[:period]) / period
    ema_values.append(round(first_sma, 2))
    
    for i in range(period, len(prices)):
        ema = (prices[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(round(ema, 2))
    
    return ema_values


def calculate_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    محاسبه MACD (Moving Average Convergence Divergence)
    
    پارامترها:
        prices: لیست قیمت‌ها
        fast_period: دوره سریع (پیش‌فرض: ۱۲)
        slow_period: دوره کند (پیش‌فرض: ۲۶)
        signal_period: دوره سیگنال (پیش‌فرض: ۹)
    
    خروجی:
        (macd_line, signal_line, histogram)
    """
    if len(prices) < slow_period:
        return [], [], []
    
    ema_fast = calculate_ema(prices, fast_period)
    ema_slow = calculate_ema(prices, slow_period)
    
    # محاسبه MACD Line
    macd_line = []
    for i in range(len(ema_fast)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line.append(round(ema_fast[i] - ema_slow[i], 2))
        else:
            macd_line.append(None)
    
    # حذف Noneهای ابتدایی
    valid_macd = [x for x in macd_line if x is not None]
    
    if len(valid_macd) < signal_period:
        return [], [], []
    
    # محاسبه Signal Line (EMA روی MACD)
    signal_line = calculate_ema(valid_macd, signal_period)
    
    # محاسبه Histogram
    histogram = []
    for i in range(len(valid_macd)):
        if signal_line[i] is not None:
            histogram.append(round(valid_macd[i] - signal_line[i], 2))
        else:
            histogram.append(None)
    
    # بازگرداندن با همان طول
    macd_with_none = [None] * (len(prices) - len(valid_macd)) + valid_macd
    signal_with_none = [None] * (len(prices) - len(signal_line)) + signal_line
    hist_with_none = [None] * (len(prices) - len(histogram)) + histogram
    
    return macd_with_none, signal_with_none, hist_with_none


def get_all_indicators(
    prices: List[float]
) -> dict:
    """
    دریافت همه اندیکاتورها
    """
    return {
        'rsi': calculate_rsi(prices, 14),
        'sma_20': calculate_sma(prices, 20),
        'sma_50': calculate_sma(prices, 50),
        'ema_20': calculate_ema(prices, 20),
        'macd': calculate_macd(prices, 12, 26, 9)
    }
