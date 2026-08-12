"""
ماژول سلامت مادر (MotherHealth) - نسخه‌ی نهایی بدون خطا
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
import requests

# تنظیم لاگر
logger = logging.getLogger("MotherHealth")

class MotherHealth:
    """
    کلاس اصلی سلامت مادر - بدون خطا و با تشخیص صحیح RAM
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
            "ram": {"used_mb": 0, "total_mb": 512, "percent": 0},
            "cpu": 0,
            "cpu_count": 1,  # مقدار پیش‌فرض برای Render
            "api": {"status": "unknown", "latency": 0, "last_check": None},
            "credits": {"remaining": 0, "total": 10000, "percent": 0},
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
        
        self._add_log("INFO", "🩺 MotherHealth راه‌اندازی شد (نسخه‌ی بدون خطا)")
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
    
    # ==================== تشخیص RAM در کانتینر ====================
    
    def _get_container_memory_limit(self) -> int:
        """دریافت محدودیت RAM کانتینر (به مگابایت)"""
        try:
            # روش ۱: از cgroup v1
            with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                limit_bytes = int(f.read().strip())
                if limit_bytes < 2**63 - 1:
                    return limit_bytes // (1024 * 1024)
        except:
            pass
        
        try:
            # روش ۲: از متغیر محیطی
            mem_limit = os.environ.get('MEMORY_LIMIT')
            if mem_limit:
                return int(mem_limit) // (1024 * 1024)
        except:
            pass
        
        try:
            # روش ۳: از psutil
            mem = psutil.virtual_memory()
            return mem.total // (1024 ** 2)
        except:
            return 512  # پیش‌فرض Render Free Tier
    
    def _get_memory_usage(self) -> tuple:
        """دریافت مصرف RAM (used_mb, total_mb, percent)"""
        total_mb = self._get_container_memory_limit()
        
        try:
            # مصرف واقعی از cgroup
            with open('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'r') as f:
                used_bytes = int(f.read().strip())
                used_mb = used_bytes // (1024 * 1024)
        except:
            try:
                # از psutil
                mem = psutil.virtual_memory()
                used_mb = mem.used // (1024 ** 2)
            except:
                used_mb = total_mb // 4  # تخمین
        
        percent = min(100, round((used_mb / total_mb) * 100, 1))
        return used_mb, total_mb, percent
    
    # ==================== جمع‌آوری متریک ====================
    
    def _collect_metrics(self):
        """جمع‌آوری همه‌ی متریک‌ها"""
        try:
            # ۱. RAM - با تشخیص دقیق کانتینر
            used_mb, total_mb, percent = self._get_memory_usage()
            self.metrics["ram"] = {
                "used_mb": used_mb,
                "total_mb": total_mb,
                "percent": percent
            }
            
            # ۲. CPU
            try:
                cpu_percent = psutil.cpu_percent(interval=0.2)
                self.metrics["cpu"] = round(min(100, cpu_percent), 1)
            except:
                self.metrics["cpu"] = 0.5
            
            # ۳. تعداد هسته‌های CPU (با مقدار پیش‌فرض برای Render)
            try:
                cpu_count = psutil.cpu_count()
                self.metrics["cpu_count"] = cpu_count if cpu_count else 1
            except:
                self.metrics["cpu_count"] = 1
            
            # ۴. آپ‌تایم
            self.metrics["uptime"] = int(time.time() - self.start_time)
            
            # ۵. API Status و Credits
            if self.config.get("metric_collection", True):
                self._check_api_health()
            
            # ۶. به‌روزرسانی وضعیت کلی سلامت
            self._update_health_status()
            
            self.metrics["last_update"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self._add_log("ERROR", f"خطا در جمع‌آوری متریک: {str(e)}")
    
    def _check_api_health(self):
        """بررسی سلامت API و اعتبار با درخواست مستقیم"""
        try:
            # ۱. بررسی وضعیت API
            start_time = time.time()
            status_resp = requests.get(
                "https://api.coinstats.app/v1/status",
                headers={"X-API-KEY": self.api_key},
                timeout=5
            )
            latency = round((time.time() - start_time) * 1000, 1)
            
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                if status_data.get("status") == "ok":
                    self.metrics["api"]["status"] = "ok"
                    self.metrics["api"]["latency"] = latency
                else:
                    self.metrics["api"]["status"] = "error"
                    self.metrics["api"]["latency"] = latency
            else:
                self.metrics["api"]["status"] = "error"
                self.metrics["api"]["latency"] = latency
            
            # ۲. بررسی اعتبار
            credits_resp = requests.get(
                "https://api.coinstats.app/v1/usage/credits",
                headers={"X-API-KEY": self.api_key},
                timeout=5
            )
            if credits_resp.status_code == 200:
                credits_data = credits_resp.json()
                self.metrics["credits"]["remaining"] = credits_data.get("remainingCredits", 0)
                self.metrics["credits"]["total"] = credits_data.get("totalCredits", 10000)
                self.metrics["credits"]["percent"] = round(
                    (self.metrics["credits"]["remaining"] / max(1, self.metrics["credits"]["total"])) * 100, 1
                )
            
            self.metrics["api"]["last_check"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self.metrics["api"]["status"] = "unreachable"
            self._add_log("WARNING", f"⚠️ API در دسترس نیست: {str(e)[:50]}")
    
    def _update_health_status(self):
        """به‌روزرسانی وضعیت کلی سلامت"""
        status = "healthy"
        
        # بررسی RAM
        ram_percent = self.metrics["ram"]["percent"]
        if ram_percent >= self.config["thresholds"]["ram_critical"]:
            status = "critical"
            self._add_log("CRITICAL", f"🔴 RAM به {ram_percent}% رسید!")
        elif ram_percent >= self.config["thresholds"]["ram_warning"]:
            status = "degraded"
            self._add_log("WARNING", f"🟡 RAM به {ram_percent}% رسید")
        
        # بررسی اعتبار
        credit_percent = self.metrics["credits"]["percent"]
        if credit_percent <= self.config["thresholds"]["credit_critical"] and credit_percent > 0:
            status = "critical"
            self._add_log("CRITICAL", f"🔴 اعتبار به {credit_percent}% رسید!")
        elif credit_percent <= self.config["thresholds"]["credit_warning"] and credit_percent > 0:
            if status != "critical":
                status = "degraded"
            self._add_log("WARNING", f"🟡 اعتبار به {credit_percent}% رسید")
        
        # بررسی API
        if self.metrics["api"]["status"] != "ok":
            if status != "critical":
                status = "degraded"
        
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
        check_interval=10
    )
    
    print("=" * 50)
    print("🩺 MotherHealth v2.0 (نسخه‌ی بدون خطا)")
    print("=" * 50)
    print(f"📊 پورت: {health.port}")
    print(f"🔄 حالت: {health.config['dashboard_mode']}")
    print("=" * 50)
    print("🌐 داشبورد:")
    print(f"   http://localhost:{health.port}")
    print("=" * 50)
    
    try:
        health.run()
    except KeyboardInterrupt:
        print("\n🛑 در حال خروج...")
        health.stop()
        sys.exit(0)
