# app.py
# ============================================================
# هسته اصلی سیستم تشخیص الگوهای بازاری
# شامل: سیستم، مدیریت تسک‌ها، روت‌های بازار
# نسخه ۶.۰ - با ModelManager و دیتابیس جدید
# ============================================================

import os
import sys
import json
import time
import uuid
import threading
import numpy as np
import logging
import subprocess
import io
from typing import Any
from datetime import datetime, timedelta
from queue import Queue
from flask import Flask, jsonify, request, redirect, send_from_directory
from api_handler import CoinStatsAPI
from auto_trainer import AutoTrainer
from database import get_cache, health_check as db_health_check
from config import (
    get_config,
    get_model_config,
    get_system_config,
    get_thresholds
)
from auth_manager import get_auth, require_auth, get_current_user_from_request
from model_manager import ModelManager
import secrets
from numeric_analyzer import NumericAnalyzer
from command_system import CommandSystem
from database.database_factory import ensure_databases_connected
from database import get_db, get_db_for, get_cache, get_primary, get_backup, health_check


# ============================================================
# هسته اصلی سیستم
# ============================================================

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

        logger = logging.getLogger(__name__)
        logger.info('AutoTrainer started')

        # دیتابیس‌ها

        sel.db_healthy = False
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


    # در کلاس TradingSignalSystem، بعد از __init__ اضافه کنید
    def _ensure_database_health(self):
        """
        بررسی و اطمینان از سلامت اتصال دیتابیس‌ها
        این تابع در زمان راه‌اندازی و به صورت دوره‌ای صدا زده می‌شود
        """
        try:
            result = ensure_databases_connected()
        
            # به‌روزرسانی وضعیت دیتابیس در سیستم
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

    def _get_memory_usage(self):
        """دریافت دقیق حافظه مصرفی پروسه فعلی"""
        try:
            if os.path.exists('/proc/self/status'):
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            parts = line.split()
                            if len(parts) >= 2:
                                used_kb = int(parts[1])
                                used_mb = used_kb / 1024
                                return used_mb, 512
        except:
            pass
        return 0, 512

    def extract_features(self, chart_data):
        """
        تبدیل داده‌های خام قیمت به ویژگی‌های عددی برای XGBoost
        
        ورودی: لیست [[timestamp, priceUSD, priceBTC, priceETH], ...]
        خروجی: آرایه numpy از ویژگی‌ها
        """
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
        """
        نسخه همگام (Synchronous) پیش‌بینی
      
        این تابع داده‌ها رو از API دریافت میکنه، ویژگی‌ها رو استخراج میکنه
        و با مدل XGBoost (یا حالت DEMO) پیش‌بینی رو انجام میده.
    
        پارامترها:
            coin_id: شناسه ارز (مثال: bitcoin, ethereum)
            period: بازه زمانی (24h, 1w, 1m, 3m, 6m)
    
        خروجی:
            دیکشنری شامل: سیگنال، اطمینان، قیمت فعلی و اطلاعات تکمیلی
        """
        import xgboost as xgb
        xgb.set_config({"save_format": "json"})
        start_time = time.time()

        # اعتبارسنجی بازه زمانی
        valid_periods = ["24h", "1w", "1m", "3m", "6m"]
        if period not in valid_periods:
            return {
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد"
            }

        # 1. دریافت داده‌های تاریخی
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

        # 2. استخراج ویژگی‌ها
        features = self.extract_features(chart_data)

        if features is None:
            return {
                "error": "InsufficientData",
                "message": "داده‌های کافی برای تحلیل وجود ندارد (حداقل ۳۰ نقطه لازم است)",
                "coin": coin_id,
                "period": period,
                "data_points": len(chart_data) if chart_data else 0
            }

        # 3. پیش‌بینی با مدل جدید (ModelManager)
        if self.model_manager.current_model:
            try:
                prediction = self.model_manager.predict(features)
                prediction = float(prediction)
            except Exception as e:
                print(f"⚠️ خطا در پیش‌بینی با مدل: {e}")
                prediction = self._demo_predict(features)
        else:
            prediction = self._demo_predict(features)

        # 4. تفسیر نتیجه
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

        # 5. دریافت اطلاعات لحظه‌ای
        coin_info = self.api.get_coin(coin_id)
        current_price = coin_info.get('price', 0) if coin_info else 0

        # 6. اطلاعات تکمیلی
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
            "model_mode": "PRODUCTION" if self.model_manager.current_model else "DEMO"
        }

    def _demo_predict(self, features):
        """
        شبیه‌سازی پیش‌بینی در حالت DEMO (بدون مدل واقعی)
        """
        import numpy as np
    
        base_score = 0.5
    
        # تأثیر بازده‌ها
        if len(features) >= 4:
            returns_avg = np.mean(features[:4])
            base_score += returns_avg * 1.5
    
        # تأثیر روند
        if len(features) >= 10:
            trend_strength = features[9]  # شیب ۲۰ قدمی
            base_score += trend_strength * 0.3
    
        # تأثیر ترس و طمع
        if len(features) >= 8:
            fear = features[7]  # 0-1
            if fear < 0.3:  # ترس شدید → احتمال برگشت
                base_score += 0.15
            elif fear > 0.7:  # طمع شدید → احتمال ریزش
                base_score -= 0.15
    
        # اضافه کردن نویز تصادفی برای شبیه‌سازی
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

        # 2. سلامت مدل (با ModelManager)
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

        # 4. حافظه
        try:
            used_mb, total_mb = self._get_memory_usage()
            if total_mb == 0 or total_mb > 10000:
                total_mb = 512
            memory_percent = (used_mb / total_mb) * 100 if total_mb > 0 else 0

            status["components"]["memory"] = {
                "status": "healthy" if memory_percent < 80 else "warning",
                "used_mb": round(used_mb, 1),
                "total_mb": round(total_mb, 1),
                "percent": round(memory_percent, 1)
            }

            if memory_percent > 90:
                status["status"] = "critical"
            elif memory_percent > 80 and status["status"] == "ok":
                status["status"] = "degraded"

        except Exception as e:
            status["components"]["memory"] = {
                "status": "unknown",
                "message": f"خطا: {str(e)}"
            }

        # 5. آمار API
        status["components"]["api_stats"] = self.api.get_stats()
        
        return status

    # 6. سلامت دیتابیس (اضافه کنید)
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
# راه‌اندازی وب سرویس Flask
# ============================================================

app = Flask(__name__)
system = TradingSignalSystem()
numeric_analyzer = NumericAnalyzer(system.api, system.model_manager)
command_system = CommandSystem(numeric_analyzer)

# ============================================================
# روت‌های API (هسته اصلی)
# ============================================================

@app.route('/predict', methods=['GET'])
def predict():
    """
    پیش‌بینی الگو با Background Task (سریع - بدون Timeout)
    
    پارامترهای Query:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h) - مقادیر: 24h, 1w, 1m, 3m, 6m
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    
    valid_periods = ["24h", "1w", "1m", "3m", "6m"]
    if period not in valid_periods:
        return jsonify({
            "error": "InvalidPeriod",
            "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
            "provided": period
        }), 400
    
    result = system.predict_async(coin, period)
    return jsonify(result), 202


@app.route('/predict-sync', methods=['GET'])
def predict_sync():
    """
    پیش‌بینی الگو به صورت همگام (ممکنه Timeout بخوره)
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    
    valid_periods = ["24h", "1w", "1m", "3m", "6m"]
    if period not in valid_periods:
        return jsonify({
            "error": "InvalidPeriod",
            "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
            "provided": period
        }), 400
    
    result = system.predict_sync(coin, period)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route('/task-status', methods=['GET'])
def task_status():
    """
    بررسی وضعیت یک تسک پس‌زمینه
    
    پارامترهای Query:
        task_id: شناسه تسک (دریافت شده از /predict)
    """
    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({
            "error": "MissingTaskId",
            "message": "پارامتر task_id الزامی است"
        }), 400
    
    result = system.task_manager.get_result(task_id)
    if not result:
        return jsonify({
            "error": "TaskNotFound",
            "message": "تسک با این شناسه وجود ندارد یا منقضی شده است",
            "task_id": task_id
        }), 404
    
    return jsonify(result)


@app.route('/test-api', methods=['GET'])
def test_api():
    """
    تست ارتباط با API و نمایش داده‌های خام
    
    پارامترهای Query:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h)
        type: نوع داده (chart, coin, fear_greed, btc_dominance, market, coins, news, status, credits)
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    data_type = request.args.get('type', 'chart')
    
    valid_types = ['chart', 'coin', 'fear_greed', 'btc_dominance', 'market', 'coins', 'news', 'status', 'credits']
    if data_type not in valid_types:
        return jsonify({
            "error": "InvalidType",
            "message": f"نوع داده باید یکی از {valid_types} باشد",
            "provided": data_type
        }), 400
    
    try:
        if data_type == 'chart':
            data = system.api.get_chart(coin, period)
            if data and "error" not in data:
                return jsonify({
                    "success": True,
                    "count": len(data),
                    "sample": data[:5] if len(data) > 5 else data,
                    "first_point": data[0] if data else None,
                    "last_point": data[-1] if data else None,
                    "data_type": "list_of_arrays",
                    "point_format": "[timestamp, priceUSD, priceBTC, priceETH]"
                })
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'coin':
            data = system.api.get_coin(coin)
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'fear_greed':
            data = system.api.get_fear_greed(use_cache=False)
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'btc_dominance':
            data = system.api.get_btc_dominance(period, use_cache=False)
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'market':
            data = system.api.get_global_market()
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'coins':
            limit = int(request.args.get('limit', 20))
            data = system.api.get_coins_list(limit=limit)
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400
            
        elif data_type == 'news':
            limit = int(request.args.get('limit', 6))
            data = system.api.get_news(limit=limit)
            if data and "error" not in data:
                return jsonify({"success": True, "data": data})
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}), 400

        elif data_type == 'status':
            data = system.api.get_status()
            return jsonify({"success": True, "data": data})

        elif data_type == 'credits':
            data = system.api.get_credits()
            if data and "error" not in data:
                return jsonify({
                    "success": True,
                    "data": {
                        "totalCredits": data.get('totalCredits'),
                        "usedCredits": data.get('usedCredits'),
                        "remainingCredits": data.get('remainingCredits'),
                        "subscription": data.get('subscription', 'free')
                    }
                })
            return jsonify({"success": False, "error": data.get("message", "خطا در دریافت اعتبار") if data else "داده‌ای دریافت نشد"}), 400
            
    except Exception as e:
        import logging
        logging.error(f"Error in test-api: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# روت‌های مدل و آموزش
# ============================================================

@app.route('/model/status', methods=['GET'])
def model_status():
    """دریافت وضعیت مدل و آموزش"""
    try:
        status = system.trainer.get_stats()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/model/train', methods=['POST'])
def model_train():
    """اجرای دستی آموزش"""
    try:
        period = request.args.get('period', '1m')
        result = system.trainer.train_model(period=period)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/start', methods=['POST'])
def model_start():
    """شروع آموزش خودکار"""
    try:
        interval = int(request.args.get('interval', 6))
        period = request.args.get('period', '1m')
        result = system.trainer.start_auto_train(interval_hours=interval, period=period)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/stop', methods=['POST'])
def model_stop():
    """متوقف کردن آموزش خودکار"""
    try:
        result = system.trainer.stop_auto_train()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/check-api', methods=['GET'])
def model_check_api():
    """بررسی وضعیت API و اعتبار"""
    try:
        status = system.trainer.check_api_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/model/history', methods=['GET'])
def model_history():
    """دریافت سابقه آموزش با فیلتر دوره"""
    try:
        period = request.args.get('period', None)
        history = system.trainer.get_training_history(period)
        return jsonify({
            "success": True,
            "data": history,
            "count": len(history),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/clear-logs', methods=['POST'])
def model_clear_logs():
    """پاک کردن لاگ‌های آموزش"""
    try:
        system.trainer.clear_logs()
        return jsonify({"success": True, "message": "لاگ‌ها پاک شدند"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# روت‌های دیتابیس
# ============================================================


@app.route('/health/database', methods=['GET'])
def health_database():
    """بررسی سلامت همه دیتابیس‌ها"""
    from database import health_check
    return jsonify({
        "success": True,
        "data": health_check(),
        "timestamp": datetime.now().isoformat()
    })


# ============================================================
# روت‌های تنظیمات (Settings API)
# ============================================================

@app.route('/api/config', methods=['GET'])
def get_settings():
    """دریافت تمام تنظیمات سیستم (به جز توکن‌های حساس)"""
    try:
        from config import config as config_manager
        
        settings = config_manager.get_all()
        
        if 'databases' in settings:
            for db_name, db_config in settings['databases'].items():
                if 'token' in db_config:
                    token = db_config['token']
                    if token and len(token) > 10:
                        db_config['token'] = token[:6] + '...' + token[-4:]
                    else:
                        db_config['token'] = '••••••••'
        
        return jsonify({
            "success": True,
            "data": settings,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/config', methods=['POST'])
def update_settings():
    """به‌روزرسانی تنظیمات سیستم"""
    try:
        from config import config as config_manager
        
        data = request.json
        if not data:
            return jsonify({
                "success": False,
                "error": "داده ارسال نشده"
            }), 400
        
        for section, values in data.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    path = f"{section}.{key}"
                    config_manager.update(path, value)
            else:
                config_manager.update(section, values)
        
        return jsonify({
            "success": True,
            "message": "تنظیمات با موفقیت ذخیره شد",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/config/reset', methods=['POST'])
def reset_settings():
    """بازنشانی تنظیمات به حالت پیش‌فرض"""
    try:
        from config import config as config_manager
        
        config_manager.reload()
        
        return jsonify({
            "success": True,
            "message": "تنظیمات به حالت پیش‌فرض بازگشت",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error resetting settings: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# روت‌های احراز هویت
# ============================================================


@app.route('/login', methods=['GET'])
def login_page():
    """صفحه ورود"""
    return send_from_directory('static', 'login.html')


@app.route('/login', methods=['POST'])
def login():
    """ورود کاربر"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({"success": False, "error": "لطفاً نام کاربری و رمز عبور را وارد کنید"}), 400
    
    auth_manager = get_auth()
    result = auth_manager.login(username, password)
    
    if result["success"]:
        response = jsonify(result)
        response.set_cookie(
            'session_id', 
            result['session_id'],
            max_age=86400,
            httponly=True,
            secure=True,
            samesite='Lax',
            path='/'
        )
        return response
    
    return jsonify(result), 401


@app.route('/logout', methods=['POST'])
def logout():
    """خروج از حساب"""
    session_id = request.cookies.get('session_id')
    if session_id:
        auth_manager = get_auth()
        auth_manager.logout(session_id)
    
    response = jsonify({"success": True, "message": "خروج موفق"})
    response.delete_cookie('session_id', path='/')
    return response


@app.route('/recover', methods=['POST'])
def recover_password():
    """درخواست بازیابی رمز عبور"""
    data = request.json
    email = data.get('email', '').strip()
    
    if not email:
        return jsonify({"success": False, "error": "لطفاً ایمیل خود را وارد کنید"}), 400
    
    auth_manager = get_auth()
    username = auth_manager.get_user_by_email(email)
    
    if not username:
        return jsonify({
            "success": False, 
            "error": "ایمیل یافت نشد",
            "show_support": True,
            "support_id": "@your_telegram_id"
        }), 404
    
    code = auth_manager.generate_recovery_code(email)
    
    if code:
        return jsonify({
            "success": True,
            "message": "کد تایید به ایمیل شما ارسال شد",
            "email": email
        })
    
    return jsonify({"success": False, "error": "خطا در ارسال کد تایید"}), 500


@app.route('/recover/verify', methods=['POST'])
def verify_recovery_code():
    """تایید کد بازیابی"""
    data = request.json
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    
    if not email or not code:
        return jsonify({"success": False, "error": "لطفاً ایمیل و کد تایید را وارد کنید"}), 400
    
    auth_manager = get_auth()
    username = auth_manager.verify_recovery_code(email, code)
    
    if not username:
        return jsonify({"success": False, "error": "کد اشتباه است یا منقضی شده"}), 401
    
    user = auth_manager.get_user(username)
    session_id = secrets.token_hex(16)
    
    auth_manager._sessions[session_id] = {
        "username": username,
        "role": user.get("role", "guest"),
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(seconds=auth_manager._config.get("session_timeout", 86400))).isoformat(),
        "recovered": True
    }
    
    response = jsonify({
        "success": True,
        "message": "✅ ورود با بازیابی موفق",
        "username": username,
        "role": user.get("role", "guest"),
        "recovered": True
    })
    response.set_cookie(
        'session_id', 
        session_id,
        max_age=86400,
        httponly=True,
        secure=True,
        samesite='Lax',
        path='/'
    )
    return response


@app.route('/api/user', methods=['GET'])
def get_current_user():
    """دریافت اطلاعات کاربر فعلی"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
    
    auth_manager = get_auth()
    session = auth_manager.verify_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
    
    user = auth_manager.get_user(session["username"])
    if not user:
        return jsonify({"success": False, "error": "کاربر یافت نشد"}), 404
    
    return jsonify({
        "success": True,
        "data": {
            "username": session["username"],
            "role": session.get("role", "guest"),
            "password": user.get("password", ""),
            "recovered": session.get("recovered", False),
            **user
        }
    })


@app.route('/api/users', methods=['GET'])
def get_users():
    """دریافت لیست کاربران (فقط ادمین)"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
    
    auth_manager = get_auth()
    session = auth_manager.verify_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
    
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "دسترسی غیرمجاز"}), 403
    
    users = auth_manager.get_all_users()
    return jsonify({"success": True, "data": users})


@app.route('/api/users/<username>', methods=['PUT'])
def update_user(username):
    """به‌روزرسانی کاربر (فقط ادمین)"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
    
    auth_manager = get_auth()
    session = auth_manager.verify_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
    
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "دسترسی غیرمجاز"}), 403
    
    if username == "admin":
        return jsonify({"success": False, "error": "امکان تغییر ادمین وجود ندارد"}), 403
    
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "داده ارسال نشده"}), 400
    
    if auth_manager.update_user(username, data):
        return jsonify({"success": True, "message": f"کاربر {username} به‌روزرسانی شد"})
    
    return jsonify({"success": False, "error": "کاربر یافت نشد"}), 404


@app.route('/api/user/email', methods=['PUT'])
@require_auth()
def update_user_email():
    """به‌روزرسانی ایمیل کاربر"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"success": False, "error": "وارد نشده‌اید"}), 401
    
    auth_manager = get_auth()
    session = auth_manager.verify_session(session_id)
    if not session:
        return jsonify({"success": False, "error": "نشست منقضی شده"}), 401
    
    data = request.json
    email = data.get('email', '').strip()
    
    if not email:
        return jsonify({"success": False, "error": "لطفاً ایمیل را وارد کنید"}), 400
    
    if '@' not in email or '.' not in email:
        return jsonify({"success": False, "error": "ایمیل نامعتبر است"}), 400
    
    username = session["username"]
    if auth_manager.update_user(username, {"recovery_email": email, "email": email}):
        return jsonify({"success": True, "message": "ایمیل با موفقیت به‌روزرسانی شد"})
    
    return jsonify({"success": False, "error": "خطا در به‌روزرسانی ایمیل"}), 500


# ============================================================
# روت‌های جدید برای مدیریت مدل (ModelManager)
# ============================================================

@app.route('/model/versions', methods=['GET'])
def model_versions():
    """دریافت تاریخچه نسخه‌های مدل"""
    try:
        history = system.model_manager.get_version_history(limit=20)
        return jsonify({
            "success": True,
            "data": history,
            "count": len(history)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/version/<version>', methods=['GET'])
def model_version_detail(version):
    """دریافت اطلاعات یک نسخه خاص"""
    try:
        model = system.model_manager.get_model_by_version(version)
        if model:
            return jsonify({
                "success": True,
                "version": version,
                "loaded": True
            })
        return jsonify({"success": False, "message": "مدل یافت نشد"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/model/save', methods=['POST'])
def model_save():
    """ذخیره مدل فعلی در دیتابیس"""
    try:
        data = request.json
        period = data.get('period', '1m')
        accuracy = data.get('accuracy', 0.0)
        
        result = system.model_manager.save_model(
            system.model_manager.current_model,
            accuracy,
            period
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# روت‌های جدید برای صفحه تحلیلگر و چت
# ============================================================
@app.route('/api/command', methods=['POST'])
def process_command():
    """پردازش دستور متنی کاربر (API)"""
    try:
        data = request.json
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({"success": False, "error": "دستور وارد نشده"}), 400
        
        # دریافت اطلاعات کاربر (برای تاریخچه)
        user_id = None
        session_id = request.cookies.get('session_id')
        if session_id:
            auth_manager = get_auth()
            session = auth_manager.verify_session(session_id)
            if session:
                user_id = session.get('username')
        
        # پردازش دستور
        response = command_system.process_command(command, user_id)
        
        return jsonify({
            "success": True,
            "response": response,
            "command": command,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in process_command: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/analyze/<coin>', methods=['GET'])
def analyze_coin(coin):
    """تحلیل عددی یک ارز با تمام شاخص‌ها (API)"""
    period = request.args.get('period', '24h')
    try:
        analysis = numeric_analyzer.analyze_coin(coin, period)
        return jsonify({"success": True, "data": analysis})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/model/current', methods=['GET'])
def model_current():
    """دریافت وضعیت مدل جاری (API) - این روت قبلاً وجود داشت ولی با پاسخ جدیدتر"""
    try:
        stats = system.model_manager.get_stats()
        
        # افزودن اطلاعات بیشتر از trainer
        trainer_stats = system.trainer.get_stats() if hasattr(system, 'trainer') else {}
        
        return jsonify({
            "success": True,
            "data": {
                "loaded": stats.get('loaded', False),
                "version": stats.get('version', 'N/A'),
                "accuracy": trainer_stats.get('stats', {}).get('last_score'),
                "total_trainings": trainer_stats.get('stats', {}).get('total_trainings', 0),
                "data_points_used": trainer_stats.get('stats', {}).get('data_points_used', 0),
                "mode": trainer_stats.get('stats', {}).get('mode', 'DEMO')
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
# ============================================================
# صفحات خطا
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """صفحه خطای ۴۰۴ - صفحه یافت نشد"""
    return send_from_directory('static', '404.html'), 404


@app.errorhandler(403)
def forbidden(error):
    """صفحه خطای ۴۰۳ - دسترسی غیرمجاز"""
    return send_from_directory('static', '403.html'), 403


@app.errorhandler(500)
def internal_error(error):
    """صفحه خطای ۵۰۰ - خطای داخلی سرور"""
    return send_from_directory('static', '500.html'), 500


@app.errorhandler(Exception)
def handle_exception(error):
    """مدیریت تمام خطاهای پیش‌بینی‌نشده"""
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {error}")
    return send_from_directory('static', '500.html'), 500


# ============================================================
# روت‌های دیباگ (فقط برای توسعه)
# ============================================================

@app.route('/api/debug/exec', methods=['POST'])
def debug_exec():
    """اجرای دستور پایتون (فقط توسعه)"""
    data = request.json
    command = data.get('command', '').strip()
    
    if not command:
        return jsonify({"success": False, "error": "دستور وارد نشده"}), 400
    
    try:
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        exec(command, globals(), locals())
        
        result = sys.stdout.getvalue()
        sys.stdout = old_stdout
        
        return jsonify({
            "success": True,
            "result": result or "✅ اجرا شد (بدون خروجی)"
        })
    except Exception as e:
        sys.stdout = sys.__stdout__
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/debug/file', methods=['POST'])
def debug_file():
    """خواندن محتوای فایل"""
    data = request.json
    filename = data.get('filename', '').strip()
    
    if not filename:
        return jsonify({"success": False, "error": "نام فایل وارد نشده"}), 400
    
    allowed_files = [
        'config/settings.json', 
        'config/databases.json', 
        'config/users.json',
        'app.py',
        'routes.py',
        'auth_manager.py',
        'api_handler.py',
        'requirements.txt'
    ]
    
    if filename not in allowed_files:
        return jsonify({"success": False, "error": "دسترسی به این فایل مجاز نیست"}), 403
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({
            "success": True,
            "content": content
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/debug/env', methods=['GET'])
def debug_env():
    """دریافت متغیرهای محیطی (فقط کلیدها، بدون مقادیر حساس)"""
    env_vars = {}
    sensitive = ['TOKEN', 'PASSWORD', 'SECRET', 'KEY']
    
    for key, value in os.environ.items():
        if any(s in key.upper() for s in sensitive):
            env_vars[key] = '••••••••'
        else:
            env_vars[key] = value
    
    return jsonify({
        "success": True,
        "data": env_vars
    })


# ============================================================
# روت‌های دیتابیس (مدیریت)
# ============================================================

@app.route('/api/db/postgresql/tables', methods=['GET'])
def get_postgresql_tables():
    """دریافت لیست جدول‌های PostgreSQL با تعداد رکوردها"""
    from database import get_primary
    
    db = get_primary()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "دیتابیس متصل نیست"}), 503
    
    try:
        tables = db.execute("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        for table in tables:
            size_result = db.execute(f"""
                SELECT pg_total_relation_size('{table['table_name']}') / 1024 / 1024 as size_mb
            """)
            table['size_mb'] = size_result[0]['size_mb'] if size_result else 0
            
            update_result = db.execute(f"""
                SELECT last_analyze FROM pg_stat_user_tables 
                WHERE relname = '{table['table_name']}'
            """)
            table['last_update'] = update_result[0]['last_analyze'] if update_result else None
        
        return jsonify({
            "success": True,
            "data": tables
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/postgresql/table/<table_name>', methods=['GET'])
def get_postgresql_table_data(table_name):
    """دریافت محتوای یک جدول خاص"""
    from database import get_primary
    
    db = get_primary()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "دیتابیس متصل نیست"}), 503
    
    try:
        columns = db.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """)
        
        data = db.execute(f"SELECT * FROM {table_name} LIMIT 100")
        
        return jsonify({
            "success": True,
            "data": {
                "columns": columns,
                "rows": data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/redis/keys', methods=['GET'])
def get_redis_keys():
    """دریافت لیست کلیدهای Redis با نوع و حجم"""
    from database import get_cache
    
    db = get_cache()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "Redis متصل نیست"}), 503
    
    try:
        keys = db._client.keys('*')
        result = []
        for key in keys:
            key_type = db._client.type(key)
            ttl = db._client.ttl(key)
            size = 0
            if key_type == 'string':
                size = len(db._client.get(key) or '')
            elif key_type in ['hash', 'list', 'set', 'zset']:
                size = db._client.dbsize()
            
            result.append({
                'key': key,
                'type': key_type,
                'ttl': ttl if ttl > 0 else '∞',
                'size': size
            })
        
        return jsonify({
            "success": True,
            "data": result,
            "count": len(result)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/redis/key/<path:key>', methods=['GET'])
def get_redis_key_value(key):
    """دریافت مقدار یک کلید خاص"""
    from database import get_cache
    import json
    
    db = get_cache()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "Redis متصل نیست"}), 503
    
    try:
        value = db.get(key)
        key_type = db._client.type(key)
        ttl = db._client.ttl(key)
        
        try:
            if isinstance(value, str):
                json.loads(value)
        except:
            pass
        
        return jsonify({
            "success": True,
            "data": {
                "key": key,
                "value": value,
                "type": key_type,
                "ttl": ttl if ttl > 0 else '∞'
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/sqlite/tables', methods=['GET'])
def get_sqlite_tables():
    """دریافت لیست جدول‌های SQLite"""
    from database import get_backup
    
    db = get_backup()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "SQLite متصل نیست"}), 503
    
    try:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        
        result = []
        for table in tables:
            table_name = table['name']
            count_result = db.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = count_result[0]['count'] if count_result else 0
            
            result.append({
                'table_name': table_name,
                'row_count': row_count
            })
        
        return jsonify({
            "success": True,
            "data": result
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/sqlite/table/<table_name>', methods=['GET'])
def get_sqlite_table_data(table_name):
    """دریافت محتوای یک جدول SQLite"""
    from database import get_backup
    
    db = get_backup()
    if not db or not db.is_connected():
        return jsonify({"success": False, "error": "SQLite متصل نیست"}), 503
    
    try:
        columns_info = db.execute(f"PRAGMA table_info({table_name})")
        columns = [col['name'] for col in columns_info]
        
        data = db.execute(f"SELECT * FROM {table_name} LIMIT 100")
        
        return jsonify({
            "success": True,
            "data": {
                "columns": columns,
                "rows": data
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/db/search', methods=['GET'])
def search_databases():
    """جستجوی یکپارچه در همه دیتابیس‌ها"""
    from database import get_primary, get_cache, get_backup
    
    query = request.args.get('q', '').strip()
    target = request.args.get('target', 'all')
    
    if not query or len(query) < 2:
        return jsonify({"success": False, "error": "حداقل ۲ کاراکتر وارد کنید"}), 400
    
    results = []
    
    if target in ['all', 'postgresql']:
        pg = get_primary()
        if pg and pg.is_connected():
            try:
                tables = pg.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                for table in tables:
                    table_name = table['table_name']
                    data = pg.execute(f"SELECT * FROM {table_name} WHERE CAST(row_to_json(row) AS text) ILIKE '%{query}%' LIMIT 10")
                    for row in data:
                        results.append({
                            'database': 'PostgreSQL',
                            'type': 'table',
                            'table': table_name,
                            'content': str(row)
                        })
            except:
                pass
    
    if target in ['all', 'redis']:
        redis = get_cache()
        if redis and redis.is_connected():
            try:
                keys = redis._client.keys(f'*{query}*')
                for key in keys[:10]:
                    value = redis.get(key)
                    results.append({
                        'database': 'Redis',
                        'type': 'key',
                        'key': key,
                        'content': str(value)[:200]
                    })
            except:
                pass
    
    if target in ['all', 'sqlite']:
        sqlite = get_backup()
        if sqlite and sqlite.is_connected():
            try:
                tables = sqlite.execute("SELECT name FROM sqlite_master WHERE type='table'")
                for table in tables:
                    table_name = table['name']
                    data = sqlite.execute(f"SELECT * FROM {table_name} WHERE CAST(row_to_json(row) AS text) ILIKE '%{query}%' LIMIT 10")
                    for row in data:
                        results.append({
                            'database': 'SQLite',
                            'type': 'table',
                            'table': table_name,
                            'content': str(row)
                        })
            except:
                pass
    
    return jsonify({
        "success": True,
        "data": results[:50]
    })

@app.route('/admin/db/ensure', methods=['POST'])
def admin_ensure_db():
    """
   强制执行 reconnect دیتابیس‌ها (Self-Healing)
    """
    try:
        from database.database_factory import db_factory
        result = db_factory.force_reconnect()
        return jsonify({
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/admin/db/status', methods=['GET'])
def admin_db_status():
    """
    دریافت وضعیت دقیق دیتابیس‌ها
    """
    try:
        from database import registry, get_primary, get_cache, get_backup
        
        return jsonify({
            "success": True,
            "data": {
                "registry": {
                    name: str(type(db)) for name, db in registry.get_all().items()
                },
                "primary": {
                    "connected": get_primary() is not None and get_primary().is_connected(),
                    "instance": str(type(get_primary()))
                },
                "cache": {
                    "connected": get_cache() is not None and get_cache().is_connected(),
                    "instance": str(type(get_cache()))
                },
                "backup": {
                    "connected": get_backup() is not None and get_backup().is_connected(),
                    "instance": str(type(get_backup()))
                }
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================
# ایمپورت روت‌های جدید
# ============================================================

from routes import *
from health_mother_system import *


# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    print("=" * 60)
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۶.۰ - با ModelManager)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print(f"🧠 مدل: {'✅ بارگذاری شده' if system.model_manager.current_model else '❌ بارگذاری نشده'}")
    print(f"📊 نسخه مدل: {system.model_manager.current_version or 'N/A'}")
    print(f"📊 API Key: {'✅ تنظیم شده' if system.api.api_key else '❌ تنظیم نشده'}")
    print("=" * 60)
    print("📌 صفحات HTML:")
    print("  /              - صفحه اصلی")
    print("  /dashboard     - داشبورد")
    print("  /chart-page    - نمودار")
    print("  /predict-page  - پیش‌بینی")
    print("  /test-api-page - تست API")
    print("  /health-page   - سلامت سیستم")
    print("  /stats-page    - آمار")
    print("  /task-manager  - مدیریت تسک‌ها")
    print("=" * 60)
    print("📌 اندپوینت‌های API:")
    print("  /health        - بررسی سلامت (JSON)")
    print("  /credits       - اطلاعات اعتبار")
    print("  /stats         - آمار (JSON)")
    print("  /status        - وضعیت کلی")
    print("  /predict       - پیش‌بینی (Async)")
    print("  /predict-sync  - پیش‌بینی (Sync)")
    print("  /task-status   - وضعیت تسک")
    print("  /test-api      - تست API (JSON)")
    print("  /task-manager/stats - آمار تسک‌ها")
    print("  /task-manager/clear - پاک کردن تسک‌ها")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=debug)
