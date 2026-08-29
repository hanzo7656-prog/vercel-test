# services/prediction_service.py
# ============================================================
# سرویس پیش‌بینی موازی - نسخه ۱.۰
# ============================================================

import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from core.parallel_processor import parallel_processor, TaskResult
from core.feature_engineering import FeatureEngineer
from api.coinstats_client import coinstats_client
from models.manager.model_manager import ModelManager

logger = logging.getLogger(__name__)


class PredictionService:
    """
    سرویس پیش‌بینی با قابلیت پردازش موازی
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.model_manager = ModelManager(coinstats_client)
        self.feature_engineer = FeatureEngineer(coinstats_client)
        
        # کش پیش‌بینی‌ها
        self._prediction_cache = {}
        self._cache_ttl = 300  # ۵ دقیقه
        
        logger.info("✅ PredictionService initialized")
    
    # ============================================================
    # ۱. پیش‌بینی تک‌ارز
    # ============================================================
    
    def predict_single(
        self,
        coin_id: str,
        period: str = "24h"
    ) -> Dict[str, Any]:
        """پیش‌بینی برای یک ارز"""
        cache_key = f"{coin_id}_{period}"
        
        # بررسی کش
        if cache_key in self._prediction_cache:
            cached_data, cached_time = self._prediction_cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                return cached_data
        
        try:
            # دریافت داده
            chart_data = coinstats_client.get_chart(coin_id, period)
            if not chart_data or "error" in chart_data:
                return {"error": "No data", "coin": coin_id}
            
            # استخراج ویژگی
            features = self.feature_engineer.extract_features(chart_data)
            if features is None:
                return {"error": "Insufficient data", "coin": coin_id}
            
            # پیش‌بینی
            if self.model_manager.current_model:
                prediction = self.model_manager.predict(features)
            else:
                prediction = self._demo_predict(features)
            
            # تفسیر
            result = self._interpret_prediction(prediction, coin_id)
            
            # ذخیره در کش
            self._prediction_cache[cache_key] = (result, time.time())
            
            return result
            
        except Exception as e:
            logger.error(f"Prediction error for {coin_id}: {e}")
            return {"error": str(e), "coin": coin_id}
    
    # ============================================================
    # ۲. پیش‌بینی چندارز (موازی)
    # ============================================================
    
    def predict_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        max_workers: int = 5
    ) -> List[Dict[str, Any]]:
        """
        پیش‌بینی موازی برای چند ارز
        
        پارامترها:
            coins: لیست ارزها
            period: بازه زمانی
            max_workers: تعداد Threadهای همزمان
        
        خروجی:
            لیست نتایج پیش‌بینی
        """
        if not coins:
            return []
        
        def predict_coin(coin: str) -> Dict[str, Any]:
            return self.predict_single(coin, period)
        
        # پردازش موازی
        results = parallel_processor.process_parallel(
            coins,
            predict_coin,
            max_workers=max_workers
        )
        
        # استخراج نتایج
        predictions = []
        for result in results:
            if result.success:
                predictions.append(result.result)
            else:
                predictions.append({
                    "error": result.error,
                    "timestamp": datetime.now().isoformat()
                })
        
        return predictions
    
    # ============================================================
    # ۳. پیش‌بینی Async (غیرمترقبه)
    # ============================================================
    
    async def predict_async(
        self,
        coins: List[str],
        period: str = "24h"
    ) -> List[Dict[str, Any]]:
        """پیش‌بینی غیرمترقبه با asyncio"""
        
        async def predict_coin_async(coin: str) -> Dict[str, Any]:
            # از Thread Pool برای عملیات I/O استفاده می‌کنیم
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.predict_single,
                coin,
                period
            )
        
        # اجرای همزمان همه پیش‌بینی‌ها
        tasks = [predict_coin_async(coin) for coin in coins]
        results = await asyncio.gather(*tasks)
        
        return results
    
    # ============================================================
    # ۴. پیش‌بینی دسته‌ای (Batch)
    # ============================================================
    
    def predict_batch(
        self,
        coins: List[str],
        period: str = "24h",
        batch_size: int = 3
    ) -> List[Dict[str, Any]]:
        """پیش‌بینی دسته‌ای با پردازش Batch"""
        
        def process_batch(batch: List[str]) -> List[Dict[str, Any]]:
            """پردازش یک Batch"""
            results = []
            for coin in batch:
                result = self.predict_single(coin, period)
                results.append(result)
            return results
        
        # پردازش موازی Batchها
        batch_results = parallel_processor.process_batch(
            coins,
            process_batch,
            batch_size=batch_size,
            max_workers=min(3, len(coins))
        )
        
        # استخراج نتایج
        predictions = []
        for result in batch_results:
            if result.success:
                predictions.append(result.result)
            else:
                predictions.append({
                    "error": result.error or "Batch processing failed",
                    "timestamp": datetime.now().isoformat()
                })
        
        return predictions
    
    # ============================================================
    # ۵. به‌روزرسانی کش
    # ============================================================
    
    def clear_cache(self):
        """پاک کردن کش پیش‌بینی"""
        self._prediction_cache.clear()
        logger.info("✅ Prediction cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """دریافت آمار کش"""
        return {
            "size": len(self._prediction_cache),
            "keys": list(self._prediction_cache.keys())[:10],
            "ttl": self._cache_ttl
        }
    
    # ============================================================
    # ۶. توابع کمکی
    # ============================================================
    
    def _demo_predict(self, features) -> float:
        """شبیه‌سازی پیش‌بینی DEMO"""
        import numpy as np
        base_score = 0.5
        
        if len(features) >= 4:
            returns_avg = np.mean(features[:4])
            base_score += returns_avg * 1.5
        
        if len(features) >= 10:
            trend_strength = features[9]
            base_score += trend_strength * 0.3
        
        if len(features) >= 8:
            fear = features[7]
            if fear < 0.3:
                base_score += 0.15
            elif fear > 0.7:
                base_score -= 0.15
        
        return float(np.clip(base_score + np.random.randn() * 0.05, 0, 1))
    
    def _interpret_prediction(self, prediction: float, coin_id: str) -> Dict[str, Any]:
        """تفسیر نتیجه پیش‌بینی"""
        if prediction >= 0.65:
            signal = "🟢 صعودی (الگوی خرید)"
            confidence = int(((prediction - 0.5) / 0.5) * 100)
            signal_type = "BUY"
        elif prediction <= 0.35:
            signal = "🔴 نزولی (الگوی فروش)"
            confidence = int(((0.5 - prediction) / 0.5) * 100)
            signal_type = "SELL"
        else:
            signal = "🟡 خنثی (بدون الگوی مشخص)"
            confidence = 50
            signal_type = "NEUTRAL"
        
        # دریافت قیمت لحظه‌ای
        coin_info = coinstats_client.get_coin(coin_id)
        current_price = coin_info.get('price', 0) if coin_info else 0
        
        return {
            "coin": coin_id,
            "coin_name": coin_info.get('name', coin_id) if coin_info else coin_id,
            "current_price": current_price,
            "signal": signal,
            "signal_type": signal_type,
            "confidence": f"{confidence}%",
            "confidence_score": confidence,
            "prediction_score": float(prediction),
            "timestamp": datetime.now().isoformat(),
            "model_mode": "PRODUCTION" if self.model_manager.current_model else "DEMO"
        }


# نمونه Singleton
prediction_service = PredictionService()
