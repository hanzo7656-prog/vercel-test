# numeric_analyzer.py
# ============================================================
# موتور تحلیل عددی - محاسبه شاخص‌های تکنیکال و تحلیل داده‌ها
# ============================================================

import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional

class NumericAnalyzer:
    def __init__(self, api, model_manager):
        self.api = api
        self.model_manager = model_manager

    def analyze_coin(self, coin_id: str, period: str = "24h") -> Dict[str, Any]:
        """
        تحلیل کامل یک ارز و بازگرداندن همه شاخص‌ها و سیگنال‌ها
        """
        # ۱. دریافت داده‌های قیمت
        chart_data = self.api.get_chart(coin_id, period)
        if not chart_data:
            return {"error": "داده‌ای دریافت نشد"}

        prices = [point[1] for point in chart_data if isinstance(point, list) and len(point) >= 2]
        if len(prices) < 30:
            return {"error": "داده کافی نیست"}

        # ۲. محاسبه شاخص‌ها
        analysis = {
            "coin": coin_id,
            "current_price": prices[-1],
            "price_change": self._calculate_price_change(prices),
            "sma_7": self._calculate_sma(prices, 7),
            "sma_30": self._calculate_sma(prices, 30),
            "rsi": self._calculate_rsi(prices),
            "macd": self._calculate_macd(prices),
            "volatility": self._calculate_volatility(prices),
            "trend": self._detect_trend(prices),
            "support": self._find_support(prices),
            "resistance": self._find_resistance(prices),
        }

        # ۳. دریافت سیگنال از مدل XGBoost
        try:
            # شبیه‌سازی استخراج ویژگی‌ها (باید با extract_features هماهنگ شود)
            features = self._extract_features_from_data(prices) 
            if features is not None and self.model_manager.current_model:
                prediction = self.model_manager.predict(features)
                analysis["xgboost_signal"] = "BUY" if prediction > 0.65 else "SELL" if prediction < 0.35 else "NEUTRAL"
                analysis["xgboost_confidence"] = int(abs(prediction - 0.5) * 200)
        except Exception as e:
            analysis["xgboost_signal"] = "ERROR"
            analysis["xgboost_confidence"] = 0

        return analysis

    # ---------- توابع کمکی برای محاسبه شاخص‌ها ----------
    def _calculate_sma(self, prices, window):
        if len(prices) < window:
            return None
        return round(np.mean(prices[-window:]), 2)

    def _calculate_rsi(self, prices, period=14):
        # ... (کد محاسبه RSI)
        return 50  # مقدار پیش‌فرض

    def _calculate_macd(self, prices):
        # ... (کد محاسبه MACD)
        return 0.0

    def _calculate_volatility(self, prices):
        returns = np.diff(prices) / prices[:-1]
        return round(np.std(returns), 4)

    def _detect_trend(self, prices):
        # تشخیص روند با رگرسیون خطی
        if len(prices) < 10:
            return "Neutral"
        x = np.arange(len(prices[-10:]))
        slope = np.polyfit(x, prices[-10:], 1)[0]
        if slope > 0.5:
            return "Uptrend"
        elif slope < -0.5:
            return "Downtrend"
        return "Sideways"

    def _find_support(self, prices):
        # ساده‌شده: پیدا کردن کمترین قیمت اخیر
        return round(min(prices[-20:]), 2) if len(prices) >= 20 else None

    def _find_resistance(self, prices):
        # ساده‌شده: پیدا کردن بیشترین قیمت اخیر
        return round(max(prices[-20:]), 2) if len(prices) >= 20 else None

    def _calculate_price_change(self, prices):
        if len(prices) < 2:
            return 0.0
        return round(((prices[-1] - prices[0]) / prices[0]) * 100, 2)

    def _extract_features_from_data(self, prices):
        # اینجا باید منطق مشابه extract_features از app.py پیاده‌سازی شود
        # برای نمونه، یک آرایه خالی برمی‌گردانیم
        return np.zeros(13)  # تعداد ویژگی‌ها
