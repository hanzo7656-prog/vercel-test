# application/use_cases/predict_coin.py
# ============================================================
# Use Case: Predict Coin - نسخه ۲.۰
# Repository Integration + Cache + Better Demo
# ============================================================

import time
import logging
import numpy as np
from typing import Optional, Dict, Any, List
from datetime import datetime

from domain.entities.prediction import Prediction, SignalType
from domain.value_objects.signal import Signal
from domain.interfaces.api_client import APIClient
from core.feature_engineering import FeatureEngineer
from models.manager.model_manager import ModelManager
from infrastructure.repositories import repos

logger = logging.getLogger(__name__)


class PredictCoinUseCase:
    """
    Use Case پیش‌بینی یک ارز
    
    رفع باگ‌ها:
        - ذخیره Prediction در Repository
        - رفع issue with id
    
    ارتقاها:
        - Repository integration
        - Cache for predictions
        - Better demo predict
        - Result validation
    """
    
    # Cache TTL
    CACHE_TTL = 300  # ۵ دقیقه
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        feature_engineer: FeatureEngineer,
    ) -> None:
        self.api_client = api_client
        self.model_manager = model_manager
        self.feature_engineer = feature_engineer
        
        # اعتبارسنجی بازه‌ها
        self.valid_periods: List[str] = ["24h", "1w", "1m", "3m", "6m"]
        
        # Prediction Repository
        self.prediction_repo = repos.prediction
        
        # Cache
        try:
            from infrastructure.database import get_cache
            self.cache = get_cache()
        except Exception:
            self.cache = None
        
        logger.info("✅ PredictCoinUseCase v2.0 initialized")
    
    # ============================================================
    # Execute - Single
    # ============================================================
    
    def execute(
        self,
        coin_id: str,
        period: str = "24h",
        save: bool = True,
        use_cache: bool = True,
    ) -> Prediction:
        """
        اجرای Use Case
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه زمانی
            save: آیا در DB ذخیره بشه؟
            use_cache: آیا از cache استفاده بشه؟
        
        خروجی:
            Entity Prediction
        
        استثناها:
            ValueError: بازه نامعتبر
            RuntimeError: داده دریافت نشد
        """
        start_time = time.time()
        
        # ===== ۱. اعتبارسنجی =====
        if period not in self.valid_periods:
            raise ValueError(
                f"Invalid period: {period}. "
                f"Must be one of {self.valid_periods}"
            )
        
        # ===== ۲. Cache Check =====
        cache_key = f"prediction:{coin_id}:{period}"
        
        if use_cache and self.cache and self.cache.is_connected():
            cached = self.cache.get(cache_key)
            if cached and isinstance(cached, dict):
                logger.debug(f"⚡ Prediction from cache: {coin_id}")
                return self._dict_to_prediction(cached)
        
        # ===== ۳. دریافت داده =====
        chart_data = self.api_client.get_chart(coin_id, period)
        
        if not chart_data or (
            isinstance(chart_data, dict) and "error" in chart_data
        ):
            error_msg = (
                chart_data.get("error", "No data")
                if isinstance(chart_data, dict) else "No data"
            )
            logger.error(f"Chart data failed for {coin_id}: {error_msg}")
            raise RuntimeError(f"Failed to get chart data: {error_msg}")
        
        # ===== ۴. استخراج ویژگی =====
        features = self.feature_engineer.extract_features(chart_data)
        
        if features is None:
            raise RuntimeError(
                f"Insufficient data for {coin_id} (need 30+ points)"
            )
        
        # ===== ۵. پیش‌بینی =====
        if self.model_manager.current_model:
            try:
                prediction_score = self.model_manager.predict(features)
                model_mode = "PRODUCTION"
            except Exception as e:
                logger.error(f"Model prediction error: {e}")
                prediction_score = self._demo_predict(features)
                model_mode = "DEMO_FALLBACK"
        else:
            prediction_score = self._demo_predict(features)
            model_mode = "DEMO"
        
        # ===== ۶. Signal =====
        signal = Signal.from_score(prediction_score)
        
        # ===== ۷. اطلاعات ارز =====
        coin_info = self.api_client.get_coin(coin_id)
        current_price = coin_info.get("price", 0) if coin_info else 0
        coin_name = coin_info.get("name", coin_id) if coin_info else coin_id
        
        # ===== ۸. ساخت Entity =====
        processing_time = (time.time() - start_time) * 1000
        
        prediction = Prediction(
            coin=coin_id,
            coin_name=coin_name,
            current_price=float(current_price),
            signal=signal.get_text(),
            signal_type=signal.type,
            confidence=signal.confidence,
            confidence_score=signal.confidence,
            prediction_score=float(prediction_score),
            period=period,
            model_mode=model_mode,
            timestamp=datetime.now(),
            processing_time_ms=round(processing_time, 2),
            data_points=len(chart_data) if chart_data else 0,
        )
        
        # ===== ۹. ذخیره در Repository (رفع باگ) =====
        if save:
            try:
                self.prediction_repo.save(prediction)
                logger.debug(
                    f"✅ Prediction saved: {coin_id} ({signal.type.value})"
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not save prediction: {e}")
        
        # ===== ۱۰. Cache =====
        if use_cache and self.cache and self.cache.is_connected():
            try:
                self.cache.set(
                    cache_key,
                    prediction.to_dict(),
                    ttl=self.CACHE_TTL,
                )
            except Exception as e:
                logger.debug(f"Cache set error: {e}")
        
        logger.info(
            f"✅ Prediction for {coin_id}: "
            f"{signal.type.value} ({signal.confidence}%)"
        )
        
        return prediction
    
    # ============================================================
    # Execute - Multiple
    # ============================================================
    
    def execute_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        save: bool = True,
    ) -> List[Prediction]:
        """
        اجرای پیش‌بینی برای چند ارز
        
        پارامترها:
            coins: لیست ارزها
            period: بازه
            save: ذخیره بشه؟
        
        خروجی:
            لیست Predictions
        """
        predictions: List[Prediction] = []
        
        for coin in coins:
            try:
                prediction = self.execute(
                    coin,
                    period,
                    save=save,
                    use_cache=True,
                )
                predictions.append(prediction)
            except Exception as e:
                logger.error(f"Failed to predict {coin}: {e}")
                
                # Prediction خطا
                predictions.append(Prediction(
                    coin=coin,
                    coin_name=coin,
                    current_price=0,
                    signal="خطا در پیش‌بینی",
                    signal_type=SignalType.ERROR,
                    confidence=0,
                    confidence_score=0,
                    prediction_score=0.0,
                    period=period,
                    model_mode="ERROR",
                    timestamp=datetime.now(),
                    processing_time_ms=0,
                    data_points=0,
                    extra={"error": str(e)},
                ))
        
        return predictions
    
    # ============================================================
    # Demo Predict (بهبود)
    # ============================================================
    
    def _demo_predict(self, features: np.ndarray) -> float:
        """
        شبیه‌سازی پیش‌بینی در حالت DEMO
        
        بهبود:
            - استفاده از weights بهتر
            - منطق منطقی‌تر
            - نویز کمتر
        """
        base_score = 0.5
        
        # بازده‌ها (weight بیشتر)
        if len(features) >= 4:
            returns_avg = float(np.mean(features[:4]))
            # بازده مثبت → boost
            base_score += returns_avg * 1.5
        
        # روند
        if len(features) >= 10:
            trend_strength = float(features[9])
            base_score += trend_strength * 0.3
        
        # ترس و طمع (contrarian)
        if len(features) >= 8:
            fear = float(features[7])
            if fear < 0.25:  # ترس شدید → buy
                base_score += 0.20
            elif fear < 0.40:
                base_score += 0.10
            elif fear > 0.75:  # طمع شدید → sell
                base_score -= 0.20
            elif fear > 0.60:
                base_score -= 0.10
        
        # R² (قدرت روند)
        if len(features) >= 12:
            r2 = float(features[12])
            if r2 > 0.5:  # روند قوی
                base_score += 0.05
            elif r2 < -0.5:
                base_score -= 0.05
        
        # نویز کم
        noise = float(np.random.randn() * 0.03)
        
        return float(np.clip(base_score + noise, 0, 1))
    
    # ============================================================
    # Helpers
    # ============================================================
    
    def _dict_to_prediction(self, data: Dict[str, Any]) -> Prediction:
        """تبدیل dict به Prediction"""
        signal_type_str = data.get("signal_type", "NEUTRAL")
        try:
            signal_type = SignalType(signal_type_str)
        except ValueError:
            signal_type = SignalType.NEUTRAL
        
        return Prediction(
            coin=data.get("coin", ""),
            coin_name=data.get("coin_name", ""),
            current_price=float(data.get("current_price", 0)),
            signal=data.get("signal", ""),
            signal_type=signal_type,
            confidence=int(data.get("confidence", 50)),
            confidence_score=int(data.get("confidence_score", 50)),
            prediction_score=float(data.get("prediction_score", 0.5)),
            period=data.get("period", "24h"),
            model_mode=data.get("model_mode", "DEMO"),
            timestamp=datetime.fromisoformat(
                data.get("timestamp", datetime.now().isoformat())
            ),
            processing_time_ms=float(data.get("processing_time_ms", 0)),
            data_points=int(data.get("data_points", 0)),
            extra=data.get("extra"),
        )
