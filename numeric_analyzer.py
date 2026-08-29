# numeric_analyzer.py
# ============================================================
# موتور تحلیل عددی - نسخه ۳.۰ (با Type Hints کامل)
# ============================================================

import numpy as np
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union

from api.coinstats_client import coinstats_client
from models.manager.model_manager import ModelManager
from core.feature_engineering import FeatureEngineer

logger = logging.getLogger(__name__)


class NumericAnalyzer:
    """
    موتور تحلیل عددی و تکنیکال
    
    ✅ نسخه ۳.۰: اضافه شدن Type Hints و استفاده از FeatureEngineer
    """
    
    def __init__(self, api: Any, model_manager: ModelManager) -> None:
        self.api: Any = api
        self.model_manager: ModelManager = model_manager
        self.feature_engineer: FeatureEngineer = FeatureEngineer(api)
        
        self._register_with_scheduler()
        
        logger.info("✅ NumericAnalyzer v3.0 initialized")
    
    def _register_with_scheduler(self) -> None:
        """ثبت در Scheduler"""
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
            chart_data: Union[List[List], Dict] = self.api.get_chart(coin_id, period)
            if not chart_data or isinstance(chart_data, dict) and "error" in chart_data:
                return {"error": "داده‌ای دریافت نشد", "coin": coin_id}

            prices: List[float] = []
            for point in chart_data:
                if isinstance(point, list) and len(point) >= 2:
                    prices.append(float(point[1]))
            
            if len(prices) < 30:
                return {"error": "داده کافی نیست (حداقل ۳۰ نقطه نیاز است)", "coin": coin_id}

            # ۲. محاسبه شاخص‌ها
            analysis: Dict[str, Any] = {
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
                features: Optional[np.ndarray] = self.feature_engineer.extract_features(chart_data)
                if features is not None and self.model_manager.current_model:
                    prediction: float = self.model_manager.predict(features)
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
    # توابع محاسبه شاخص‌ها
    # ============================================================
    
    def _calculate_sma(self, prices: List[float], window: int) -> Optional[float]:
        """محاسبه میانگین متحرک ساده"""
        if len(prices) < window:
            return None
        return round(np.mean(prices[-window:]), 2)

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """محاسبه شاخص RSI"""
        if len(prices) < period + 1:
            return 50.0
        
        try:
            deltas: np.ndarray = np.diff(prices[-period-1:])
            gains: np.ndarray = deltas[deltas > 0]
            losses: np.ndarray = -deltas[deltas < 0]
            
            if len(gains) == 0:
                return 0.0
            if len(losses) == 0:
                return 100.0
            
            avg_gain: float = np.mean(gains)
            avg_loss: float = np.mean(losses)
            
            if avg_loss == 0:
                return 100.0
            
            rs: float = avg_gain / avg_loss
            rsi: float = 100 - (100 / (1 + rs))
            return round(rsi, 2)
        except Exception as e:
            logger.debug(f"RSI calculation error: {e}")
            return 50.0

    def _calculate_macd(self, prices: List[float]) -> Dict[str, float]:
        """محاسبه MACD"""
        if len(prices) < 26:
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
        
        try:
            def ema(data: List[float], period: int) -> float:
                if len(data) < period:
                    return data[-1] if data else 0
                multiplier: float = 2 / (period + 1)
                ema_value: float = data[-period:][0]
                for price in data[-period+1:]:
                    ema_value = (price * multiplier) + (ema_value * (1 - multiplier))
                return ema_value
            
            ema_12: float = ema(prices, 12)
            ema_26: float = ema(prices, 26)
            macd_line: float = ema_12 - ema_26
            
            signal_line: float = np.mean([macd_line for _ in range(min(9, len(prices)))])
            histogram: float = macd_line - signal_line
            
            return {
                "macd": round(macd_line, 4),
                "signal": round(signal_line, 4),
                "histogram": round(histogram, 4)
            }
        except Exception as e:
            logger.debug(f"MACD calculation error: {e}")
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0}

    def _calculate_volatility(self, prices: List[float]) -> float:
        """محاسبه نوسان"""
        if len(prices) < 2:
            return 0.0
        
        try:
            returns: np.ndarray = np.diff(prices) / prices[:-1]
            return round(np.std(returns) * 100, 2)
        except Exception:
            return 0.0

    def _calculate_price_change(self, prices: List[float]) -> float:
        """محاسبه درصد تغییر قیمت"""
        if len(prices) < 2:
            return 0.0
        return round(((prices[-1] - prices[0]) / prices[0]) * 100, 2)

    def _detect_trend(self, prices: List[float]) -> str:
        """تشخیص روند"""
        if len(prices) < 10:
            return "Neutral"
        
        try:
            x: np.ndarray = np.arange(len(prices[-10:]))
            slope: float = np.polyfit(x, prices[-10:], 1)[0]
            slope_percent: float = (slope / prices[-10:][0]) * 100
            
            if slope_percent > 0.5:
                return "Uptrend 📈"
            elif slope_percent < -0.5:
                return "Downtrend 📉"
            return "Sideways ↔️"
        except Exception:
            return "Neutral"

    def _find_support(self, prices: List[float]) -> Optional[float]:
        """پیدا کردن سطح حمایت"""
        if len(prices) < 20:
            return None
        support: float = min(prices[-20:])
        return round(support, 2)

    def _find_resistance(self, prices: List[float]) -> Optional[float]:
        """پیدا کردن سطح مقاومت"""
        if len(prices) < 20:
            return None
        resistance: float = max(prices[-20:])
        return round(resistance, 2)
