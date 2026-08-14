# app.py
# ============================================================
# سیستم اصلی تشخیص الگوهای بازاری با XGBoost
# شامل: مهندسی ویژگی‌ها، پیش‌بینی، سلامت، و API وب
# ============================================================

import os
import sys
import json
import time
import numpy as np
from datetime import datetime

from flask import Flask, jsonify, request

# import xgboost as xgb  # برای زمانی که مدل واقعی داریم
from api_handler import CoinStatsAPI


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
        self.load_model()

    def _get_memory_usage(self):
        """
        دریافت دقیق حافظه مصرفی پروسه فعلی
        (مقدار واقعی حافظه اختصاص داده شده به کانتینر)
        """
        try:
            # روش 1: از /proc/self/status (دقیق‌ترین برای پروسه فعلی)
            if os.path.exists('/proc/self/status'):
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            # VmRSS = Resident Set Size (حافظه واقعی مصرفی)
                            parts = line.split()
                            if len(parts) >= 2:
                                used_kb = int(parts[1])
                                used_mb = used_kb / 1024
                                
                                # گرفتن محدودیت از Cgroup (اگر وجود داشته باشه)
                                total_mb = self._get_memory_limit()
                                return used_mb, total_mb
        except:
            pass
        
        # روش 2: از Cgroup (برای Docker/Render)
        try:
            used_mb, total_mb = self._get_cgroup_memory()
            if total_mb > 0:
                return used_mb, total_mb
        except:
            pass
        
        # روش 3: Fallback به psutil
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
            # Cgroup v1
            if os.path.exists('/sys/fs/cgroup/memory/memory.limit_in_bytes'):
                with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                    limit_bytes = int(f.read())
                    if limit_bytes < 10**15:  # اگر محدودیت اعمال شده باشه
                        return limit_bytes / 1024**2
            
            # Cgroup v2
            if os.path.exists('/sys/fs/cgroup/memory.max'):
                with open('/sys/fs/cgroup/memory.max', 'r') as f:
                    limit_str = f.read().strip()
                    if limit_str != 'max':
                        limit_bytes = int(limit_str)
                        return limit_bytes / 1024**2
        except:
            pass
        
        # اگر محدودیتی پیدا نشد، 512MB رو پیش‌فرض بگیر (محدودیت Render)
        return 512
    
    def _get_cgroup_memory(self):
        """دریافت حافظه از Cgroup"""
        try:
            # Cgroup v1
            if os.path.exists('/sys/fs/cgroup/memory/memory.usage_in_bytes'):
                with open('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'r') as f:
                    used_bytes = int(f.read())
                    used_mb = used_bytes / 1024**2
                    total_mb = self._get_memory_limit()
                    return used_mb, total_mb
        except:
            pass
        
        # Cgroup v2
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
        """
        بارگذاری مدل XGBoost از فایل
        اگر فایل وجود نداشت، حالت DEMO فعال میشه
        """
        try:
            # بررسی وجود فایل مدل
            if os.path.exists("model.json"):
                # import xgboost as xgb
                # self.model = xgb.Booster()
                # self.model.load_model("model.json")
                # self.model_loaded = True
                # print("✅ مدل XGBoost با موفقیت بارگذاری شد", file=sys.stderr)

                # فعلاً برای تست از حالت DEMO استفاده میکنیم
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
        """
        تبدیل داده‌های خام قیمت به ویژگی‌های عددی برای XGBoost

        ورودی: لیست [[timestamp, priceUSD, priceBTC, priceETH], ...]
        خروجی: آرایه numpy از ویژگی‌ها

        ویژگی‌های تولید شده:
        1-4: بازده در بازه‌های ۱، ۳، ۵، ۱۰ قدم
        5-7: فاصله قیمت از میانگین متحرک ۵، ۱۰، ۲۰ قدمی
        8: نوسان (انحراف معیار بازده‌ها)
        9: شاخص ترس و طمع (نرمال‌سازی شده)
        10-12: شیب قیمت در بازه‌های ۵، ۱۰، ۲۰ قدمی
        13: قدرت روند (R-squared)
        """
        if not chart_data or len(chart_data) < 30:
            return None

        # استخراج قیمت‌های USD
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

        # 3. نوسان (Volatility) - انحراف معیار بازده‌های اخیر
        if len(prices) >= 15:
            returns = np.diff(prices[-15:]) / (prices[-15:-1] + 1e-8)
            volatility = np.std(returns)
            features.append(np.clip(volatility, 0, 0.5))
        else:
            features.append(0.0)

        # 4. شاخص ترس و طمع (از API با کش)
        try:
            fg = self.api.get_fear_greed(use_cache=True)
            if fg and 'now' in fg:
                fear_value = fg['now'].get('value', 50)
                features.append(fear_value / 100.0)
            else:
                features.append(0.5)
        except:
            features.append(0.5)

        # 5. شیب قیمت (روند) در بازه‌های مختلف
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

        # تبدیل به آرایه numpy
        return np.array(features, dtype=np.float32)

    # ============================================================
    # پیش‌بینی اصلی
    # ============================================================

    def predict(self, coin_id="bitcoin", period="24h"):
        """
        هسته اصلی سیستم: دریافت داده → استخراج ویژگی → پیش‌بینی

        پارامترها:
            coin_id: شناسه ارز (مثال: bitcoin, ethereum)
            period: بازه زمانی (1h, 4h, 24h)

        خروجی:
            دیکشنری شامل: سیگنال، اطمینان، قیمت فعلی و ...
        """
        start_time = time.time()

        # اعتبارسنجی بازه زمانی
        valid_periods = ["1h", "4h", "24h"]
        if period not in valid_periods:
            return {
                "error": "InvalidPeriod",
                "message": f"بازه زمانی باید یکی از {valid_periods} باشد"
            }

        # 1. دریافت داده‌های تاریخی
        chart_data = self.api.get_chart(coin_id, period)

        # مدیریت خطا در دریافت داده
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

        # 3. پیش‌بینی با مدل
        if self.model_loaded and self.model:
            try:
                # dmatrix = xgb.DMatrix(features.reshape(1, -1))
                # prediction = self.model.predict(dmatrix)[0]
                # prediction = float(prediction)
                prediction = 0.55  # موقتاً برای تست
            except Exception as e:
                prediction = 0.5 + (np.random.randn() * 0.05)
        else:
            # حالت DEMO: شبیه‌سازی ساده بر اساس ویژگی‌ها
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

            prediction = np.clip(base_score + np.random.randn() * 0.05, 0, 1)

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
            "model_mode": "DEMO" if not self.model_loaded else "PRODUCTION"
        }

    # ============================================================
    # سلامت سیستم
    # ============================================================

    def health_check(self):
        """
        بررسی کامل سلامت سیستم:
        - اتصال به API
        - بارگذاری مدل
        - اعتبار باقیمانده
        - وضعیت حافظه
        """
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
        status["components"]["model"] = {
            "status": "healthy" if self.model_loaded else "degraded",
            "message": "مدل بارگذاری شده است" if self.model_loaded else "حالت DEMO (بدون مدل)",
            "mode": "PRODUCTION" if self.model_loaded else "DEMO"
        }

        if not self.model_loaded:
            status["status"] = "degraded" if status["status"] == "ok" else status["status"]

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
            else:
                status["components"]["credits"] = {
                    "status": "unknown",
                    "message": "امکان دریافت اطلاعات اعتبار وجود ندارد"
                }
        except Exception as e:
            status["components"]["credits"] = {
                "status": "unknown",
                "message": f"خطا: {str(e)}"
            }

        # 4. حافظه (با روش دقیق /proc/self/status)
        try:
            used_mb, total_mb = self._get_memory_usage()
            
            # اگر total_mb صفر یا خیلی بزرگ بود، از مقدار پیش‌فرض استفاده کن
            if total_mb == 0 or total_mb > 10000:  # بیشتر از 10GB یعنی کل سیستم
                total_mb = 512  # محدودیت پیش‌فرض Render
            
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


# ============================================================
# راه‌اندازی وب سرویس Flask
# ============================================================

app = Flask(__name__)

# ایجاد یک نمونه از سیستم (Global)
system = TradingSignalSystem()


@app.route('/', methods=['GET'])
def home():
    """
    صفحه اصلی - معرفی سرویس
    """
    return jsonify({
        "service": "Trading Signal System",
        "version": "1.0.0",
        "description": "سیستم تشخیص الگوهای بازاری با XGBoost",
        "endpoints": {
            "/": "این صفحه",
            "/health": "بررسی سلامت سیستم",
            "/predict": "پیش‌بینی الگو",
            "/stats": "آمار درخواست‌ها"
        },
        "usage": {
            "/predict?coin=bitcoin&period=24h": "پیش‌بینی برای بیت‌کوین با بازه ۲۴ ساعته",
            "/predict?coin=ethereum&period=1h": "پیش‌بینی برای اتریوم با بازه ۱ ساعته"
        },
        "supported_periods": ["1h", "4h", "24h"],
        "status": "online",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/health', methods=['GET'])
def health():
    """
    بررسی سلامت کامل سیستم
    """
    result = system.health_check()
    http_status = 200 if result.get('status') in ['ok', 'degraded'] else 503
    return jsonify(result), http_status


@app.route('/predict', methods=['GET'])
def predict():
    """
    پیش‌بینی الگو برای یک ارز خاص

    پارامترهای Query:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h) - مقادیر: 1h, 4h, 24h
    """
    coin = request.args.get('coin', 'bitcoin')
    period = request.args.get('period', '24h')

    # اعتبارسنجی بازه زمانی
    valid_periods = ["1h", "4h", "24h"]
    if period not in valid_periods:
        return jsonify({
            "error": "InvalidPeriod",
            "message": f"بازه زمانی باید یکی از {valid_periods} باشد",
            "provided": period
        }), 400

    # اجرای پیش‌بینی
    result = system.predict(coin, period)

    # اگر خطا داشت، کد وضعیت مناسب برگردون
    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@app.route('/stats', methods=['GET'])
def stats():
    """
    دریافت آمار درخواست‌ها و وضعیت سیستم
    """
    return jsonify({
        "api_stats": system.api.get_stats(),
        "model_loaded": system.model_loaded,
        "uptime": str(datetime.now() - system.start_time),
        "timestamp": datetime.now().isoformat()
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "NotFound",
        "message": "مسیر درخواستی وجود ندارد",
        "available_endpoints": ["/", "/health", "/predict", "/stats"]
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
    # دریافت پورت از محیط (برای Render)
    port = int(os.environ.get("PORT", 5000))

    # حالت دیباگ در محیط توسعه
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    print("=" * 60)
    print("🚀 سیستم تشخیص الگوهای بازاری")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print("=" * 60)

    # اجرای سرویس
    app.run(host="0.0.0.0", port=port, debug=debug)
