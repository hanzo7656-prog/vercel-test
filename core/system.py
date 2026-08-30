# core/system.py
# ============================================================
# فقط بخش Import - نسخه اصلاح شده
# ============================================================

import os
import sys
import time
import json
import logging
import numpy as np
import xgboost as xgb
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple, Union
from pathlib import Path

# ✅ اصلاح Import - استفاده از مسیر جدید
from infrastructure.api.coinstats_client import coinstats_client
from infrastructure.api.cache_manager import cache_manager
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer
from core.feature_engineering import feature_engineer
from core.threading_manager import threading_manager
from infrastructure.database import get_cache, health_check as db_health_check
from infrastructure.database.database_factory import ensure_databases_connected
from config import get_config, get_model_config, get_system_config, get_thresholds, get_auto_trainer_config
from config.version import VERSION

logger = logging.getLogger(__name__)

# ============================================================
# کش پیش‌بینی - حذف شده (استفاده از Redis)
# ============================================================


class TradingSignalSystem:
    """
    سیستم تشخیص الگوی بازاری
    شامل: دریافت داده → مهندسی ویژگی‌ها → پیش‌بینی با XGBoost
    
    ✅ نسخه ۸.۰: حذف print، استفاده از logger، Type Hints کامل
    """
    
    _instance = None
    
    def __new__(cls) -> 'TradingSignalSystem':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        """راه‌اندازی سیستم با کلید API"""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.start_time: datetime = datetime.now()
        
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
        
        # تنظیمات
        self.config: Dict[str, Any] = {
            "thresholds": get_thresholds(),
            "model": get_model_config(),
            "system": get_system_config(),
            "cache_ttl": get_config("cache.default_ttl", 3600)
        }

        # بارگذاری مدل با ModelManager
        self._init_model()
        
        # کش برای داده‌های خودکار
        self._cached_coins: Optional[Any] = None
        self._cached_news: Optional[Any] = None
        self._cached_fear_greed: Optional[Any] = None
        self._cached_market: Optional[Any] = None

        # ============================================================
        # ✅ AutoTrainer - غیرفعال در Startup (برای کاهش مصرف API)
        # ============================================================
        self.trainer = AutoTrainer(self.api, self.model_manager)
        
        # ✅ فقط تنظیمات را اعمال کن
        auto_config: Dict[str, Any] = get_auto_trainer_config()
        if auto_config.get("enabled", False):
            interval: int = auto_config.get("interval_hours", 6)
            period: str = auto_config.get("period", "1m")
            self.trainer.start_auto_train(interval_hours=interval, period=period)
            logger.info(f"✅ AutoTrainer started: every {interval}h, period: {period}")
        else:
            logger.info("🛑 AutoTrainer is DISABLED on startup to save API credits.")
            logger.info("📌 Use POST /model/train to train manually.")
            logger.info("📌 Use POST /model/start to enable auto-train.")

        # دیتابیس‌ها
        self.db_healthy: bool = False
        self._ensure_database_health()
        
        self.db = get_cache()
        if self.db and self.db.is_connected():
            logger.info("✅ اتصال به دیتابیس برقرار شد")
        else:
            logger.warning("⚠️ دیتابیس در دسترس نیست")
        
        # ثبت در Scheduler
        self._register_with_scheduler()
        
        logger.info(f"✅ TradingSignalSystem v{VERSION} initialized")

    def _register_with_scheduler(self) -> None:
        """ثبت در Scheduler"""
        try:
            from core.metrics import metrics_scheduler
            logger.info("✅ TradingSignalSystem registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")

    def _init_model(self) -> None:
        """راه‌اندازی مدل با ModelManager"""
        try:
            if self.model_manager.current_model is not None:
                logger.info("✅ مدل با موفقیت بارگذاری شد")
                logger.info(f"📊 نسخه مدل: {self.model_manager.current_version}")
            else:
                logger.warning("⚠️ مدلی یافت نشد - استفاده از حالت DEMO")
        except Exception as e:
            logger.warning(f"⚠️ خطا در بارگذاری مدل: {e}")

    def _ensure_database_health(self) -> Dict[str, Any]:
        """بررسی و اطمینان از سلامت اتصال دیتابیس‌ها"""
        try:
            result: Dict[str, Any] = ensure_databases_connected()
            self.db_healthy = result.get("primary", False)
            if not self.db_healthy:
                logger.warning("⚠️ دیتابیس اصلی در دسترس نیست، برخی قابلیت‌ها محدود خواهند شد")
            return result
        except Exception as e:
            logger.error(f"❌ خطا در بررسی سلامت دیتابیس: {e}")
            self.db_healthy = False
            return {"error": str(e)}
            
    def cache_get(self, key: str) -> Optional[Any]:
        """دریافت از کش (با دیتابیس)"""
        if self.db and self.db.is_connected():
            return self.db.get(key)
        return None
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """ذخیره در کش (با دیتابیس)"""
        if self.db and self.db.is_connected():
            return self.db.set(key, value, ttl)
        return False

    def extract_features(self, chart_data: List[List]) -> Optional[np.ndarray]:
        """
        تبدیل داده‌های خام قیمت به ویژگی‌های عددی برای XGBoost
        
        ⚠️ این متد برای سازگاری با کدهای قدیمی نگهداری شده است
        ✅ توصیه می‌شود از feature_engineer.extract_features استفاده کنید
        """
        if not chart_data or len(chart_data) < 30:
            return None

        prices: List[float] = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))

        if len(prices) < 30:
            return None

        prices_arr: np.ndarray = np.array(prices, dtype=np.float32)
        features: List[float] = []

        # 1. بازده‌ها (Returns)
        for lag in [1, 3, 5, 10]:
            if len(prices) > lag:
                ret: float = (prices_arr[-1] - prices_arr[-lag-1]) / (prices_arr[-lag-1] + 1e-8)
                features.append(np.clip(ret, -0.5, 0.5))
            else:
                features.append(0.0)

        # 2. میانگین متحرک ساده (SMA)
        for window in [5, 10, 20]:
            if len(prices) >= window:
                sma: float = np.mean(prices_arr[-window:])
                ratio: float = prices_arr[-1] / (sma + 1e-8) - 1
                features.append(np.clip(ratio, -0.5, 0.5))
            else:
                features.append(0.0)

        # 3. نوسان (Volatility)
        if len(prices) >= 15:
            returns: np.ndarray = np.diff(prices_arr[-15:]) / (prices_arr[-15:-1] + 1e-8)
            volatility: float = np.std(returns)
            features.append(np.clip(volatility, 0, 0.5))
        else:
            features.append(0.0)

        # 4. شاخص ترس و طمع
        try:
            fg: Optional[Dict[str, Any]] = self.api.get_fear_greed(use_cache=True)
            if fg and 'now' in fg:
                fear_value: float = fg['now'].get('value', 50)
                features.append(fear_value / 100.0)
            else:
                features.append(0.5)
        except Exception as e:
            logger.debug(f"Fear & Greed error in extract_features: {e}")
            features.append(0.5)

        # 5. شیب قیمت (روند)
        for window in [5, 10, 20]:
            if len(prices) >= window:
                slope: float = np.polyfit(range(window), prices_arr[-window:], 1)[0]
                slope_norm: float = slope / (prices_arr[-1] + 1e-8) * 100
                features.append(np.clip(slope_norm, -10, 10))
            else:
                features.append(0.0)

        # 6. قدرت روند (R-squared)
        if len(prices) >= 10:
            x: np.ndarray = np.arange(10)
            y: np.ndarray = prices_arr[-10:]
            slope, intercept = np.polyfit(x, y, 1)
            y_pred: np.ndarray = slope * x + intercept
            ss_tot: float = np.sum((y - np.mean(y)) ** 2)
            ss_res: float = np.sum((y - y_pred) ** 2)
            r2: float = 1 - (ss_res / (ss_tot + 1e-8))
            features.append(np.clip(r2, -1, 1))
        else:
            features.append(0.0)

        return np.array(features, dtype=np.float32)

    def _demo_predict(self, features: np.ndarray) -> float:
        """شبیه‌سازی پیش‌بینی در حالت DEMO (بدون مدل واقعی)"""
        base_score: float = 0.5
    
        if len(features) >= 4:
            returns_avg: float = float(np.mean(features[:4]))
            base_score += returns_avg * 1.5
    
        if len(features) >= 10:
            trend_strength: float = float(features[9])
            base_score += trend_strength * 0.3
    
        if len(features) >= 8:
            fear: float = float(features[7])
            if fear < 0.3:
                base_score += 0.15
            elif fear > 0.7:
                base_score -= 0.15
    
        prediction: float = float(np.clip(base_score + np.random.randn() * 0.05, 0, 1))
        return prediction

    def predict_sync(self, coin_id: str = "bitcoin", period: str = "24h") -> Dict[str, Any]:
        """
        نسخه همگام (Synchronous) پیش‌بینی با کش و بهینه‌سازی
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه زمانی (24h, 1w, 1m, 3m, 6m)
        
        خروجی:
            دیکشنری نتیجه پیش‌بینی
        """
        start_time: float = time.time()

        valid_periods: List[str] = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            logger.warning(f"Invalid period requested: {period}")
            return {
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد"
            }

        # ✅ دریافت داده از API (کش در api_handler انجام می‌شود)
        chart_data: Union[List[List], Dict[str, Any]] = self.api.get_chart(coin_id, period)

        if not chart_data or isinstance(chart_data, dict) and "error" in chart_data:
            error_msg: str = chart_data.get("error", "NoData") if isinstance(chart_data, dict) else "NoData"
            logger.error(f"Failed to get chart data for {coin_id}: {error_msg}")
            return {
                "error": "NoData",
                "message": "داده‌ای از API دریافت نشد",
                "coin": coin_id,
                "period": period
            }

        # ✅ استخراج ویژگی با FeatureEngineer یکپارچه
        features: Optional[np.ndarray] = self.feature_engineer.extract_features(chart_data)

        if features is None:
            logger.warning(f"Insufficient data for {coin_id} ({period})")
            return {
                "error": "InsufficientData",
                "message": "داده‌های کافی برای تحلیل وجود ندارد (حداقل ۳۰ نقطه لازم است)",
                "coin": coin_id,
                "period": period,
                "data_points": len(chart_data) if chart_data else 0
            }

        # ✅ پیش‌بینی
        if self.model_manager.current_model:
            try:
                prediction: float = self.model_manager.predict(features)
                prediction = float(prediction)
            except Exception as e:
                logger.error(f"⚠️ خطا در پیش‌بینی با مدل: {e}")
                prediction = self._demo_predict(features)
        else:
            prediction = self._demo_predict(features)
        
        # تفسیر نتیجه
        if prediction >= 0.65:
            signal: str = "🟢 صعودی (الگوی خرید)"
            confidence: int = int(((prediction - 0.5) / 0.5) * 100)
            signal_type: str = "BUY"
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
        coin_info: Optional[Dict[str, Any]] = self.api.get_coin(coin_id)
        current_price: float = coin_info.get('price', 0) if coin_info else 0

        processing_time: float = (time.time() - start_time) * 1000

        result: Dict[str, Any] = {
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

        return result

    def health_check(self) -> Dict[str, Any]:
        """بررسی کامل سلامت سیستم"""
        status: Dict[str, Any] = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }

        # 1. سلامت API
        try:
            api_status: Optional[Dict[str, Any]] = self.api.get_status()
            if api_status and api_status.get('status') == 'ok':
                status["components"]["api"] = {
                    "status": "healthy",
                    "message": "اتصال به API برقرار است"
                }
            else:
                status["components"]["api"] = {
                    "status": "degraded",
                    "message": "API در دسترس نیست"
                }
                status["status"] = "degraded"
        except requests.exceptions.Timeout as e:
            logger.error(f"API health check timeout: {e}")
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": f"خطا در اتصال به API: Timeout"
            }
            status["status"] = "unhealthy"
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API health check connection error: {e}")
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": f"خطا در اتصال به API: Connection Error"
            }
            status["status"] = "unhealthy"
        except Exception as e:
            logger.error(f"API health check error: {e}", exc_info=True)
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": f"خطا در اتصال به API: {str(e)}"
            }
            status["status"] = "unhealthy"

        # 2. سلامت مدل
        model_stats: Dict[str, Any] = self.model_manager.get_stats() if self.model_manager else {}
        model_exists: bool = model_stats.get('loaded', False)
    
        status["components"]["model"] = {
            "status": "healthy" if model_exists else "degraded",
            "message": "مدل بارگذاری شده است" if model_exists else "حالت DEMO (بدون مدل)",
            "mode": "BETA" if model_exists else "DEMO",
            "version": model_stats.get('version', 'unknown'),
            "file_exists": model_exists
        }

        # 3. اعتبار
        try:
            credits: Optional[Dict[str, Any]] = self.api.get_credits()
            if credits and 'remainingCredits' in credits:
                status["components"]["credits"] = {
                    "status": "healthy",
                    "remaining": credits.get('remainingCredits'),
                    "total": credits.get('totalCredits'),
                    "used": credits.get('usedCredits'),
                    "subscription": credits.get('subscription', 'free')
                }
        except Exception as e:
            logger.error(f"Credits check error: {e}")
            status["components"]["credits"] = {
                "status": "unknown",
                "message": f"خطا: {str(e)}"
            }

        # 4. دیتابیس
        try:
            from database import get_primary, get_cache, get_backup
            primary_ok: bool = get_primary() is not None and get_primary().is_connected()
            cache_ok: bool = get_cache() is not None and get_cache().is_connected()
            backup_ok: bool = get_backup() is not None and get_backup().is_connected()
        
            status["components"]["databases"] = {
                "status": "healthy" if (primary_ok and cache_ok and backup_ok) else "degraded",
                "primary": primary_ok,
                "cache": cache_ok,
                "backup": backup_ok
            }
        
            if not primary_ok:
                status["status"] = "degraded"
             
        except ImportError as e:
            logger.error(f"Database import error: {e}")
            status["components"]["databases"] = {
                "status": "unknown",
                "message": "Database module not available"
            }
        except Exception as e:
            logger.error(f"Database health check error: {e}", exc_info=True)
            status["components"]["databases"] = {
                "status": "unknown",
                "message": str(e)
            }
     
        return status


# ============================================================
# ایجاد نمونه Singleton
# ============================================================

system: TradingSignalSystem = TradingSignalSystem()
