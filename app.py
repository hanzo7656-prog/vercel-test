# app.py
# ============================================================
# سیستم اصلی تشخیص الگوهای بازاری با XGBoost
# با پشتیبانی از Background Tasks برای پردازش‌های سنگین
# ============================================================

import os
import sys
import json
import time
import uuid
import threading
import numpy as np
from datetime import datetime
from queue import Queue
from flask import Flask, jsonify, request

# import xgboost as xgb
from api_handler import CoinStatsAPI


# ============================================================
# مدیریت تسک‌های پس‌زمینه
# ============================================================

class BackgroundTaskManager:
    """
    مدیریت تسک‌های سنگین در پس‌زمینه با Queue
    """
    def __init__(self):
        self.tasks = {}  # ذخیره نتایج تسک‌ها
        self.queue = Queue()
        self.worker_thread = None
        self.running = True
        self.start_worker()
    
    def start_worker(self):
        """شروع worker در یک ترد جداگانه"""
        def worker():
            while self.running:
                try:
                    task_id, func, args, kwargs = self.queue.get(timeout=1)
                    try:
                        result = func(*args, **kwargs)
                        self.tasks[task_id] = {
                            "status": "completed",
                            "result": result,
                            "timestamp": datetime.now().isoformat()
                        }
                    except Exception as e:
                        self.tasks[task_id] = {
                            "status": "failed",
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        }
                except:
                    pass
        
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()
    
    def submit(self, func, *args, **kwargs):
        """ارسال یک تسک به صف"""
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        }
        self.queue.put((task_id, func, args, kwargs))
        return task_id
    
    def get_result(self, task_id):
        """دریافت نتیجه یک تسک"""
        if task_id in self.tasks:
            return self.tasks[task_id]
        return None
    
    def cleanup(self, max_age_seconds=300):
        """پاک کردن تسک‌های قدیمی (بیش از ۵ دقیقه)"""
        now = datetime.now()
        to_delete = []
        for task_id, task in self.tasks.items():
            if 'timestamp' in task:
                task_time = datetime.fromisoformat(task['timestamp'])
                if (now - task_time).total_seconds() > max_age_seconds:
                    to_delete.append(task_id)
        for task_id in to_delete:
            del self.tasks[task_id]


# ============================================================
# هسته اصلی سیستم
# ============================================================

class TradingSignalSystem:
    """
    سیستم تشخیص الگوی بازاری
    شامل: دریافت داده → مهندسی ویژگی‌ها → پیش‌بینی با XGBoost
    """

    def __init__(self, api_key=None):
        """
        راه‌اندازی سیستم با کلید API
        """
        self.api = CoinStatsAPI(api_key)
        self.model = None
        self.model_loaded = False
        self.start_time = datetime.now()
        self.task_manager = BackgroundTaskManager()
        self.load_model()

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
                                total_mb = self._get_memory_limit()
                                return used_mb, total_mb
        except:
            pass
        
        try:
            used_mb, total_mb = self._get_cgroup_memory()
            if total_mb > 0:
                return used_mb, total_mb
        except:
            pass
        
        try:
            import psutil
            process = psutil.Process(os.getpid())
            used_mb = process.memory_info().rss / 1024**2
            total_mb = psutil.virtual_memory().total / 1024**2
            return used_mb, total_mb
        except:
            return 0, 0
    
    def _get_memory_limit(self):
        """دریافت محدودیت حافظه از Cgroup"""
        try:
            if os.path.exists('/sys/fs/cgroup/memory/memory.limit_in_bytes'):
                with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                    limit_bytes = int(f.read())
                    if limit_bytes < 10**15:
                        return limit_bytes / 1024**2
            if os.path.exists('/sys/fs/cgroup/memory.max'):
                with open('/sys/fs/cgroup/memory.max', 'r') as f:
                    limit_str = f.read().strip()
                    if limit_str != 'max':
                        limit_bytes = int(limit_str)
                        return limit_bytes / 1024**2
        except:
            pass
        return 512
    
    def _get_cgroup_memory(self):
        """دریافت حافظه از Cgroup"""
        try:
            if os.path.exists('/sys/fs/cgroup/memory/memory.usage_in_bytes'):
                with open('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'r') as f:
                    used_bytes = int(f.read())
                    used_mb = used_bytes / 1024**2
                    total_mb = self._get_memory_limit()
                    return used_mb, total_mb
        except:
            pass
        try:
            if os.path.exists('/sys/fs/cgroup/memory.current'):
                with open('/sys/fs/cgroup/memory.current', 'r') as f:
                    used_bytes = int(f.read().strip())
                    used_mb = used_bytes / 1024**2
                    total_mb = self._get_memory_limit()
                    return used_mb, total_mb
        except:
            pass
        return 0, 0

    def load_model(self):
        """بارگذاری مدل XGBoost از فایل"""
        try:
            if os.path.exists("model.json"):
                # import xgboost as xgb
                # self.model = xgb.Booster()
                # self.model.load_model("model.json")
                # self.model_loaded = True
                # print("✅ مدل XGBoost با موفقیت بارگذاری شد", file=sys.stderr)
                self.model_loaded = False
                print("⚠️ حالت DEMO: مدل واقعی بارگذاری نشد", file=sys.stderr)
            else:
                print("⚠️ فایل model.json یافت نشد - استفاده از حالت DEMO", file=sys.stderr)
                self.model_loaded = False
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری مدل: {e}", file=sys.stderr)
            self.model_loaded = False

    # ============================================================
    # مهندسی ویژگی‌ها
    # ============================================================

    def extract_features(self, chart_data):
        """تبدیل داده‌های خام قیمت به ویژگی‌های عددی برای XGBoost"""
        if not chart_data or len(chart_data) < 30:
            return None

        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
            elif isinstance(point, dict) and 'price' in point:
                prices.append(float(point['price']))

        if len(prices) < 30:
            return None

        prices = np.array(prices, dtype=np.float32)
        features = []

        # 1. بازده‌ها (Returns) در بازه‌های مختلف
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

        # 5. شیب قیمت
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

    # ============================================================
    # پیش‌بینی اصلی (برای اجرا در Background)
    # ============================================================

    def predict_sync(self, coin_id="bitcoin", period="24h"):
        """
        نسخه همگام (Synchronous) پیش‌بینی - برای اجرا در Background Task
        """
        start_time = time.time()

        valid_periods = ["1h", "4h", "24h"]
        if period not in valid_periods:
            return {
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد"
            }

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

        features = self.extract_features(chart_data)

        if features is None:
            return {
                "error": "InsufficientData",
                "message": "داده‌های کافی برای تحلیل وجود ندارد (حداقل ۳۰ نقطه لازم است)",
                "coin": coin_id,
                "period": period,
                "data_points": len(chart_data) if chart_data else 0
            }

        # پیش‌بینی با مدل یا DEMO
        if self.model_loaded and self.model:
            try:
                prediction = 0.55
            except Exception as e:
                prediction = 0.5 + (np.random.randn() * 0.05)
        else:
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
            "model_mode": "DEMO" if not self.model_loaded else "PRODUCTION"
        }

    # ============================================================
    # پیش‌بینی با Background Task (نسخه Async)
    # ============================================================

    def predict_async(self, coin_id="bitcoin", period="24h"):
        """
        نسخه غیرهمگام (Asynchronous) - تسک رو به صف اضافه میکنه
        """
        task_id = self.task_manager.submit(self.predict_sync, coin_id, period)
        return {
            "status": "processing",
            "task_id": task_id,
            "message": "پردازش در پس‌زمینه شروع شد",
            "check_status": f"/task-status?task_id={task_id}"
        }

    # ============================================================
    # سلامت سیستم
    # ============================================================

    def health_check(self):
        """بررسی کامل سلامت سیستم"""
        status = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }

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

        status["components"]["model"] = {
            "status": "healthy" if self.model_loaded else "degraded",
            "message": "مدل بارگذاری شده است" if self.model_loaded else "حالت DEMO (بدون مدل)",
            "mode": "PRODUCTION" if self.model_loaded else "DEMO"
        }

        if not self.model_loaded:
            status["status"] = "degraded" if status["status"] == "ok" else status["status"]

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

        status["components"]["api_stats"] = self.api.get_stats()
        status["components"]["task_manager"] = {
            "pending_tasks": self.task_manager.queue.qsize(),
            "total_tasks": len(self.task_manager.tasks)
        }

        return status


# ============================================================
# راه‌اندازی وب سرویس Flask
# ============================================================

app = Flask(__name__)
system = TradingSignalSystem()


@app.route('/', methods=['GET'])
def home():
    """صفحه اصلی - معرفی سرویس"""
    return jsonify({
        "service": "Trading Signal System",
        "version": "2.0.0",
        "description": "سیستم تشخیص الگوهای بازاری با XGBoost (با پشتیبانی از Background Tasks)",
        "endpoints": {
            "/": "این صفحه",
            "/health": "بررسی سلامت سیستم",
            "/predict": "پیش‌بینی الگو (Async - سریع)",
            "/predict-sync": "پیش‌بینی الگو (Sync - کندتر)",
            "/task-status": "بررسی وضعیت تسک",
            "/stats": "آمار درخواست‌ها",
            "/test-api": "تست و نمایش داده‌های خام API"
        },
        "usage": {
            "/predict?coin=bitcoin&period=24h": "پیش‌بینی (پس‌زمینه - فوری)",
            "/predict-sync?coin=bitcoin&period=24h": "پیش‌بینی (همگام - ممکنه Timeout بخوره)",
            "/task-status?task_id=abc123": "بررسی نتیجه تسک"
        },
        "supported_periods": ["1h", "4h", "24h"],
        "status": "online",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/health', methods=['GET'])
def health():
    """بررسی سلامت کامل سیستم"""
    result = system.health_check()
    http_status = 200 if result.get('status') in ['ok', 'degraded'] else 503
    return jsonify(result), http_status


@app.route('/predict', methods=['GET'])
def predict():
    """
    پیش‌بینی الگو با Background Task (سریع - بدون Timeout)
    
    پارامترهای Query:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h) - مقادیر: 1h, 4h, 24h
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    
    valid_periods = ["1h", "4h", "24h"]
    if period not in valid_periods:
        return jsonify({
            "error": "InvalidPeriod",
            "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
            "provided": period
        }), 400
    
    # ارسال تسک به پس‌زمینه
    result = system.predict_async(coin, period)
    return jsonify(result), 202  # 202 = Accepted


@app.route('/predict-sync', methods=['GET'])
def predict_sync():
    """
    پیش‌بینی الگو به صورت همگام (ممکنه Timeout بخوره)
    
    پارامترهای Query:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h)
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    
    valid_periods = ["1h", "4h", "24h"]
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
    
    return jsonify({
        "task_id": task_id,
        "status": result.get("status"),
        "result": result.get("result"),
        "error": result.get("error"),
        "timestamp": result.get("timestamp")
    })


@app.route('/stats', methods=['GET'])
def stats():
    """دریافت آمار درخواست‌ها و وضعیت سیستم"""
    return jsonify({
        "api_stats": system.api.get_stats(),
        "model_loaded": system.model_loaded,
        "uptime": str(datetime.now() - system.start_time),
        "pending_tasks": system.task_manager.queue.qsize(),
        "total_tasks": len(system.task_manager.tasks),
        "timestamp": datetime.now().isoformat()
    })


@app.route('/test-api', methods=['GET'])
def test_api():
    """تست ارتباط با API و نمایش داده‌های خام (با Background)"""
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    data_type = request.args.get('type', 'chart')
    
    valid_types = ['chart', 'coin', 'fear_greed', 'btc_dominance', 'status', 'credits']
    if data_type not in valid_types:
        return jsonify({
            "error": "InvalidType",
            "message": f"نوع داده باید یکی از {valid_types} باشد",
            "provided": data_type
        }), 400


# ============================================================
# روت‌های صفحات HTML
# ============================================================

@app.route('/dashboard')
def dashboard_page():
    """داشبورد اصلی"""
    health = system.health_check()
    return render_template_string(open('templates/dashboard.html').read(), 
        active_page='dashboard',
        status=health.get('status', 'unknown'),
        model_loaded=system.model_loaded,
        memory_used=health.get('components', {}).get('memory', {}).get('used_mb', 0),
        memory_total=health.get('components', {}).get('memory', {}).get('total_mb', 512),
        memory_percent=health.get('components', {}).get('memory', {}).get('percent', 0),
        credits_total=health.get('components', {}).get('credits', {}).get('total', 0),
        credits_used=health.get('components', {}).get('credits', {}).get('used', 0),
        credits_remaining=health.get('components', {}).get('credits', {}).get('remaining', 0),
        subscription=health.get('components', {}).get('credits', {}).get('subscription', 'free'),
        total_requests=health.get('components', {}).get('api_stats', {}).get('total_requests', 0),
        uptime=str(datetime.now() - system.start_time).split('.')[0],
        status_class='online' if health.get('status') == 'ok' else 'degraded' if health.get('status') == 'degraded' else 'offline',
        status_text='آنلاین' if health.get('status') == 'ok' else 'محدود' if health.get('status') == 'degraded' else 'آفلاین'
    )

@app.route('/predict-page')
def predict_page():
    """صفحه پیش‌بینی"""
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')
    return render_template_string(open('templates/predict.html').read(),
        active_page='predict',
        coin=coin,
        period=period,
        status_class='online',
        status_text='آنلاین',
        uptime=str(datetime.now() - system.start_time).split('.')[0]
    )

@app.route('/test-api-page')
def test_api_page():
    """صفحه تست API"""
    return render_template_string(open('templates/test_api.html').read(),
        active_page='test-api',
        status_class='online',
        status_text='آنلاین',
        uptime=str(datetime.now() - system.start_time).split('.')[0]
    )

@app.route('/health-page')
def health_page():
    """صفحه سلامت سیستم"""
    return render_template_string(open('templates/health.html').read(),
        active_page='health',
        status_class='online',
        status_text='آنلاین',
        uptime=str(datetime.now() - system.start_time).split('.')[0]
    )

@app.route('/stats-page')
def stats_page():
    """صفحه آمار"""
    return render_template_string(open('templates/stats.html').read(),
        active_page='stats',
        status_class='online',
        status_text='آنلاین',
        uptime=str(datetime.now() - system.start_time).split('.')[0]
    )

    
    # استفاده از Background Task برای دریافت داده
    def fetch_data():
        try:
            if data_type == 'chart':
                data = system.api.get_chart(coin, period)
                if data and "error" not in data:
                    return {
                        "count": len(data),
                        "sample": data[:5] if len(data) > 5 else data,
                        "first_point": data[0] if data else None,
                        "last_point": data[-1] if data else None,
                        "data_type": "list_of_arrays",
                        "point_format": "[timestamp, priceUSD, priceBTC, priceETH]"
                    }
                return {"error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}
            elif data_type == 'coin':
                data = system.api.get_coin(coin)
                if data and "error" not in data:
                    return {
                        "id": data.get('id'),
                        "name": data.get('name'),
                        "symbol": data.get('symbol'),
                        "price": data.get('price'),
                        "volume": data.get('volume'),
                        "marketCap": data.get('marketCap'),
                        "priceChange1h": data.get('priceChange1h'),
                        "priceChange1d": data.get('priceChange1d'),
                        "priceChange1w": data.get('priceChange1w')
                    }
                return {"error": data.get("message", "خطا در دریافت داده") if data else "داده‌ای دریافت نشد"}
            else:
                return {"error": f"نوع داده {data_type} پشتیبانی نمیشود"}
        except Exception as e:
            return {"error": str(e)}
    
    task_id = system.task_manager.submit(fetch_data)
    
    return jsonify({
        "status": "processing",
        "task_id": task_id,
        "message": "دریافت داده در پس‌زمینه شروع شد",
        "check_status": f"/task-status?task_id={task_id}"
    }), 202


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "NotFound",
        "message": "مسیر درخواستی وجود ندارد",
        "available_endpoints": ["/", "/health", "/predict", "/predict-sync", "/task-status", "/stats", "/test-api"]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "InternalServerError",
        "message": "خطای داخلی سرور",
        "timestamp": datetime.now().isoformat()
    }), 500


# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    print("=" * 60)
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۲.۰ - با Background Tasks)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print(f"📊 API Key: {'✅ تنظیم شده' if system.api.api_key else '❌ تنظیم نشده'}")
    print("=" * 60)
    print("📌 اندپوینت‌های موجود:")
    print("  /              - صفحه اصلی")
    print("  /health        - بررسی سلامت")
    print("  /predict       - پیش‌بینی (Async - سریع) ⭐")
    print("  /predict-sync  - پیش‌بینی (Sync - ممکنه Timeout بخوره)")
    print("  /task-status   - بررسی وضعیت تسک")
    print("  /stats         - آمار درخواست‌ها")
    print("  /test-api      - تست API (Async)")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=debug)
