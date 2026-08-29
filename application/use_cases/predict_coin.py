# application/use_cases/predict_coin.py
# ============================================================
# Use Case: Predict Coin (پیش‌بینی ارز)
# ============================================================

import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from domain.entities.prediction import Prediction, SignalType
from domain.value_objects.signal import Signal
from domain.interfaces.api_client import APIClient
from domain.interfaces.repository import Repository
from core.feature_engineering import FeatureEngineer
from models.manager.model_manager import ModelManager

logger = logging.getLogger(__name__)


class PredictCoinUseCase:
    """
    Use Case پیش‌بینی یک ارز
    
    مسئولیت:
        - دریافت داده‌های قیمت از API
        - استخراج ویژگی‌ها
        - پیش‌بینی با مدل
        - ایجاد Entity Prediction
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        feature_engineer: FeatureEngineer
    ):
        self.api_client = api_client
        self.model_manager = model_manager
        self.feature_engineer = feature_engineer
        
        # اعتبارسنجی بازه‌های زمانی
        self.valid_periods: List[str] = ["24h", "1w", "1m", "3m", "6m"]
        
        logger.info("✅ PredictCoinUseCase initialized")
    
    def execute(self, coin_id: str, period: str = "24h") -> Prediction:
        """
        اجرای Use Case
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه زمانی
        
        خروجی:
            Entity Prediction
        
        استثناها:
            ValueError: اگر بازه زمانی نامعتبر باشد
            RuntimeError: اگر داده‌ها دریافت نشوند
        """
        start_time = time.time()
        
        # 1. اعتبارسنجی بازه زمانی
        if period not in self.valid_periods:
            raise ValueError(f"Invalid period: {period}. Must be one of {self.valid_periods}")
        
        # 2. دریافت داده از API
        chart_data = self.api_client.get_chart(coin_id, period)
        
        if not chart_data or (isinstance(chart_data, dict) and "error" in chart_data):
            error_msg = chart_data.get("error", "No data") if isinstance(chart_data, dict) else "No data"
            logger.error(f"Failed to get chart data for {coin_id}: {error_msg}")
            raise RuntimeError(f"Failed to get chart data: {error_msg}")
        
        # 3. استخراج ویژگی‌ها
        features = self.feature_engineer.extract_features(chart_data)
        
        if features is None:
            raise RuntimeError(f"Insufficient data for {coin_id} (need at least 30 points)")
        
        # 4. پیش‌بینی با مدل
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
        
        # 5. ایجاد Signal از امتیاز
        signal = Signal.from_score(prediction_score)
        
        # 6. دریافت اطلاعات ارز
        coin_info = self.api_client.get_coin(coin_id)
        current_price = coin_info.get('price', 0) if coin_info else 0
        coin_name = coin_info.get('name', coin_id) if coin_info else coin_id
        
        # 7. ایجاد Entity Prediction
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
            data_points=len(chart_data) if chart_data else 0
        )
        
        logger.info(f"✅ Prediction completed for {coin_id}: {signal.type.value} ({signal.confidence}%)")
        
        return prediction
    
    def execute_multiple(self, coins: List[str], period: str = "24h") -> List[Prediction]:
        """
        اجرای پیش‌بینی برای چند ارز
        
        پارامترها:
            coins: لیست شناسه ارزها
            period: بازه زمانی
        
        خروجی:
            لیست Entities Prediction
        """
        predictions: List[Prediction] = []
        
        for coin in coins:
            try:
                prediction = self.execute(coin, period)
                predictions.append(prediction)
            except Exception as e:
                logger.error(f"Failed to predict {coin}: {e}")
                # ایجاد Prediction خطا
                predictions.append(
                    Prediction(
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
                        extra={"error": str(e)}
                    )
                )
        
        return predictions
    
    def _demo_predict(self, features) -> float:
        """شبیه‌سازی پیش‌بینی در حالت DEMO"""
        import numpy as np
        
        base_score = 0.5
        
        if len(features) >= 4:
            returns_avg = float(np.mean(features[:4]))
            base_score += returns_avg * 1.5
        
        if len(features) >= 10:
            trend_strength = float(features[9])
            base_score += trend_strength * 0.3
        
        if len(features) >= 8:
            fear = float(features[7])
            if fear < 0.3:
                base_score += 0.15
            elif fear > 0.7:
                base_score -= 0.15
        
        return float(np.clip(base_score + np.random.randn() * 0.05, 0, 1))
