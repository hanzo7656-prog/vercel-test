# app.py
# ============================================================
# هسته اصلی سیستم تشخیص الگوهای بازاری
# شامل: سیستم، مدیریت تسک‌ها، روت‌های بازار
# ============================================================

import os
import sys
import json
import time
import uuid
import threading
import numpy as np
import logging
from datetime import datetime
from queue import Queue
from flask import Flask, jsonify, request

from api_handler import CoinStatsAPI
from task_manager import get_task_manager, TaskPriority
from auto_trainer import AutoTrainer
from database import get_redis, health_check, as db_health_check

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
        self.model = None
        self.model_loaded = False
        self.start_time = datetime.now()
        
        # استفاده از TaskManager جدید
        self.task_manager = get_task_manager(
            num_workers=1,      # برای سرور ۵۱۲MB
            max_tasks=50,       # حداکثر ۵۰ تسک در حافظه
            task_ttl=300        # تسک‌ها بعد از ۵ دقیقه پاک میشن
        )
        self.load_model()
        
        # کش برای داده‌های خودکار
        self._cached_coins = None
        self._cached_news = None
        self._cached_fear_greed = None
        self._cached_market = None
        
        # ثبت تسک‌های خودکار
        self._register_auto_tasks()

        #اموزش خودکار مدل XGboost
        self.trainer = AutoTrainer(self.api, "model.xgb")
        self.trainer.start_auto_train(interval_hours=6)

        logger=logging.getLogger(__name__)
        logger.info('AutoTrainer started')

        # دیتابیس‌ها
        self.db = get_redis()
        is self.db and self.db.is_connected():
            print("✅ اتصال به دیتابیس برقرار شد", file=sys.stderr)
        else
            print("⚠️ دیتابیس در دسترس نیست", file=sys.stderr)


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

    def load_model(self):
        """بارگذاری مدل XGBoost از فایل"""
        try:
            if os.path.exists("model.xgb"):
                import xgboost as xgb
                self.model = xgb.Booster()
                self.model.load_model("model.xgb")
                self.model_loaded = True
                print("✅ مدل XGBoost با موفقیت بارگذاری شد", file=sys.stderr)
            else:
                print("⚠️ فایل model.json یافت نشد - استفاده از حالت DEMO", file=sys.stderr)
                self.model_loaded = False
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری مدل: {e}", file=sys.stderr)
            self.model_loaded = False
            
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

        # 3. پیش‌بینی با مدل یا حالت DEMO
        if self.model_loaded and self.model:
            try:
                # تبدیل ویژگی‌ها به فرمت DMatrix برای XGBoost
                dmatrix = xgb.DMatrix(features.reshape(1, -1))
                prediction = self.model.predict(dmatrix)[0]
                prediction = float(prediction)
            except Exception as e:
                print(f"⚠️ خطا در پیش‌بینی با مدل: {e}")
                # Fallback به حالت DEMO
                prediction = self._demo_predict(features)
        else:
            # حالت DEMO (وقتی مدل وجود نداشته باشه)
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
            "model_mode": "PRODUCTION" if self.model_loaded else "DEMO"
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
                
    def predict_async(self, coin_id="bitcoin", period="24h"):
        """نسخه غیرهمگام (Asynchronous) با TaskManager جدید"""
        task_id = self.task_manager.submit(
            func=self.predict_sync,
            name=f"پیش‌بینی {coin_id} {period}",
            args=(coin_id, period),
            priority=TaskPriority.HIGH,
            timeout=120
        )
        return {
            "status": "processing",
            "task_id": task_id,
            "message": "پردازش در پس‌زمینه شروع شد",
            "check_status": f"/task-status?task_id={task_id}"
         }

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

        # 2. سلامت مدل (اصلاح شده)
        model_exists = os.path.exists("model.json")
        model_status = "healthy" if model_exists else "degraded"
        model_mode = "BETA" if model_exists else "DEMO"
      
        status["components"]["model"] = {
            "status": model_status,
            "message": "مدل بارگذاری شده است" if model_exists else "حالت DEMO (بدون مدل)",
            "mode": model_mode,
            "file_exists": model_exists
        }

        # اگر مدل وجود داشته باشه، وضعیت کلی رو ok نگه دار
        if model_exists and status["status"] == "degraded":
            status["status"] = "ok"

        return status

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
        
        # 6. آمار TaskManager
        status["components"]["task_manager"] = self.task_manager.get_stats()

        return status

    # ============================================================
    # تسک‌های خودکار
    # ============================================================
    
    def _register_auto_tasks(self):
        """ثبت تسک‌های خودکار در TaskManager"""
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. به‌روزرسانی ارزهای برتر
        def update_top_coins():
            try:
                data = self.api.get_coins_list(limit=20)
                if data and "error" not in data:
                    self._cached_coins = data
                    logger.info("✅ Top coins updated")
                    return {"status": "success", "count": len(data.get('result', []))}
                return {"status": "failed", "error": "No data"}
            except Exception as e:
                logger.error(f"Update top coins failed: {e}")
                return {"status": "failed", "error": str(e)}
        
        # 2. به‌روزرسانی اخبار
        def update_news():
            try:
                data = self.api.get_news(limit=6)
                if data and "error" not in data:
                    self._cached_news = data
                    logger.info("✅ News updated")
                    return {"status": "success", "count": len(data.get('data', []))}
                return {"status": "failed", "error": "No data"}
            except Exception as e:
                logger.error(f"Update news failed: {e}")
                return {"status": "failed", "error": str(e)}
        
        # 3. به‌روزرسانی شاخص ترس و طمع
        def update_fear_greed():
            try:
                data = self.api.get_fear_greed(use_cache=False)
                if data and "error" not in data:
                    self._cached_fear_greed = data
                    logger.info("✅ Fear & Greed updated")
                    return {"status": "success", "data": data}
                return {"status": "failed", "error": "No data"}
            except Exception as e:
                logger.error(f"Update fear greed failed: {e}")
                return {"status": "failed", "error": str(e)}
        
        # 4. به‌روزرسانی وضعیت بازار
        def update_market_stats():
            try:
                data = self.api.get_global_market()
                if data and "error" not in data:
                    self._cached_market = data
                    logger.info("✅ Market stats updated")
                    return {"status": "success", "data": data}
                return {"status": "failed", "error": "No data"}
            except Exception as e:
                logger.error(f"Update market stats failed: {e}")
                return {"status": "failed", "error": str(e)}
        
        # ثبت تسک‌ها
        self.task_manager.register_auto_task(
            "به‌روزرسانی ارزهای برتر", 
            update_top_coins, 
            120
        )
        self.task_manager.register_auto_task(
            "به‌روزرسانی اخبار", 
            update_news, 
            120
        )
        self.task_manager.register_auto_task(
            "شاخص ترس و طمع", 
            update_fear_greed, 
            300
        )
        self.task_manager.register_auto_task(
            "وضعیت کلی بازار", 
            update_market_stats, 
            300
        )
        
        # شروع خودکار همه تسک‌ها
        self.task_manager.start_all_auto_tasks(stagger=5)
        logger.info("✅ All auto tasks started")


# ============================================================
# راه‌اندازی وب سرویس Flask
# ============================================================

app = Flask(__name__)
system = TradingSignalSystem()


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
# روت‌های TaskManager
# ============================================================

@app.route('/task-manager/stats', methods=['GET'])
def task_manager_stats():
    """دریافت آمار کامل TaskManager"""
    stats = system.task_manager.get_stats()
    return jsonify(stats)


@app.route('/task-manager/clear', methods=['POST'])
def task_manager_clear():
    """پاک کردن تسک‌های تکمیل‌شده"""
    system.task_manager.clear_completed()
    return jsonify({
        "success": True,
        "message": "تسک‌های تکمیل‌شده پاک شدند",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/task-manager/auto/start', methods=['POST'])
def auto_start():
    """شروع یک تسک خودکار"""
    name = request.args.get('name')
    if not name:
        return jsonify({"success": False, "error": "نام تسک الزامی است"}), 400
    
    result = system.task_manager.start_auto_task(name)
    if result:
        return jsonify({"success": True, "message": f"تسک {name} شروع شد"})
    return jsonify({"success": False, "error": "تسک پیدا نشد یا در حال اجراست"}), 400


@app.route('/task-manager/auto/stop', methods=['POST'])
def auto_stop():
    """متوقف کردن یک تسک خودکار"""
    name = request.args.get('name')
    if not name:
        return jsonify({"success": False, "error": "نام تسک الزامی است"}), 400
    
    result = system.task_manager.stop_auto_task(name)
    if result:
        return jsonify({"success": True, "message": f"تسک {name} متوقف شد"})
    return jsonify({"success": False, "error": "تسک پیدا نشد یا در حال اجرا نیست"}), 400


@app.route('/task-manager/auto/start-all', methods=['POST'])
def auto_start_all():
    """شروع همه تسک‌های خودکار"""
    system.task_manager.start_all_auto_tasks()
    return jsonify({"success": True, "message": "همه تسک‌های خودکار شروع شدند"})


@app.route('/task-manager/auto/stop-all', methods=['POST'])
def auto_stop_all():
    """متوقف کردن همه تسک‌های خودکار"""
    system.task_manager.stop_all_auto_tasks()
    return jsonify({"success": True, "message": "همه تسک‌های خودکار متوقف شدند"})





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


#===================================================================
# روت‌های دیتابیس
#===================================================================

@app.route('/health/database', methods=['GET'])
def health_database():
    """بررسی سلامت دیتابیس‌ها"""
    return jsonify({
        "success": True,
        "data": db_health_check(),
        "timestamp": datetime.now().isoformat()
    })
# ============================================================
# Import روت‌های دیگر
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
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۵.۰ - با TaskManager)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
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
