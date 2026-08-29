# core/feature_engineering.py
# ============================================================
# مهندسی ویژگی یکپارچه - نسخه ۱.۰
# ============================================================

import numpy as np
import logging
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """
    استخراج ویژگی‌ها از داده‌های قیمتی
    یکپارچه‌سازی منطق feature extraction از system.py و numeric_analyzer.py
    """
    
    # نام ویژگی‌ها
    FEATURE_NAMES = [
        "return_1", "return_3", "return_5", "return_10",
        "sma_5", "sma_10", "sma_20",
        "volatility", "fear_greed",
        "trend_5", "trend_10", "trend_20", "r2"
    ]
    
    def __init__(self, api=None):
        self.api = api
    
    def extract_features(self, chart_data: List[List]) -> Optional[np.ndarray]:
        """
        استخراج ویژگی‌ها از داده‌های خام قیمت
        
        پارامترها:
            chart_data: لیست نقاط قیمتی [[timestamp, price], ...]
        
        خروجی:
            آرایه numpy از ویژگی‌ها
        """
        if not chart_data or len(chart_data) < 30:
            return None
        
        # استخراج قیمت‌ها
        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 30:
            return None
        
        prices = np.array(prices, dtype=np.float32)
        features = []
        
        # 1. بازده‌ها (Returns)
        for lag in [1, 3, 5, 10]:
            if len(prices) > lag:
                ret = (prices[-1] - prices[-lag-1]) / (prices[-lag-1] + 1e-8)
                features.append(np.clip(ret, -0.5, 0.5))
            else:
                features.append(0.0)
        
        # 2. میانگین متحرک ساده (SMA)
        for window in [5, 10, 20]:
            if len(prices) >= window:
                sma = np.mean(prices[-window:])
                ratio = prices[-1] / (sma + 1e-8) - 1
                features.append(np.clip(ratio, -0.5, 0.5))
            else:
                features.append(0.0)
        
        # 3. نوسان (Volatility)
        if len(prices) >= 15:
            returns = np.diff(prices[-15:]) / (prices[-15:-1] + 1e-8)
            volatility = np.std(returns)
            features.append(np.clip(volatility, 0, 0.5))
        else:
            features.append(0.0)
        
        # 4. شاخص ترس و طمع (از API یا کش)
        features.append(self._get_fear_greed_value())
        
        # 5. شیب قیمت (روند)
        for window in [5, 10, 20]:
            if len(prices) >= window:
                slope = np.polyfit(range(window), prices[-window:], 1)[0]
                slope_norm = slope / (prices[-1] + 1e-8) * 100
                features.append(np.clip(slope_norm, -10, 10))
            else:
                features.append(0.0)
        
        # 6. قدرت روند (R-squared)
        if len(prices) >= 10:
            x = np.arange(10)
            y = prices[-10:]
            slope, intercept = np.polyfit(x, y, 1)
            y_pred = slope * x + intercept
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1 - (ss_res / (ss_tot + 1e-8))
            features.append(np.clip(r2, -1, 1))
        else:
            features.append(0.0)
        
        return np.array(features, dtype=np.float32)
    
    def extract_features_for_training(
        self, 
        chart_data: List[List], 
        lookback: int = 20,
        future: int = 3
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        استخراج ویژگی‌ها برای آموزش مدل (با Label)
        
        پارامترها:
            chart_data: داده‌های قیمتی
            lookback: پنجره بازگشتی
            future: تعداد قدم‌های آینده برای Label
        
        خروجی:
            (features, labels): آرایه‌های ویژگی و برچسب
        """
        if not chart_data or len(chart_data) < 30:
            return None, None
        
        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 30:
            return None, None
        
        prices = np.array(prices, dtype=np.float32)
        features_list = []
        labels_list = []
        
        for i in range(lookback, len(prices) - future):
            window = prices[i-lookback:i+1]
            current_price = prices[i]
            future_price = prices[i+future]
            
            # Label: 1 اگر قیمت آینده بالاتر باشد
            label = 1 if future_price > current_price else 0
            
            # استخراج ویژگی‌ها از پنجره
            feat = self._extract_features_from_window(window)
            if feat is not None:
                features_list.append(feat)
                labels_list.append(label)
        
        if not features_list:
            return None, None
        
        return np.array(features_list, dtype=np.float32), np.array(labels_list, dtype=np.int32)
    
    def _extract_features_from_window(self, window: np.ndarray) -> Optional[List[float]]:
        """استخراج ویژگی‌ها از یک پنجره قیمتی"""
        if len(window) < 10:
            return None
        
        features = []
        
        # 1. بازده‌ها
        for lag in [1, 3, 5]:
            if len(window) > lag:
                ret = (window[-1] - window[-lag-1]) / (window[-lag-1] + 1e-8)
                features.append(np.clip(ret, -0.5, 0.5))
            else:
                features.append(0.0)
        
        # 2. SMA
        for w in [5, 10]:
            if len(window) >= w:
                sma = np.mean(window[-w:])
                ratio = window[-1] / (sma + 1e-8) - 1
                features.append(np.clip(ratio, -0.5, 0.5))
            else:
                features.append(0.0)
        
        # 3. Volatility
        if len(window) >= 10:
            returns = np.diff(window[-10:]) / (window[-10:-1] + 1e-8)
            volatility = np.std(returns)
            features.append(np.clip(volatility, 0, 0.5))
        else:
            features.append(0.0)
        
        # 4. Fear & Greed
        features.append(self._get_fear_greed_value())
        
        # 5. Trend
        for w in [5, 10]:
            if len(window) >= w:
                slope = np.polyfit(range(w), window[-w:], 1)[0]
                slope_norm = slope / (window[-1] + 1e-8) * 100
                features.append(np.clip(slope_norm, -10, 10))
            else:
                features.append(0.0)
        
        # 6. R-squared
        if len(window) >= 10:
            x = np.arange(10)
            y = window[-10:]
            slope, intercept = np.polyfit(x, y, 1)
            y_pred = slope * x + intercept
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            ss_res = np.sum((y - y_pred) ** 2)
            r2 = 1 - (ss_res / (ss_tot + 1e-8))
            features.append(np.clip(r2, -1, 1))
        else:
            features.append(0.0)
        
        # 7. BTC Dominance
        features.append(self._get_btc_dominance())
        
        return features
    
    def _get_fear_greed_value(self) -> float:
        """دریافت مقدار ترس و طمع (با کش)"""
        try:
            if self.api:
                fg = self.api.get_fear_greed(use_cache=True)
                if fg and 'now' in fg:
                    return fg['now'].get('value', 50) / 100.0
        except Exception as e:
            logger.debug(f"Fear & Greed error: {e}")
        return 0.5
    
    def _get_btc_dominance(self) -> float:
        """دریافت مقدار سلطه بیت‌کوین"""
        try:
            if self.api:
                dominance = self.api.get_btc_dominance(use_cache=True)
                if dominance:
                    return dominance.get('dominance', 50) / 100.0
        except Exception as e:
            logger.debug(f"BTC Dominance error: {e}")
        return 0.5


# نمونه Singleton
feature_engineer = FeatureEngineer()
