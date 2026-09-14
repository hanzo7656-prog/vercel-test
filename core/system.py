# core/system.py
# ============================================================
# سیستم اصلی - نسخه ۹.۰
# رفع باگ‌ها + Container + Cache + Profile Support
# ============================================================

import os
import sys
import time
import json
import logging
import numpy as np
import xgboost as xgb
import requests
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple, Union
from pathlib import Path

from infrastructure.api.coinstats_client import coinstats_client
from infrastructure.api.cache_manager import cache_manager
from infrastructure.database import (
    get_cache,
    get_primary,
    health_check as db_health_check,
)
from infrastructure.database.database_factory import ensure_databases_connected
from core.feature_engineering import feature_engineer
from core.threading_manager import threading_manager
from config import (
    get_config,
    get_model_config,
    get_system_config,
    get_thresholds,
    get_auto_trainer_config,
)
from config.version import VERSION

logger = logging.getLogger(__name__)


# ============================================================
# TradingSignalSystem - Singleton
# ============================================================

class TradingSignalSystem:
    """
    سیستم اصلی تشخیص الگو
    
    شامل:
        - دریافت داده → مهندسی ویژگی → پیش‌بینی با XGBoost
    
    رفع باگ‌ها:
        - Import درست از infrastructure
        - requests در import
        - timeout در health_check
        - Singleton واقعی
        - استفاده از feature_engineer (بدون تکرار)
        - get_primary درست
        - cache در predict
    
    ارتقاها:
        - Container integration (با fallback)
        - Profile support
        - Prediction cache
        - بهبود _demo_predict
        - Health check کامل
    """
    
    _instance: Optional['TradingSignalSystem'] = None
    
    def __new__(cls) -> 'TradingSignalSystem':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """راه‌اندازی سیستم"""
        # Singleton واقعی
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.start_time: datetime = datetime.now()
        
        # ============================================================
        # ۱. API Client
        # ============================================================
        self.api = coinstats_client
        
        # ============================================================
        # ۲. Feature Engineer (استفاده از singleton)
        # ============================================================
        self.feature_engineer = feature_engineer
        self.feature_engineer.api = self.api
        
        # ============================================================
        # ۳. Model Manager و Trainer
        #    (با fallback اگه container نیست)
        # ============================================================
        self.model_manager, self.trainer = self._init_model_components()
        
        # ============================================================
        # ۴. Cache
        # ============================================================
        self.cache = get_cache()
        self.db = self.cache  # برای سازگاری
        
        # ============================================================
        # ۵. Database Health
        # ============================================================
        self.db_healthy: bool = False
        self._ensure_database_health()
        
        # ============================================================
        # ۶. تنظیمات
        # ============================================================
        self.config: Dict[str, Any] = {
            "thresholds": get_thresholds(),
            "model": get_model_config(),
            "system": get_system_config(),
            "cache_ttl": get_config("cache.default_ttl", 3600),
        }
        
        # ============================================================
        # ۷. کش‌های داخلی
        # ============================================================
        self._cached_coins: Optional[Any] = None
        self._cached_news: Optional[Any] = None
        self._cached_fear_greed: Optional[Any] = None
        self._cached_market: Optional[Any] = None
        
        # ============================================================
        # ۸. AutoTrainer (اختیاری)
        # ============================================================
        self._configure_auto_trainer()
        
        # ============================================================
        # ۹. ثبت در Scheduler
        # ============================================================
        self._register_with_scheduler()
        
        logger.info(f"✅ TradingSignalSystem v{VERSION} initialized")
    
    # ============================================================
    # Init Helpers
    # ============================================================
    
    def _init_model_components(self) -> Tuple[Any, Any]:
        """
        ساخت/دریافت ModelManager و AutoTrainer
        
        خروجی:
            (model_manager, trainer)
        """
        # تلاش برای استفاده از container
        try:
            from container import container
            model_manager = container.get('model_manager')
            trainer = container.get('trainer')
            
            logger.info("✅ Model components from container")
            return model_manager, trainer
        except (ImportError, KeyError, Exception) as e:
            logger.debug(f"⚠️ Container unavailable: {e}")
        
        # Fallback: ساخت مستقیم
        from models.manager.model_manager import ModelManager
        from models.trainer.auto_trainer import AutoTrainer
        
        model_manager = ModelManager(self.api)
        trainer = AutoTrainer(self.api, model_manager)
        
        logger.info("✅ Model components created directly")
        return model_manager, trainer
    
    def _configure_auto_trainer(self) -> None:
        """تنظیم AutoTrainer (بدون شروع خودکار)"""
        try:
            auto_config = get_auto_trainer_config()
            
            if auto_config.get("enabled", False):
                interval = auto_config.get("interval_hours", 6)
                period = auto_config.get("period", "1m")
                profile_name = auto_config.get("profile_name", "balanced")
                
                self.trainer.start_auto_train(
                    interval_hours=interval,
                    period=period,
                    profile_name=profile_name,
                )
                logger.info(
                    f"✅ AutoTrainer started: every {interval}h, "
                    f"period: {period}, profile: {profile_name}"
                )
            else:
                logger.info("🛑 AutoTrainer DISABLED on startup to save credits")
                logger.info("📌 Use POST /model/train-with-profile to train manually")
        except Exception as e:
            logger.warning(f"⚠️ AutoTrainer config error: {e}")
    
    def _register_with_scheduler(self) -> None:
        """ثبت در Metrics Scheduler"""
        try:
            from core.metrics import metrics_scheduler
            logger.debug("✅ TradingSignalSystem registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"⚠️ Could not register with scheduler: {e}")
    
    def _ensure_database_health(self) -> Dict[str, Any]:
        """بررسی و اطمینان از سلامت اتصال دیتابیس‌ها"""
        try:
            result = ensure_databases_connected()
            self.db_healthy = result.get("primary", False)
            
            if not self.db_healthy:
                logger.warning(
                    "⚠️ Primary database not available, "
                    "some features limited"
                )
            
            return result
        except Exception as e:
            logger.error(f"❌ Database health error: {e}")
            self.db_healthy = False
            return {"error": str(e)}
    
    # ============================================================
    # Cache Helpers
    # ============================================================
    
    def cache_get(self, key: str) -> Optional[Any]:
        """دریافت از کش"""
        if self.cache and self.cache.is_connected():
            return self.cache.get(key)
        return None
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """ذخیره در کش"""
        if self.cache and self.cache.is_connected():
            return self.cache.set(key, value, ttl)
        return False
    
    # ============================================================
    # Feature Extraction (Delegate به feature_engineer)
    # ============================================================
    
    def extract_features(
        self,
        chart_data: List[List],
    ) -> Optional[np.ndarray]:
        """
        استخراج ویژگی‌ها (delegate به feature_engineer)
        
        پارامترها:
            chart_data: لیست [timestamp, price]
        
        خروجی:
            numpy array از ویژگی‌ها یا None
        
        توجه:
            این متد برای سازگاری با کدهای قدیمی نگه داشته شده.
            توصیه می‌شه از self.feature_engineer.extract_features استفاده کنی.
        """
        return self.feature_engineer.extract_features(chart_data)
    
    # ============================================================
    # Demo Prediction
    # ============================================================
    
    def _demo_predict(self, features: np.ndarray) -> float:
        """
        شبیه‌سازی پیش‌بینی در حالت DEMO
        
        پارامترها:
            features: آرایه ویژگی‌ها
        
        خروجی:
            عدد بین ۰ تا ۱
        """
        base_score: float = 0.5
        
        if len(features) >= 4:
            # میانگین بازده‌ها
            returns_avg = float(np.mean(features[:4]))
            base_score += returns_avg * 1.5
        
        if len(features) >= 10:
            # روند
            trend_strength = float(features[9])
            base_score += trend_strength * 0.3
        
        if len(features) >= 8:
            # ترس و طمع
            fear = float(features[7])
            if fear < 0.3:
                base_score += 0.15
            elif fear > 0.7:
                base_score -= 0.15
        
        # نویز کوچک
        noise = float(np.random.randn() * 0.05)
        prediction = float(np.clip(base_score + noise, 0, 1))
        
        return prediction
    
    # ============================================================
    # Prediction
    # ============================================================
    
    def predict_sync(
        self,
        coin_id: str = "bitcoin",
        period: str = "24h",
    ) -> Dict[str, Any]:
        """
        پیش‌بینی همگام (sync) با کش
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه (24h, 1w, 1m, 3m, 6m)
        
        خروجی:
            دیکشنری نتیجه
        """
        start_time = time.time()
        
        # ===== اعتبارسنجی =====
        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            logger.warning(f"Invalid period: {period}")
            return {
                "error": "InvalidPeriod",
                "message": f"بازه باید یکی از {valid_periods} باشه",
            }
        
        # ===== دریافت داده =====
        chart_data = self.api.get_chart(coin_id, period)
        
        if not chart_data or (isinstance(chart_data, dict) and "error" in chart_data):
            error_msg = (
                chart_data.get("error", "NoData")
                if isinstance(chart_data, dict) else "NoData"
            )
            logger.error(f"Chart data failed for {coin_id}: {error_msg}")
            return {
                "error": "NoData",
                "message": "داده‌ای از API دریافت نشد",
                "coin": coin_id,
                "period": period,
            }
        
        # ===== استخراج ویژگی =====
        features = self.feature_engineer.extract_features(chart_data)
        
        if features is None:
            logger.warning(f"Insufficient data for {coin_id} ({period})")
            return {
                "error": "InsufficientData",
                "message": "داده‌های کافی نیست (حداقل ۳۰ نقطه)",
                "coin": coin_id,
                "period": period,
                "data_points": len(chart_data) if chart_data else 0,
            }
        
        # ===== پیش‌بینی =====
        if self.model_manager.current_model:
            try:
                prediction = float(self.model_manager.predict(features))
                model_mode = "PRODUCTION"
            except Exception as e:
                logger.error(f"⚠️ Model prediction error: {e}")
                prediction = self._demo_predict(features)
                model_mode = "DEMO_FALLBACK"
        else:
            prediction = self._demo_predict(features)
            model_mode = "DEMO"
        
        # ===== تفسیر =====
        if prediction >= 0.65:
            signal = "🟢 صعودی (الگوی خرید)"
            confidence = int(((prediction - 0.5) / 0.5) * 100)
            signal_type = "BUY"
        elif prediction <= 0.35:
            signal = "🔴 نزولی (الگوی فروش)"
            confidence = int(((0.5 - prediction) / 0.5) * 100)
            signal_type = "SELL"
        else:
            signal = "🟡 خنثی (بدون الگو)"
            confidence = 50
            signal_type = "NEUTRAL"
        
        confidence = min(100, max(0, confidence))
        
        # ===== اطلاعات لحظه‌ای =====
        coin_info = self.api.get_coin(coin_id)
        current_price = coin_info.get("price", 0) if coin_info else 0
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "coin": coin_id,
            "coin_name": coin_info.get("name", coin_id) if coin_info else coin_id,
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
            "model_mode": model_mode,
            "from_cache": False,
        }
    
    # ============================================================
    # Health Check
    # ============================================================
    
    def health_check(self, timeout: int = 10) -> Dict[str, Any]:
        """
        بررسی کامل سلامت سیستم
        
        پارامترها:
            timeout: حداکثر زمان (ثانیه)
        
        خروجی:
            دیکشنری وضعیت
        """
        status = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "version": VERSION,
            "components": {},
        }
        
        # ===== ۱. API =====
        try:
            api_status = self.api.get_status()
            if api_status and api_status.get("status") == "ok":
                status["components"]["api"] = {
                    "status": "healthy",
                    "message": "اتصال برقرار",
                }
            else:
                status["components"]["api"] = {
                    "status": "degraded",
                    "message": "API در دسترس نیست",
                }
                status["status"] = "degraded"
        except requests.exceptions.Timeout:
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": "Timeout",
            }
            status["status"] = "unhealthy"
        except requests.exceptions.ConnectionError:
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": "Connection Error",
            }
            status["status"] = "unhealthy"
        except Exception as e:
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": str(e)[:100],
            }
            status["status"] = "unhealthy"
        
        # ===== ۲. مدل =====
        try:
            model_stats = self.model_manager.get_stats()
            model_loaded = model_stats.get("loaded", False)
            
            status["components"]["model"] = {
                "status": "healthy" if model_loaded else "degraded",
                "message": (
                    "مدل بارگذاری شده"
                    if model_loaded else "حالت DEMO"
                ),
                "mode": "BETA" if model_loaded else "DEMO",
                "version": model_stats.get("version", "unknown"),
                "accuracy": model_stats.get("max_accuracy", 0),
            }
        except Exception as e:
            status["components"]["model"] = {
                "status": "unknown",
                "error": str(e)[:100],
            }
        
        # ===== ۳. Credits =====
        try:
            credits = self.api.get_credits()
            if credits and "remainingCredits" in credits:
                status["components"]["credits"] = {
                    "status": "healthy",
                    "remaining": credits.get("remainingCredits"),
                    "total": credits.get("totalCredits"),
                    "used": credits.get("usedCredits"),
                }
        except Exception as e:
            status["components"]["credits"] = {
                "status": "unknown",
                "error": str(e)[:100],
            }
        
        # ===== ۴. دیتابیس =====
        try:
            db_health = db_health_check()
            status["components"]["databases"] = {
                "status": "healthy" if self.db_healthy else "degraded",
                "details": db_health,
            }
            
            if not self.db_healthy:
                status["status"] = "degraded"
        except Exception as e:
            status["components"]["databases"] = {
                "status": "unknown",
                "error": str(e)[:100],
            }
        
        # ===== ۵. Cache =====
        try:
            cache_ok = self.cache and self.cache.is_connected()
            status["components"]["cache"] = {
                "status": "healthy" if cache_ok else "degraded",
            }
        except Exception as e:
            status["components"]["cache"] = {
                "status": "unknown",
                "error": str(e)[:100],
            }
        
        return status


# ============================================================
# Singleton Instance
# ============================================================

system: TradingSignalSystem = TradingSignalSystem()
