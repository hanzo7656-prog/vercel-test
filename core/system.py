# core/system.py
# ============================================================
# هسته اصلی سیستم تشخیص الگوهای بازاری
# ============================================================

import os
import sys
import time
import json
import numpy as np
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from api_handler import CoinStatsAPI
from auto_trainer import AutoTrainer
from model_manager import ModelManager
from database import get_cache, health_check as db_health_check
from database.database_factory import ensure_databases_connected
from config import get_config, get_model_config, get_system_config, get_thresholds

logger = logging.getLogger(__name__)


class TradingSignalSystem:
    """
    سیستم تشخیص الگوی بازاری
    شامل: دریافت داده → مهندسی ویژگی‌ها → پیش‌بینی با XGBoost
    """
    
    def __init__(self, api_key=None):
        """راه‌اندازی سیستم با کلید API"""
        self.api = CoinStatsAPI(api_key)
        self.model_manager = ModelManager(self.api)
        self.start_time = datetime.now()

        self.config = {
            "thresholds": get_thresholds(),
            "model": get_model_config(),
            "system": get_system_config(),
            "cache_ttl": get_config("cache.default_ttl", 3600)
        }

        # بارگذاری مدل با ModelManager
        self._init_model()
        
        # کش برای داده‌های خودکار
        self._cached_coins = None
        self._cached_news = None
        self._cached_fear_greed = None
        self._cached_market = None

        # آموزش خودکار مدل XGBoost
        self.trainer = AutoTrainer(
            self.api, 
            self.model_manager
        )

        interval = get_config("model.auto_train_interval", 6)
        self.trainer.start_auto_train(interval_hours=interval)

        logger.info('AutoTrainer started')

        # دیتابیس‌ها
        self.db_healthy = False
        self._ensure_database_health()
        
        self.db = get_cache()
        if self.db and self.db.is_connected():
            print("✅ اتصال به دیتابیس برقرار شد", file=sys.stderr)
        else:
            print("⚠️ دیتابیس در دسترس نیست", file=sys.stderr)

    def _init_model(self):
        """راه‌اندازی مدل با ModelManager"""
        try:
            if self.model_manager.current_model is not None:
                print("✅ مدل با موفقیت بارگذاری شد", file=sys.stderr)
                print(f"📊 نسخه مدل: {self.model_manager.current_version}", file=sys.stderr)
            else:
                print("⚠️ مدلی یافت نشد - استفاده از حالت DEMO", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری مدل: {e}", file=sys.stderr)

    def _ensure_database_health(self):
        """بررسی و اطمینان از سلامت اتصال دیتابیس‌ها"""
        try:
            result = ensure_databases_connected()
            self.db_healthy = result.get("primary", False)
            if not self.db_healthy:
                logger.warning("⚠️ دیتابیس اصلی در دسترس نیست، برخی قابلیت‌ها محدود خواهند شد")
            return result
        except Exception as e:
            logger.error(f"❌ خطا در بررسی سلامت دیتابیس: {e}")
            self.db_healthy = False
            return {"error": str(e)}
            
    def cache_get(self, key: str):
        """دریافت از کش (با دیتابیس)"""
        if self.db and self.db.is_connected():
            return self.db.get(key)
        return None
    
    def cache_set(self, key: str, value: Any, ttl: int = 3600):
        """ذخیره در کش (با دیتابیس)"""
        if self.db and self.db.is_connected():
            return self.db.set(key, value, ttl)
        return False

    def extract_features(self, chart_data):
        """تبدیل داده‌های خام قیمت به ویژگی‌های عددی برای XGBoost"""
        if not chart_data or len(chart_data) < 30:
            return None

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

        # 4. شاخص ترس و طمع
        try:
            fg = self.api.get_fear_greed(use_cache=True)
            if fg and 'now' in fg:
                fear_value = fg['now'].get('value', 50)
                features.append(fear_value / 100.0)
            else:
                features.append(0.5)
        except:
            features.append(0.5)

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

    def predict_sync(self, coin_id="bitcoin", period="24h"):
        """نسخه همگام (Synchronous) پیش‌بینی با کش و بهینه‌سازی"""
        import xgboost as xgb
        
        start_time = time.time()

        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            return {
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد"
            }

        # کش
        cache_key = f"{coin_id}_{period}"
        from app import prediction_cache, PREDICTION_CACHE_TTL
        if cache_key in prediction_cache:
            cached_data, cached_time = prediction_cache[cache_key]
            if time.time() - cached_time < PREDICTION_CACHE_TTL:
                cached_data["from_cache"] = True
                cached_data["cache_age"] = round(time.time() - cached_time, 1)
                return cached_data

        # دریافت داده
        chart_data = self.api.get_chart(coin_id, period)

        if not chart_data:
            return {
                "error": "NoData",
                "message": "داده‌ای از API دریافت نشد",
                "coin": coin_id,
                "period": period
            }

        if "error" in chart_data:
            return {
                "error": chart_data.get("error"),
                "message": chart_data.get("message", "خطا در دریافت داده"),
                "coin": coin_id,
                "period": period
            }

        # استخراج ویژگی‌ها
        features = self.extract_features(chart_data)

        if features is None:
            return {
                "error": "InsufficientData",
                "message": "داده‌های کافی برای تحلیل وجود ندارد (حداقل ۳۰ نقطه لازم است)",
                "coin": coin_id,
                "period": period,
                "data_points": len(chart_data) if chart_data else 0
            }

        # پیش‌بینی
        if self.model_manager.current_model:
            try:
                prediction = self.model_manager.predict(features)
                prediction = float(prediction)
            except Exception as e:
                print(f"⚠️ خطا در پیش‌بینی با مدل: {e}")
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

        result = {
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

        prediction_cache[cache_key] = (result.copy(), time.time())
        return result

    def _demo_predict(self, features):
        """شبیه‌سازی پیش‌بینی در حالت DEMO (بدون مدل واقعی)"""
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
    
        prediction = np.clip(base_score + np.random.randn() * 0.05, 0, 1)
        return float(prediction)

    def health_check(self):
        """بررسی کامل سلامت سیستم"""
        status = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }

        # 1. سلامت API
        try:
            api_status = self.api.get_status()
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
        except Exception as e:
            status["components"]["api"] = {
                "status": "unhealthy",
                "message": f"خطا در اتصال به API: {str(e)}"
            }
            status["status"] = "unhealthy"

        # 2. سلامت مدل
        model_stats = self.model_manager.get_stats() if self.model_manager else {}
        model_exists = model_stats.get('loaded', False)
    
        status["components"]["model"] = {
            "status": "healthy" if model_exists else "degraded",
            "message": "مدل بارگذاری شده است" if model_exists else "حالت DEMO (بدون مدل)",
            "mode": "BETA" if model_exists else "DEMO",
            "version": model_stats.get('version', 'unknown'),
            "file_exists": model_exists
        }

        # 3. اعتبار
        try:
            credits = self.api.get_credits()
            if credits and 'remainingCredits' in credits:
                status["components"]["credits"] = {
                    "status": "healthy",
                    "remaining": credits.get('remainingCredits'),
                    "total": credits.get('totalCredits'),
                    "used": credits.get('usedCredits'),
                    "subscription": credits.get('subscription', 'free')
                }
        except Exception as e:
            status["components"]["credits"] = {
                "status": "unknown",
                "message": f"خطا: {str(e)}"
            }

        # 4. دیتابیس
        try:
            from database import get_primary, get_cache, get_backup
            primary_ok = get_primary() is not None and get_primary().is_connected()
            cache_ok = get_cache() is not None and get_cache().is_connected()
            backup_ok = get_backup() is not None and get_backup().is_connected()
        
            status["components"]["databases"] = {
                "status": "healthy" if (primary_ok and cache_ok and backup_ok) else "degraded",
                "primary": primary_ok,
                "cache": cache_ok,
                "backup": backup_ok
            }
        
            if not primary_ok:
                status["status"] = "degraded"
             
        except Exception as e:
            status["components"]["databases"] = {
                "status": "unknown",
                "message": str(e)
            }
     
        return status


# ============================================================
# ایجاد نمونه Singleton
# ============================================================

system = TradingSignalSystem()
