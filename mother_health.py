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
        
        self._add_log("INFO", "🩺 MotherHealth راه‌اندازی شد (نسخه‌ی cgroup)")
    
    def _add_log(self, level: str, message: str):
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "level": level, "message": message}
        self.logs.append(log_entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        logger.info(message)
    
    def _get_container_memory_mb(self) -> int:
        """دریافت محدودیت RAM واقعی کانتینر"""
        try:
            with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                limit_bytes = int(f.read().strip())
                if limit_bytes < 2**63 - 1:
                    return limit_bytes // (1024 * 1024)
        except:
            pass
        
        try:
            mem_limit = os.environ.get('MEMORY_LIMIT')
            if mem_limit:
                return int(mem_limit) // (1024 * 1024)
        except:
            pass
        
        return 512  # پیش‌فرض Render Free Tier
    
    def _get_memory_usage_mb(self) -> tuple:
        """دریافت مصرف RAM واقعی"""
        total_mb = self._get_container_memory_mb()
        
        try:
            with open('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'r') as f:
                used_bytes = int(f.read().strip())
                used_mb = used_bytes // (1024 * 1024)
        except:
            try:
                import psutil
                used_mb = psutil.virtual_memory().used // (1024 ** 2)
            except:
                used_mb = total_mb // 4
        
        percent = min(100, round((used_mb / total_mb) * 100, 1))
        return used_mb, total_mb, percent
    
    def _collect_metrics(self):
        try:
            # RAM
            used_mb, total_mb, percent = self._get_memory_usage_mb()
            self.metrics["ram"] = {"used_mb": used_mb, "total_mb": total_mb, "percent": percent}
            
            # CPU
            try:
                import psutil
                self.metrics["cpu"] = round(min(100, psutil.cpu_percent(interval=0.2)), 1)
            except:
                self.metrics["cpu"] = 0.5
            
            # Uptime
            self.metrics["uptime"] = int(time.time() - self.start_time)
            
            # API
            if self.config.get("metric_collection", True):
                self._check_api_health()
            
            self._update_health_status()
            self.metrics["last_update"] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self._add_log("ERROR", f"خطا در جمع‌آوری متریک: {str(e)}")
    
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
            
            # Credits
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
