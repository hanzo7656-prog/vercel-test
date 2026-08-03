"""
ماژول سلامت مادر (MotherHealth) - نسخه‌ی بهینه‌شده برای Render Free Tier
"""

import os
import time
import json
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask, render_template, jsonify, request, Response, stream_with_context
import psutil

# تنظیم لاگر
logger = logging.getLogger("MotherHealth")

class MotherHealth:
    """
    کلاس اصلی سلامت مادر - بهینه‌شده برای Render
    """
    
    def __init__(self, api_key: str, port: int = 5000, check_interval: int = 30):
        self.api_key = api_key
        self.port = port
        self.check_interval = check_interval
        
        # تنظیمات پیش‌فرض
        self.config = {
            "dashboard_mode": "static",
            "self_healing": True,
            "self_optimization": True,
            "alerting": True,
            "reporting": False,
            "metric_collection": True,
            "logging": True,
            "circuit_breaker": True,
            "retry_backoff": True,
            "refresh_interval": 3,
            "thresholds": {
                "ram_warning": 70,
                "ram_critical": 85,
                "credit_warning": 15,
                "credit_critical": 5,
                "api_timeout": 5.0
            }
        }
        
        # متریک‌ها
        self.metrics = {
            "ram": {"used_mb": 0, "total_mb": 0, "percent": 0},
            "cpu": 0,
            "api": {"status": "unknown", "latency": 0, "last_check": None},
            "credits": {"remaining": 0, "total": 0, "percent": 0},
            "uptime": 0,
            "health_status": "healthy",
            "last_update": None
        }
        
        # لاگ‌ها (بافر حلقوی)
        self.logs = []
        self.max_logs = 500
        
        # Flask app
        self.app = Flask(__name__)
        self._setup_routes()
        
        # شروع ترد جمع‌آوری متریک
        self.running = True
        self.start_time = time.time()
        self.metric_thread = threading.Thread(target=self._metric_loop, daemon=True)
        self.metric_thread.start()
        
        self._add_log("INFO", "🩺 MotherHealth راه‌اندازی شد (Render Free Tier)")
        self._add_log("INFO", f"📊 پورت: {self.port} | حالت: {self.config['dashboard_mode']}")
    
    # ==================== مدیریت لاگ ====================
    
    def _add_log(self, level: str, message: str):
        """افزودن لاگ به بافر حلقوی"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        }
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)
    
    # ==================== جمع‌آوری متریک (بهینه‌شده) ====================
    
    def _collect_metrics(self):
        """جمع‌آوری همه‌ی متریک‌ها با پشتیبانی از Render"""
        try:
            # ۱. RAM - تشخیص محدودیت کانتینر
            mem_limit = os.environ.get('MEMORY_LIMIT', None)
            if mem_limit:
                total_mb = int(mem_limit) // (1024 * 1024)
            else:
                try:
                    mem = psutil.virtual_memory()
                    total_mb = mem.total // (1024 ** 2)
                except:
                    total_mb = 512  # مقدار پیش‌فرض Render Free
            
            # محاسبه‌ی مصرف واقعی
            try:
                mem = psutil.virtual_memory()
                used_mb = mem.used // (1024 ** 2)
                percent = min(100, round((used_mb / total_mb) * 100, 1))
            except:
                used_mb = total_mb // 4  # تخمین
                percent = 25
            
            self.metrics["ram"] = {
                "used_mb": used_mb,
                "total_mb": total_mb,
                "percent": percent
            }
            
            # ۲. CPU - با مقیاس‌سازی برای Render
            try:
                cpu_percent = psutil.cpu_percent(interval=0.2)
                # در Render با 0.1 CPU، مقدار واقعی را مقیاس‌سازی می‌کنیم
                if cpu_percent < 1:
                    cpu_percent = cpu_percent * 100  # تبدیل به درصد واقعی
                self.metrics["cpu"] = round(min(100, cpu_percent / 10), 1)  # مقیاس‌سازی
            except:
                self.metrics["cpu"] = 0.5  # مقدار پیش‌فرض
            
            # ۳. آپ‌تایم
            self.metrics["uptime"] = int(time.time() - self.start_time)
            
            # ۴. API Status و Credits
            if self.config.get("metric_collection", True):
                self._check_api_health()
            
            # ۵. به‌روزرسانی وضعیت کلی سلامت
            self._update_health_status()
            
            self.metrics["last_update"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self._add_log("ERROR", f"خطا در جمع‌آوری متریک: {str(e)}")
    
    def _check_api_health(self):
        """بررسی سلامت API با استفاده از coinstats_api"""
        try:
            from coinstats_api import CoinStatsAPI
            api = CoinStatsAPI(self.api_key)
            
            # ۱. بررسی وضعیت
            status = api.get_status()
            if status.get("status") == "ok":
                self.metrics["api"]["status"] = "ok"
                self.metrics["api"]["latency"] = status.get("_latency", 0)
            else:
                self.metrics["api"]["status"] = "error"
                self._add_log("WARNING", f"⚠️ API خطا: {status.get('detail', 'نامشخص')[:50]}")
            
            # ۲. بررسی اعتبار
            credits = api.get_credits()
            if "remainingCredits" in credits:
                self.metrics["credits"]["remaining"] = credits["remainingCredits"]
                self.metrics["credits"]["total"] = credits.get("totalCredits", 10000)
                self.metrics["credits"]["percent"] = round(
                    (self.metrics["credits"]["remaining"] / max(1, self.metrics["credits"]["total"])) * 100, 1
                )
            
            self.metrics["api"]["last_check"] = datetime.utcnow().isoformat()
            
        except ImportError:
            # اگر coinstats_api موجود نبود
            self.metrics["api"]["status"] = "unavailable"
            self._add_log("WARNING", "⚠️ ماژول coinstats_api یافت نشد")
        except Exception as e:
            self.metrics["api"]["status"] = "unreachable"
            self._add_log("WARNING", f"⚠️ API در دسترس نیست: {str(e)[:50]}")
    
    def _update_health_status(self):
        """به‌روزرسانی وضعیت کلی سلامت"""
        status = "healthy"
        reasons = []
        
        # بررسی RAM
        ram_percent = self.metrics["ram"]["percent"]
        if ram_percent >= self.config["thresholds"]["ram_critical"]:
            status = "critical"
            reasons.append(f"RAM: {ram_percent}% (بحرانی)")
            self._add_log("CRITICAL", f"🔴 RAM به {ram_percent}% رسید!")
        elif ram_percent >= self.config["thresholds"]["ram_warning"]:
            if status != "critical":
                status = "degraded"
            reasons.append(f"RAM: {ram_percent}% (هشدار)")
            self._add_log("WARNING", f"🟡 RAM به {ram_percent}% رسید")
        
        # بررسی اعتبار
        credit_percent = self.metrics["credits"]["percent"]
        if credit_percent <= self.config["thresholds"]["credit_critical"] and credit_percent > 0:
            if status != "critical":
                status = "critical"
            reasons.append(f"اعتبار: {credit_percent}% (بحرانی)")
            self._add_log("CRITICAL", f"🔴 اعتبار به {credit_percent}% رسید!")
        elif credit_percent <= self.config["thresholds"]["credit_warning"] and credit_percent > 0:
            if status != "critical":
                status = "degraded"
            reasons.append(f"اعتبار: {credit_percent}% (هشدار)")
            self._add_log("WARNING", f"🟡 اعتبار به {credit_percent}% رسید")
        
        # بررسی API
        if self.metrics["api"]["status"] != "ok":
            if status != "critical":
                status = "degraded"
            reasons.append(f"API: {self.metrics['api']['status']}")
        
        self.metrics["health_status"] = status
    
    def _metric_loop(self):
        """حلقه‌ی بی‌نهایت جمع‌آوری متریک"""
        while self.running:
            self._collect_metrics()
            time.sleep(self.check_interval)
    
    # ==================== مسیرهای وب ====================
    
    def _setup_routes(self):
        """تنظیم مسیرهای Flask"""
        
        @self.app.route('/')
        def dashboard():
            return render_template('health_dashboard.html', config=self.config)
        
        @self.app.route('/api/metrics')
        def get_metrics():
            return jsonify({
                "metrics": self.metrics,
                "config": self.config,
                "logs": self.logs[-20:]
            })
        
        @self.app.route('/api/logs')
        def get_logs():
            count = request.args.get('count', 50, type=int)
            return jsonify(self.logs[-count:])
        
        @self.app.route('/api/logs', methods=['DELETE'])
        def clear_logs():
            self.logs.clear()
            self._add_log("INFO", "🗑️ لاگ‌ها پاک شدند")
            return jsonify({"status": "ok"})
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            return jsonify(self.config)
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            data = request.json
            if not data:
                return jsonify({"error": "بدون داده"}), 400
            
            for key_path, value in data.items():
                keys = key_path.split('.')
                d = self.config
                for key in keys[:-1]:
                    d = d.setdefault(key, {})
                d[keys[-1]] = value
                self._add_log("INFO", f"⚙️ تنظیمات به‌روزرسانی شد: {key_path} = {value}")
            
            return jsonify({"status": "ok", "config": self.config})
        
        @self.app.route('/api/health')
        def health():
            return jsonify({
                "status": self.metrics["health_status"],
                "timestamp": self.metrics["last_update"]
            })
        
        @self.app.route('/api/stream')
        def stream():
            """ارسال داده‌های زنده (SSE) - فقط در حالت live"""
            if self.config.get("dashboard_mode") != "live":
                return jsonify({"error": "حالت داشبورد زنده فعال نیست"}), 400
            
            def generate():
                while True:
                    time.sleep(self.config.get("refresh_interval", 3))
                    yield f"data: {json.dumps({'metrics': self.metrics, 'logs': self.logs[-10:]})}\n\n"
            
            return Response(stream_with_context(generate()), mimetype="text/event-stream")
    
    # ==================== کنترل‌ها ====================
    
    def stop(self):
        self.running = False
        self._add_log("INFO", "🛑 MotherHealth متوقف شد")
    
    def run(self):
        self._add_log("INFO", f"🌐 داشبورد در http://localhost:{self.port}")
        try:
            self.app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)
        except KeyboardInterrupt:
            self.stop()


# ==================== اجرا ====================
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
    
    API_KEY = os.environ.get("API_KEY", "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw=")
    
    health = MotherHealth(
        api_key=API_KEY,
        port=int(os.environ.get("PORT", 5000)),
        check_interval=10  # هر ۱۰ ثانیه برای تست سریع‌تر
    )
    
    print("=" * 50)
    print("🩺 MotherHealth v2.0 (Render Free Tier)")
    print("=" * 50)
    print(f"📊 پورت: {health.port}")
    print(f"🔄 حالت: {health.config['dashboard_mode']}")
    print(f"💾 محدودیت RAM: 512 MB (تشخیص خودکار)")
    print("=" * 50)
    print("🌐 داشبورد:")
    print(f"   http://localhost:{health.port}")
    print("=" * 50)
    print("💡 نکته: برای مشاهده‌ی لاگ‌ها، کنسول Render را ببینید")
    print("=" * 50)
    
    try:
        health.run()
    except KeyboardInterrupt:
        print("\n🛑 در حال خروج...")
        health.stop()
        sys.exit(0)
