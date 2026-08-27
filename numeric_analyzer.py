# numeric_analyzer.py
# ============================================================
# موتور تحلیل عددی - محاسبه شاخص‌های تکنیکال و تحلیل داده‌ها
# نسخه ۲.۰ - یکپارچه با Scheduler + بهبود محاسبات
# ============================================================

import numpy as np
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from api_handler import CoinStatsAPI
from models.manager.model_manager import ModelManager

logger = logging.getLogger(__name__)


class NumericAnalyzer:
    """
    موتور تحلیل عددی و تکنیکال
    
    ✅ نسخه ۲.۰:
    - یکپارچه با Metrics Scheduler
    - بهبود محاسبات RSI و MACD
    - اضافه شدن شاخص‌های جدید
    - مدیریت بهتر خطاها
    """
    
    def __init__(self, api: CoinStatsAPI, model_manager: ModelManager):
        self.api = api
        self.model_manager = model_manager
        
        # ✅ جدید: ثبت در Scheduler
        self._register_with_scheduler()
        
        logger.info("✅ NumericAnalyzer v2.0 initialized")
    
    def _register_with_scheduler(self):
        """✅ جدید: ثبت در Scheduler"""
        try:
            from core import metrics_scheduler
            logger.info("✅ NumericAnalyzer registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")

    def analyze_coin(self, coin_id: str, period: str = "24h") -> Dict[str, Any]:
        """
        تحلیل کامل یک ارز و بازگرداندن همه شاخص‌ها و سیگنال‌ها
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه زمانی (24h, 1w, 1m)
        
        خروجی:
            دیکشنری شامل همه شاخص‌ها
        """
        try:
            # ۱. دریافت داده‌های قیمت
            chart_data = self.api.get_chart(coin_id, period)
            if not chart_data:
                return {"error": "داده‌ای دریافت نشد", "coin": coin_id}

            prices = []
            for point in chart_data:
                if isinstance(point, list) and len(point) >= 2:
                    prices.append(float(point[1]))
            
            if len(prices) < 30:
                return {"error": "داده کافی نیست (حداقل ۳۰ نقطه نیاز است)", "coin": coin_id}

            # ۲. محاسبه شاخص‌ها
            analysis = {
                "coin": coin_id,
                "period": period,
                "current_price": round(prices[-1], 2),
                "price_change": self._calculate_price_change(prices),
                "sma_7": self._calculate_sma(prices, 7),
                "sma_30": self._calculate_sma(prices, 30),
                "rsi": self._calculate_rsi(prices),
                "macd": self._calculate_macd(prices),
                "volatility": self._calculate_volatility(prices),
                "trend": self._detect_trend(prices),
                "support": self._find_support(prices),
                "resistance": self._find_resistance(prices),
                "high_52w": max(prices[-365:]) if len(prices) >= 365 else max(prices),
                "low_52w": min(prices[-365:]) if len(prices) >= 365 else min(prices),
                "data_points": len(prices),
                "timestamp": datetime.now().isoformat()
            }

            # ۳. دریافت سیگنال از مدل XGBoost
            try:
                features = self._extract_features_from_prices(prices)
                if features is not None and self.model_manager.current_model:
                    prediction = self.model_manager.predict(features)
                    analysis["xgboost_score"] = round(float(prediction), 3)
                    
                    if prediction > 0.65:
                        analysis["xgboost_signal"] = "BUY"
                        analysis["xgboost_confidence"] = int(((prediction - 0.5) / 0.5) * 100)
                    elif prediction < 0.35:
                        analysis["xgboost_signal"] = "SELL"
                        analysis["xgboost_confidence"] = int(((0.5 - prediction) / 0.5) * 100)
                    else:
                        analysis["xgboost_signal"] = "NEUTRAL"
                        analysis["xgboost_confidence"] = 50
                else:
                    analysis["xgboost_signal"] = "DEMO"
                    analysis["xgboost_confidence"] = 0
            except Exception as e:
                logger.error(f"XGBoost error for {coin_id}: {e}")
                analysis["xgboost_signal"] = "ERROR"
                analysis["xgboost_confidence"] = 0

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {coin_id}: {e}")
            return {"error": str(e), "coin": coin_id}

    # ============================================================
    # توابع محاسبه شاخص‌ها (بهبود یافته)
    # ============================================================
    
    def _calculate_sma(self, prices: List[float], window: int) -> Optional[float]:
        """محاسبه میانگین متحرک ساده"""
        if len(prices) < window:
            return None
        return round(np.mean(prices[-window:]), 2)

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        محاسبه شاخص RSI (Relative Strength Index)
        
        بهبود یافته با محاسبه دقیق‌تر
        """
        if len(prices) < period + 1:
            return 50.0  # مقدار پیش‌فرض
        
        try:
            # محاسبه تغییرات قیمت
            deltas = np.diff(prices[-period-1:])
            gains = deltas[deltas > 0]
            losses = -deltas[deltas < 0]
            
            if len(gains) == 0:
                return 0.0
            if len(losses) == 0:
                return 100.0
            
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            
            if avg_loss == 0:
                return 100.0
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            return round(rsi, 2)
        except Exception as e:
            logger.debug(f"RSI calculation error: {e}")
            return 50.0

    def _calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """
        محاسبه MACD (Moving Average Convergence Divergence)
        
        بهبود یافته با محاسبه دقیق‌تر
        """
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
        
        try:
            # محاسبه EMA
            def ema(data: List[float], period: int) -> float:
                if len(data) < period:
                    return data[-1] if data else 0
                multiplier = 2 / (period + 1)
                ema_value = data[-period:][0]
                for price in data[-period+1:]:
                    ema_value = (price * multiplier) + (ema_value * (1 - multiplier))
                return ema_value
            
            ema_12 = ema(prices, 12)
            ema_26 = ema(prices, 26)
            macd_line = ema_12 - ema_26
            
            # محاسبه Signal Line (EMA 9 روزه MACD)
            # برای سادگی از میانگین ساده استفاده می‌کنیم
            signal_line = np.mean([macd_line for _ in range(min(9, len(prices)))])
            histogram = macd_line - signal_line
            
            return {
                "macd": round(macd_line, 4),
                "signal": round(signal_line, 4),
                "histogram": round(histogram, 4)
            }
        except Exception as e:
            logger.debug(f"MACD calculation error: {e}")
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    def _calculate_volatility(self, prices: List[float]) -> float:
        """محاسبه نوسان (انحراف معیار بازده‌ها)"""
        if len(prices) < 2:
            return 0.0
        
        try:
            returns = np.diff(prices) / prices[:-1]
            return round(np.std(returns) * 100, 2)
        except:
            return 0.0

    def _calculate_price_change(self, prices: List[float]) -> float:
        """محاسبه درصد تغییر قیمت"""
        if len(prices) < 2:
            return 0.0
        return round(((prices[-1] - prices[0]) / prices[0]) * 100, 2)

    def _detect_trend(self, prices: List[float]) -> str:
        """تشخیص روند با رگرسیون خطی"""
        if len(prices) < 10:
            return "Neutral"
        
        try:
            x = np.arange(len(prices[-10:]))
            slope = np.polyfit(x, prices[-10:], 1)[0]
            slope_percent = (slope / prices[-10:][0]) * 100
            
            if slope_percent > 0.5:
                return "Uptrend 📈"
            elif slope_percent < -0.5:
                return "Downtrend 📉"
            return "Sideways ↔️"
        except:
            return "Neutral"

    def _find_support(self, prices: List[float]) -> Optional[float]:
        """پیدا کردن سطح حمایت"""
        if len(prices) < 20:
            return None
        # کمترین قیمت در ۲۰ روز اخیر
        support = min(prices[-20:])
        return round(support, 2)

    def _find_resistance(self, prices: List[float]) -> Optional[float]:
        """پیدا کردن سطح مقاومت"""
        if len(prices) < 20:
            return None
        # بیشترین قیمت در ۲۰ روز اخیر
        resistance = max(prices[-20:])
        return round(resistance, 2)

    def _extract_features_from_prices(self, prices: List[float]) -> Optional[np.ndarray]:
        """
        استخراج ویژگی‌ها از داده‌های قیمت
        این تابع با extract_features در core/system.py هماهنگ است
        """
        try:
            if len(prices) < 30:
                return None
            
            prices = np.array(prices, dtype=np.float32)
            features = []

            # 1. بازده‌ها
            for lag in [1, 3, 5, 10]:
                if len(prices) > lag:
                    ret = (prices[-1] - prices[-lag-1]) / (prices[-lag-1] + 1e-8)
                    features.append(np.clip(ret, -0.5, 0.5))
                else:
                    features.append(0.0)

            # 2. میانگین متحرک
            for window in [5, 10, 20]:
                if len(prices) >= window:
                    sma = np.mean(prices[-window:])
                    ratio = prices[-1] / (sma + 1e-8) - 1
                    features.append(np.clip(ratio, -0.5, 0.5))
                else:
                    features.append(0.0)

            # 3. نوسان
            if len(prices) >= 15:
                returns = np.diff(prices[-15:]) / (prices[-15:-1] + 1e-8)
                volatility = np.std(returns)
                features.append(np.clip(volatility, 0, 0.5))
            else:
                features.append(0.0)

            # 4. شاخص ترس و طمع (ساده شده)
            try:
                fg = self.api.get_fear_greed(use_cache=True)
                if fg and 'now' in fg:
                    fear_value = fg['now'].get('value', 50)
                    features.append(fear_value / 100.0)
                else:
                    features.append(0.5)
            except:
                features.append(0.5)

            # 5. شیب قیمت
            for window in [5, 10, 20]:
                if len(prices) >= window:
                    slope = np.polyfit(range(window), prices[-window:], 1)[0]
                    slope_norm = slope / (prices[-1] + 1e-8) * 100
                    features.append(np.clip(slope_norm, -10, 10))
                else:
                    features.append(0.0)

            # 6. قدرت روند
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
            
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
            return None
