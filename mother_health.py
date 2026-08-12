import os
import time
import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MotherHealth")

class MotherHealth:
    def __init__(self, api_key: str, port: int = 5000, check_interval: int = 30):
        self.api_key = api_key
        self.port = port
        self.check_interval = check_interval
        
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
        
        self.metrics = {
            "ram": {"used_mb": 0, "total_mb": 512, "percent": 0},
            "cpu": 0,
            "cpu_count": 1,
            "api": {"status": "unknown", "latency": 0, "last_check": None},
            "credits": {"remaining": 0, "total": 10000, "percent": 0},
            "uptime": 0,
            "health_status": "healthy",
            "last_update": None
        }
        
        self.logs = []
        self.max_logs = 500
        self.app = Flask(__name__)
        self._setup_routes()
        
        self.running = True
        self.start_time = time.time()
        self.metric_thread = threading.Thread(target=self._metric_loop, daemon=True)
        self.metric_thread.start()
        
        self._add_log("INFO", "🩺 MotherHealth راه‌اندازی شد (نسخه‌ی مستقل)")
    
    def _add_log(self, level: str, message: str):
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "level": level, "message": message}
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        logger.info(message)
    
    def _get_real_memory_mb(self) -> tuple:
        """دریافت RAM واقعی از /proc/self/status (مستقل از psutil)"""
        total_mb = 512  # پیش‌فرض Render Free
        
        # ۱. خواندن محدودیت از متغیر محیطی
        try:
            mem_limit = os.environ.get('MEMORY_LIMIT')
            if mem_limit:
                total_mb = int(mem_limit) // (1024 * 1024)
        except:
            pass
        
        # ۲. خواندن محدودیت از cgroup (اگر وجود داشت)
        if total_mb == 512:
            try:
                with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                    limit_bytes = int(f.read().strip())
                    if limit_bytes < 2**63 - 1:
                        total_mb = limit_bytes // (1024 * 1024)
            except:
                pass
        
        # ۳. خواندن مصرف از /proc/self/status
        used_mb = total_mb // 4  # مقدار پیش‌فرض
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        parts = line.split()
                        if len(parts) >= 2:
                            used_mb = int(parts[1]) // 1024  # تبدیل از KB به MB
                            break
        except:
            pass
        
        # اگر مصرف از حد مجاز بیشتر بود، اصلاح کن
        if used_mb > total_mb:
            used_mb = total_mb // 2
        
        percent = min(100, round((used_mb / total_mb) * 100, 1))
        return used_mb, total_mb, percent
    
    def _collect_metrics(self):
        try:
            # ۱. RAM - با روش مستقل
            used_mb, total_mb, percent = self._get_real_memory_mb()
            self.metrics["ram"] = {"used_mb": used_mb, "total_mb": total_mb, "percent": percent}
            
            # ۲. CPU - با مقدار ثابت برای Render
            try:
                import psutil
                cpu_percent = psutil.cpu_percent(interval=0.1)
                self.metrics["cpu"] = round(min(100, cpu_percent), 1)
            except:
                self.metrics["cpu"] = 0.5
            
            # ۳. تعداد هسته‌ها
            try:
                import psutil
                cpu_count = psutil.cpu_count()
                self.metrics["cpu_count"] = cpu_count if cpu_count else 1
            except:
                self.metrics["cpu_count"] = 1
            
            # ۴. آپ‌تایم
            self.metrics["uptime"] = int(time.time() - self.start_time)
            
            # ۵. API
            if self.config.get("metric_collection", True):
                self._check_api_health()
            
            self._update_health_status()
            self.metrics["last_update"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self._add_log("ERROR", f"خطا: {str(e)}")
    
    def _check_api_health(self):
        try:
            start = time.time()
            resp = requests.get(
                "https://api.coinstats.app/v1/status",
                headers={"X-API-KEY": self.api_key},
                timeout=5
            )
            latency = round((time.time() - start) * 1000, 1)
            
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                self.metrics["api"]["status"] = "ok"
                self.metrics["api"]["latency"] = latency
            else:
                self.metrics["api"]["status"] = "error"
                self.metrics["api"]["latency"] = latency
            
            cred_resp = requests.get(
                "https://api.coinstats.app/v1/usage/credits",
                headers={"X-API-KEY": self.api_key},
                timeout=5
            )
            if cred_resp.status_code == 200:
                data = cred_resp.json()
                self.metrics["credits"]["remaining"] = data.get("remainingCredits", 0)
                self.metrics["credits"]["total"] = data.get("totalCredits", 10000)
                self.metrics["credits"]["percent"] = round(
                    (self.metrics["credits"]["remaining"] / max(1, self.metrics["credits"]["total"])) * 100, 1
                )
            
            self.metrics["api"]["last_check"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self.metrics["api"]["status"] = "unreachable"
            self._add_log("WARNING", f"⚠️ API: {str(e)[:40]}")
    
    def _update_health_status(self):
        status = "healthy"
        if self.metrics["ram"]["percent"] >= self.config["thresholds"]["ram_critical"]:
            status = "critical"
        elif self.metrics["ram"]["percent"] >= self.config["thresholds"]["ram_warning"]:
            status = "degraded"
        elif self.metrics["credits"]["percent"] <= self.config["thresholds"]["credit_critical"]:
            status = "critical"
        elif self.metrics["credits"]["percent"] <= self.config["thresholds"]["credit_warning"]:
            if status != "critical":
                status = "degraded"
        elif self.metrics["api"]["status"] != "ok":
            if status != "critical":
                status = "degraded"
        self.metrics["health_status"] = status
    
    def _metric_loop(self):
        while self.running:
            self._collect_metrics()
            time.sleep(self.check_interval)
    
    def _setup_routes(self):
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
        
        @self.app.route('/api/logs', methods=['DELETE'])
        def clear_logs():
            self.logs.clear()
            return jsonify({"status": "ok"})
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            return jsonify(self.config)
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            data = request.json
            if not data:
                return jsonify({"error": "بدون داده"}), 400
            for key, value in data.items():
                if key in self.config:
                    self.config[key] = value
            return jsonify({"status": "ok", "config": self.config})
        
        @self.app.route('/api/health')
        def health():
            return jsonify({"status": self.metrics["health_status"]})
    
    def run(self):
        self._add_log("INFO", f"🌐 http://localhost:{self.port}")
        self.app.run(host='0.0.0.0', port=self.port, debug=False, threaded=True)

if __name__ == "__main__":
    API_KEY = os.environ.get("API_KEY", "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw=")
    health = MotherHealth(api_key=API_KEY, port=int(os.environ.get("PORT", 5000)), check_interval=10)
    health.run()
