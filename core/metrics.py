# core/metrics.py
# ============================================================
# سیستم جمع‌آوری متریک - نسخه ۸.۰ (رفع وابستگی)
# ============================================================

import time
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MetricsScheduler:
    """
    سیستم جمع‌آوری متریک بدون وابستگی به system
    ✅ داده‌ها را از طریق API می‌گیرد
    """
    
    def __init__(self):
        self._running = False
        self._stop_event = None  # توسط ThreadingManager تنظیم می‌شود
        
        self.metrics_cache: Dict[str, Any] = {}
        self.stats = {
            "collections": 0,
            "errors": 0,
            "last_collection": None
        }
        self.start_time = time.time()
        
        # فواصل
        self.light_interval = 3
        self.medium_interval = 30
        self.heavy_interval = 300
        
        logger.info("✅ MetricsScheduler v8.0 initialized")
    
    def set_stop_event(self, event):
        """تنظیم Event برای کنترل Stop"""
        self._stop_event = event
    
    def start(self):
        """شروع Scheduler"""
        if self._running:
            return
        
        self._running = True
        logger.info("🔄 Metrics Scheduler started")
        
        # جمع‌آوری اولیه
        try:
            self._collect_light_metrics()
            self._collect_medium_metrics()
            self._collect_heavy_metrics()
        except Exception as e:
            logger.error(f"❌ Initial collection error: {e}")
        
        # حلقه اصلی
        last_light = time.time()
        last_medium = time.time()
        last_heavy = time.time()
        
        while self._running and not (self._stop_event and self._stop_event.is_set()):
            try:
                now = time.time()
                
                if now - last_light >= self.light_interval:
                    self._collect_light_metrics()
                    last_light = now
                
                if now - last_medium >= self.medium_interval:
                    self._collect_medium_metrics()
                    last_medium = now
                
                if now - last_heavy >= self.heavy_interval:
                    self._collect_heavy_metrics()
                    last_heavy = now
                
                self.stats["last_collection"] = datetime.now().isoformat()
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                self.stats["errors"] += 1
                time.sleep(5)
        
        logger.info("⏹️ Metrics Scheduler stopped")
    
    def stop(self):
        """متوقف کردن"""
        self._running = False
        logger.info("⏹️ Metrics Scheduler stopping")
    
    # ============================================================
    # جمع‌آوری‌کننده‌ها (بدون وابستگی به system)
    # ============================================================
    
    def _collect_light_metrics(self):
        """CPU, RAM, Uptime"""
        try:
            cpu = psutil.cpu_percent(interval=0.2)
            ram = psutil.virtual_memory().percent
            
            elapsed = int(time.time() - self.start_time)
            if elapsed < 60:
                uptime = f"{elapsed}s"
            elif elapsed < 3600:
                uptime = f"{elapsed // 60}m {elapsed % 60}s"
            else:
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                uptime = f"{hours}h {minutes}m"
            
            self.metrics_cache["cpu"] = {
                "value": cpu,
                "timestamp": datetime.now().isoformat()
            }
            self.metrics_cache["ram"] = {
                "value": ram,
                "timestamp": datetime.now().isoformat()
            }
            self.metrics_cache["uptime"] = {
                "value": uptime,
                "timestamp": datetime.now().isoformat()
            }
            self.stats["collections"] += 1
            
        except Exception as e:
            logger.error(f"❌ Light metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_medium_metrics(self):
        """قیمت‌ها, API, مدل - با استفاده از API کلاینت"""
        try:
            # ✅ استفاده از API کلاینت (بدون وابستگی به system)
            from api.coinstats_client import coinstats_client
            from models.manager.model_manager import ModelManager
            
            # قیمت‌ها
            btc = coinstats_client.get_coin("bitcoin")
            if btc and "error" not in btc:
                self.metrics_cache["btc_price"] = {
                    "value": btc.get("price", 0),
                    "change_24h": btc.get("priceChange1d", 0),
                    "timestamp": datetime.now().isoformat()
                }
            
            eth = coinstats_client.get_coin("ethereum")
            if eth and "error" not in eth:
                self.metrics_cache["eth_price"] = {
                    "value": eth.get("price", 0),
                    "change_24h": eth.get("priceChange1d", 0),
                    "timestamp": datetime.now().isoformat()
                }
            
            # API Status
            status = coinstats_client.get_status()
            api_status = status.get("status", "unknown") if status else "unknown"
            self.metrics_cache["api_status"] = {
                "value": api_status,
                "timestamp": datetime.now().isoformat()
            }
            
            # Credits
            credits = coinstats_client.get_credits()
            api_credits = credits.get("remainingCredits", 0) if credits else 0
            self.metrics_cache["api_credits"] = {
                "value": api_credits,
                "timestamp": datetime.now().isoformat()
            }
            
            # Model Status
            # ✅ استفاده از ModelManager بدون وابستگی به system
            model_manager = ModelManager(coinstats_client)
            loaded = model_manager.current_model is not None
            version = model_manager.current_version or "N/A"
            self.metrics_cache["model_status"] = {
                "value": {"loaded": loaded, "version": version},
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"Medium metrics error: {e}")
    
    def _collect_heavy_metrics(self):
        """سایر متریک‌ها"""
        try:
            from api.coinstats_client import coinstats_client
            from database import health_check
            
            # Fear & Greed
            fg = coinstats_client.get_fear_greed(use_cache=True)
            if fg and "now" in fg:
                self.metrics_cache["fear_greed"] = {
                    "value": fg["now"].get("value", 50),
                    "classification": fg["now"].get("value_classification", "Neutral"),
                    "timestamp": datetime.now().isoformat()
                }
            
            # BTC Dominance
            dominance = coinstats_client.get_btc_dominance(use_cache=True)
            if dominance:
                self.metrics_cache["btc_dominance"] = {
                    "value": dominance.get("dominance", 50),
                    "timestamp": datetime.now().isoformat()
                }
            
            # Databases
            health = health_check()
            dbs = {}
            for name, info in health.items():
                dbs[name] = info.get("connected", False)
            self.metrics_cache["databases"] = {
                "value": dbs,
                "timestamp": datetime.now().isoformat()
            }
            
            # Disk Space
            usage = psutil.disk_usage('/')
            disk = {
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent
            }
            self.metrics_cache["disk_space"] = {
                "value": disk,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"Heavy metrics error: {e}")
    
    # ============================================================
    # API
    # ============================================================
    
    def get_metrics(self) -> Dict:
        return {
            "metrics": self.metrics_cache.copy(),
            "stats": self.stats.copy(),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_summary(self) -> Dict:
        return {
            "status": "running" if self._running else "stopped",
            "total_collections": self.stats["collections"],
            "errors": self.stats["errors"],
            "metrics_count": len(self.metrics_cache),
            "last_collection": self.stats["last_collection"]
        }
    
    def get_alert_metrics(self) -> Dict:
        cache = self.metrics_cache
        return {
            "cpu": cache.get("cpu", {}).get("value", 0),
            "ram": cache.get("ram", {}).get("value", 0),
            "api_status": cache.get("api_status", {}).get("value", "unknown"),
            "api_credits": cache.get("api_credits", {}).get("value", 0),
            "model_loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
            "model_accuracy": None,
            "databases": cache.get("databases", {}).get("value", {}),
            "uptime": cache.get("uptime", {}).get("value", "0s"),
        }
    
    def get_dashboard_metrics(self) -> Dict:
        cache = self.metrics_cache
        return {
            "system": {
                "cpu": cache.get("cpu", {}).get("value", 0),
                "ram": cache.get("ram", {}).get("value", 0),
                "uptime": cache.get("uptime", {}).get("value", "0s"),
            },
            "prices": {
                "btc": cache.get("btc_price", {}).get("value", 0),
                "eth": cache.get("eth_price", {}).get("value", 0),
            },
            "api": {
                "status": cache.get("api_status", {}).get("value", "unknown"),
                "credits": cache.get("api_credits", {}).get("value", 0)
            },
            "market": {
                "fear_greed": cache.get("fear_greed", {}).get("value", 50),
                "fear_greed_label": cache.get("fear_greed", {}).get("classification", "Neutral"),
                "btc_dominance": cache.get("btc_dominance", {}).get("value", 50),
            },
            "model": {
                "loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
                "version": cache.get("model_status", {}).get("value", {}).get("version", "N/A"),
            },
            "disk": cache.get("disk_space", {}).get("value", {}),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_health(self) -> Dict:
        cache = self.metrics_cache
        cpu = cache.get("cpu", {}).get("value", 0)
        ram = cache.get("ram", {}).get("value", 0)
        
        cpu_status = "healthy" if cpu < 70 else "warning" if cpu < 90 else "critical"
        ram_status = "healthy" if ram < 70 else "warning" if ram < 90 else "critical"
        
        return {
            "status": "ok" if cpu_status == "healthy" and ram_status == "healthy" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {"status": cpu_status, "value": round(cpu, 1)},
                "ram": {"status": ram_status, "value": round(ram, 1)},
            }
        }


# ایجاد نمونه
metrics_scheduler = MetricsScheduler()
