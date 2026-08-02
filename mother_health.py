"""
ماژول سلامت مادر (MotherHealth)
نمایش متریک‌های سیستم و API در یک داشبورد وب
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
    کلاس اصلی سلامت مادر
    """
    
    def __init__(self, api_key: str, port: int = 5000, check_interval: int = 30):
        self.api_key = api_key
        self.port = port
        self.check_interval = check_interval
        
        # تنظیمات پیش‌فرض
        self.config = {
            "dashboard_mode": "static",  # "static" یا "live"
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
            "health_status": "healthy",  # healthy | degraded | critical
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
        
        # تنظیمات پیش‌فرض
        self._add_log("INFO", "🩺 MotherHealth راه‌اندازی شد")
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
        # همچنین در لاگر پایتون چاپ کن
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)
    
    # ==================== جمع‌آوری متریک ====================
    
    def _collect_metrics(self):
        """جمع‌آوری همه‌ی متریک‌ها در یک حلقه"""
        try:
            # ۱. RAM
            mem = psutil.virtual_memory()
            self.metrics["ram"] = {
                "used_mb": mem.used // (1024 ** 2),
                "total_mb": mem.total // (1024 ** 2),
                "percent": mem.percent
            }
            
            # ۲. CPU
            self.metrics["cpu"] = psutil.cpu_percent(interval=0.1)
            
            # ۳. آپ‌تایم
            self.metrics["uptime"] = int(time.time() - self.start_time)
            
            # ۴. API Status و Credits (اگر فعال باشد)
            if self.config.get("metric_collection", True):
                self._check_api_health()
            
            # ۵. به‌روزرسانی وضعیت کلی سلامت
            self._update_health_status()
            
            self.metrics["last_update"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self._add_log("ERROR", f"خطا در جمع‌آوری متریک: {str(e)}")
    
    def _check_api_health(self):
        """بررسی سلامت API و اعتبار"""
        try:
            import requests
            start_time = time.time()
            
            # بررسی وضعیت API
            response = requests.get(
                "https://api.coinstats.app/v1/status",
                headers={"X-API-KEY": self.api_key},
                timeout=10
            )
            latency = (time.time() - start_time) * 1000  # میلی‌ثانیه
            
            if response.status_code == 200:
                self.metrics["api"]["status"] = "ok"
                self.metrics["api"]["latency"] = round(latency, 1)
                self.metrics["api"]["last_check"] = datetime.utcnow().isoformat()
                
                # بررسی اعتبار
                credits_resp = requests.get(
                    "https://api.coinstats.app/v1/usage/credits",
                    headers={"X-API-KEY": self.api_key},
                    timeout=10
                )
                if credits_resp.status_code == 200:
                    data = credits_resp.json()
                    self.metrics["credits"]["remaining"] = data.get("remainingCredits", 0)
                    self.metrics["credits"]["total"] = data.get("totalCredits", 10000)
                    self.metrics["credits"]["percent"] = round(
                        (self.metrics["credits"]["remaining"] / self.metrics["credits"]["total"]) * 100, 1
                    )
            else:
                self.metrics["api"]["status"] = "error"
                self.metrics["api"]["latency"] = round(latency, 1)
                
        except Exception as e:
            self.metrics["api"]["status"] = "unreachable"
            self._add_log("WARNING", f"⚠️ API در دسترس نیست: {str(e)}")
    
    def _update_health_status(self):
        """به‌روزرسانی وضعیت کلی سلامت"""
        status = "healthy"
        reasons = []
        
        # بررسی RAM
        ram_percent = self.metrics["ram"]["percent"]
        if ram_percent >= self.config["thresholds"]["ram_critical"]:
            status = "critical"
            reasons.append(f"RAM: {ram_percent}% (بحرانی)")
            self._add_log("CRITICAL", f"🔴 RAM به {ram_percent}% رسید! (آستانه: {self.config['thresholds']['ram_critical']}%)")
        elif ram_percent >= self.config["thresholds"]["ram_warning"]:
            if status != "critical":
                status = "degraded"
            reasons.append(f"RAM: {ram_percent}% (هشدار)")
            self._add_log("WARNING", f"🟡 RAM به {ram_percent}% رسید (آستانه: {self.config['thresholds']['ram_warning']}%)")
        
        # بررسی اعتبار
        credit_percent = self.metrics["credits"]["percent"]
        if credit_percent <= self.config["thresholds"]["credit_critical"] and credit_percent > 0:
            if status != "critical":
                status = "critical"
            reasons.append(f"اعتبار: {credit_percent}% (بحرانی)")
            self._add_log("CRITICAL", f"🔴 اعتبار به {credit_percent}% رسید! (آستانه: {self.config['thresholds']['credit_critical']}%)")
        elif credit_percent <= self.config["thresholds"]["credit_warning"] and credit_percent > 0:
            if status != "critical":
                status = "degraded"
            reasons.append(f"اعتبار: {credit_percent}% (هشدار)")
            self._add_log("WARNING", f"🟡 اعتبار به {credit_percent}% رسید (آستانه: {self.config['thresholds']['credit_warning']}%)")
        elif credit_percent == 0:
            status = "critical"
            reasons.append("اعتبار: ۰% (تمام شده)")
            self._add_log("CRITICAL", "🔴 اعتبار تمام شد!")
        
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
            """صفحه‌ی اصلی داشبورد"""
            return render_template('health_dashboard.html', config=self.config)
        
        @self.app.route('/api/metrics')
        def get_metrics():
            """دریافت متریک‌ها به‌صورت JSON"""
            return jsonify({
                "metrics": self.metrics,
                "config": self.config,
                "logs": self.logs[-20:]  # آخرین ۲۰ لاگ
            })
        
        @self.app.route('/api/logs')
        def get_logs():
            """دریافت لاگ‌ها به‌صورت JSON"""
            count = request.args.get('count', 50, type=int)
            return jsonify(self.logs[-count:])
        
        @self.app.route('/api/logs', methods=['DELETE'])
        def clear_logs():
            """پاک کردن همه‌ی لاگ‌ها"""
            self.logs.clear()
            self._add_log("INFO", "🗑️ لاگ‌ها پاک شدند")
            return jsonify({"status": "ok", "message": "لاگ‌ها پاک شدند"})
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            """دریافت تنظیمات فعلی"""
            return jsonify(self.config)
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            """به‌روزرسانی تنظیمات"""
            data = request.json
            if not data:
                return jsonify({"error": "بدون داده"}), 400
            
            # به‌روزرسانی recursive
            def update_nested(d, keys, value):
                for key in keys[:-1]:
                    d = d.setdefault(key, {})
                d[keys[-1]] = value
            
            for key_path, value in data.items():
                keys = key_path.split('.')
                update_nested(self.config, keys, value)
                self._add_log("INFO", f"⚙️ تنظیمات به‌روزرسانی شد: {key_path} = {value}")
            
            # اگر حالت dashboard تغییر کرد
            if "dashboard_mode" in data or "mother_health.dashboard_mode" in data:
                self._add_log("INFO", f"🔄 حالت داشبورد تغییر کرد: {self.config['dashboard_mode']}")
            
            return jsonify({"status": "ok", "config": self.config})
        
        @self.app.route('/api/health')
        def health():
            """وضعیت خلاصه‌ی سلامت (برای هسته)"""
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
        """متوقف کردن مادر"""
        self.running = False
        self._add_log("INFO", "🛑 MotherHealth متوقف شد")
    
    def run(self):
        """اجرای سرور Flask"""
        self._add_log("INFO", f"🌐 داشبورد در http://localhost:{self.port} در دسترس است")
        try:
            self.app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)
        except KeyboardInterrupt:
            self.stop()


# ==================== اجرای مستقل برای تست ====================

if __name__ == "__main__":
    import sys
    
    # تنظیم لاگینگ
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s'
    )
    
    API_KEY = "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw="
    
    # ایجاد نمونه
    health = MotherHealth(
        api_key=API_KEY,
        port=5000,
        check_interval=10  # هر ۱۰ ثانیه یک‌بار برای تست سریع‌تر
    )
    
    print("=" * 50)
    print("🩺 MotherHealth v2.0 (MVP)")
    print("=" * 50)
    print(f"📊 پورت: {health.port}")
    print(f"🔄 حالت: {health.config['dashboard_mode']}")
    print(f"⏱️ فاصله‌ی بررسی: {health.check_interval} ثانیه")
    print("=" * 50)
    print("🌐 داشبورد را در مرورگر باز کن:")
    print(f"   http://localhost:{health.port}")
    print("=" * 50)
    print("💡 برای تست: Ctrl+C برای خروج")
    print("=" * 50)
    
    try:
        health.run()
    except KeyboardInterrupt:
        print("\n🛑 در حال خروج...")
        health.stop()
        sys.exit(0)
