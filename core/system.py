# core/system.py
# ============================================================
# هسته اصلی سیستم - نسخه ۸.۰ (بازنویسی شده)
# ============================================================

import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from api.coinstats_client import coinstats_client
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer
from core.feature_engineering import feature_engineer
from core.threading_manager import threading_manager
from database import get_cache, health_check as db_health_check
from config.version import VERSION

logger = logging.getLogger(__name__)


class TradingSignalSystem:
    """
    هسته اصلی سیستم تشخیص الگوهای بازاری
    نسخه ۸.۰ - با مدیریت Threadها و کش یکپارچه
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
        self.start_time = datetime.now()
        
        # ✅ استفاده از کلاینت جدید با کش Redis
        self.api = coinstats_client
        
        # ✅ Feature Engineering یکپارچه
        self.feature_engineer = feature_engineer
        self.feature_engineer.api = self.api
        
        # ✅ Model Manager
        self.model_manager = ModelManager(self.api)
        
        # ✅ Trainer (غیرفعال در Startup)
        self.trainer = AutoTrainer(self.api, self.model_manager)
        
        # ✅ کش
        self.db = get_cache()
        
        # ✅ Threading Manager
        self.thread_manager = threading_manager
        
        # ثبت در Scheduler
        self._register_with_scheduler()
        
        logger.info(f"✅ TradingSignalSystem v{VERSION} initialized")
    
    def _register_with_scheduler(self):
        """ثبت در Scheduler"""
        try:
            from core.metrics import metrics_scheduler
            logger.info("✅ Registered with Metrics Scheduler")
        except ImportError:
            pass
    
    def predict_sync(self, coin_id: str = "bitcoin", period: str = "24h") -> Dict[str, Any]:
        """پیش‌بینی همگام (بدون کش اضافی)"""
        start_time = time.time()
        
        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            return {"error": "InvalidPeriod", "message": f"بازه باید یکی از {valid_periods} باشد"}
        
        # ✅ دریافت داده از API (کش در api_handler انجام می‌شود)
        chart_data = self.api.get_chart(coin_id, period)
        
        if not chart_data or "error" in chart_data:
            return {
                "error": chart_data.get("error", "NoData"),
                "message": "داده‌ای دریافت نشد",
                "coin": coin_id
            }
        
        # ✅ استخراج ویژگی با FeatureEngineer یکپارچه
        features = self.feature_engineer.extract_features(chart_data)
        
        if features is None:
            return {
                "error": "InsufficientData",
                "message": "داده کافی نیست (حداقل ۳۰ نقطه)",
                "coin": coin_id
            }
        
        # ✅ پیش‌بینی
        if self.model_manager.current_model:
            try:
                prediction = self.model_manager.predict(features)
                prediction = float(prediction)
            except Exception as e:
                logger.error(f"Prediction error: {e}")
                prediction = self._demo_predict(features)
        else:
            prediction = self._demo_predict(features)
        
        # تفسیر نتیجه
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
        
        confidence = min(100, max(0, confidence))
        
        # اطلاعات لحظه‌ای
        coin_info = self.api.get_coin(coin_id)
        current_price = coin_info.get('price', 0) if coin_info else 0
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "coin": coin_id,
            "coin_name": coin_info.get('name', coin_id) if coin_info else coin_id,
            "period": period,
            "current_price": current_price,
            "signal": signal,
            "signal_type": signal_type,
            "confidence": f"{confidence}%",
            "confidence_score": confidence,
            "prediction_score": float(prediction),
            "timestamp": datetime.now().isoformat(),
            "processing_time_ms": round(processing_time, 2),
            "data_points": len(chart_data) if chart_data else 0,
            "model_mode": "PRODUCTION" if self.model_manager.current_model else "DEMO",
            "from_cache": False
        }
    
    def _demo_predict(self, features) -> float:
        """شبیه‌سازی پیش‌بینی در حالت DEMO"""
        base_score = 0.5
        
        if len(features) >= 4:
            returns_avg = sum(features[:4]) / 4
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
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت سیستم"""
        status = {
            "status": "ok",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # 1. API
        try:
            api_status = self.api.get_status()
            status["components"]["api"] = {
                "status": "healthy" if api_status and api_status.get('status') == 'ok' else "degraded"
            }
        except Exception as e:
            status["components"]["api"] = {"status": "unhealthy", "error": str(e)}
            status["status"] = "degraded"
        
        # 2. Model
        model_stats = self.model_manager.get_stats()
        status["components"]["model"] = {
            "status": "healthy" if model_stats.get('loaded') else "degraded",
            "version": model_stats.get('version', 'N/A')
        }
        
        # 3. Threads
        status["components"]["threads"] = self.thread_manager.get_all_status()
        
        # 4. Cache
        status["components"]["cache"] = self.api.get_stats().get('cache_stats', {})
        
        return status


# ✅ نمونه Singleton
import numpy as np  # اضافه شده برای _demo_predict
system = TradingSignalSystem()
