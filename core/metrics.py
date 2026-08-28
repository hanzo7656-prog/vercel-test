# core/metrics.py
# ============================================================
# سیستم جمع‌آوری متریک با APScheduler (تنظیم شده برای Gunicorn)
# نسخه ۳.۰ - پایدار در محیط Gunicorn
# ============================================================

import time
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class MetricsScheduler:
    """
    سیستم جمع‌آوری متریک با APScheduler
    تنظیم شده برای اجرا در محیط Gunicorn
    """
    
    def __init__(self):
        # ============================================================
        # تنظیمات APScheduler برای Gunicorn
        # ============================================================
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(2)  # ✅ ۲ ترد برای اجرای همزمان
        }
        job_defaults = {
            'coalesce': False,           # اگر چندین اجرا همزمان شده باشند، همه اجرا شوند
            'max_instances': 1,          # حداکثر یک نمونه از هر job
            'misfire_grace_time': 15,    # ۱۵ ثانیه مهلت برای اجرای دیرهنگام
        }
        
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        self.metrics_cache: Dict[str, Any] = {}
        self.stats = {
            "collections": 0,
            "errors": 0,
            "last_collection": None,
        }
        self.start_time = time.time()
        self._is_running = False
        
        # تنظیم jobها
        self._setup_jobs()
        
        logger.info("✅ MetricsScheduler v3.0 initialized (APScheduler + Gunicorn compatible)")
    
    def _setup_jobs(self):
        """تنظیم jobهای زمان‌بندی"""
        
        # ۱. CPU و RAM (هر ۳ ثانیه)
        self.scheduler.add_job(
            self._collect_light_metrics,
            trigger=IntervalTrigger(seconds=3),
            id="light_metrics",
            replace_existing=True
        )
        
        # ۲. API Status و Credits (هر ۳۰ ثانیه)
        self.scheduler.add_job(
            self._collect_medium_metrics,
            trigger=IntervalTrigger(seconds=30),
            id="medium_metrics",
            replace_existing=True
        )
        
        # ۳. دیتابیس و دیسک (هر ۵ دقیقه)
        self.scheduler.add_job(
            self._collect_heavy_metrics,
            trigger=IntervalTrigger(seconds=300),
            id="heavy_metrics",
            replace_existing=True
        )
        
        logger.info("✅ Jobs configured: light(3s), medium(30s), heavy(300s)")
    
    # ============================================================
    # جمع‌آوری‌کننده‌ها
    # ============================================================
    
    def _collect_light_metrics(self):
        """جمع‌آوری متریک‌های سبک (CPU, RAM, uptime)"""
        try:
            cpu = psutil.cpu_percent(interval=0.2)
            ram = psutil.virtual_memory().percent
            
            self.metrics_cache["cpu"] = {
                "value": cpu,
                "timestamp": datetime.now().isoformat(),
                "level": "light"
            }
            self.metrics_cache["ram"] = {
                "value": ram,
                "timestamp": datetime.now().isoformat(),
                "level": "light"
            }
            
            elapsed = int(time.time() - self.start_time)
            if elapsed < 60:
                uptime = f"{elapsed}s"
            elif elapsed < 3600:
                uptime = f"{elapsed // 60}m {elapsed % 60}s"
            else:
                hours = elapsed // 3600
                minutes = (elapsed % 3600) // 60
                uptime = f"{hours}h {minutes}m"
            
            self.metrics_cache["uptime"] = {
                "value": uptime,
                "timestamp": datetime.now().isoformat(),
                "level": "light"
            }
            
            self.stats["collections"] += 1
            self.stats["last_collection"] = datetime.now().isoformat()
            
            logger.debug(f"📊 CPU: {cpu}%, RAM: {ram}%")
            
        except Exception as e:
            logger.error(f"❌ Light metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_medium_metrics(self):
        """جمع‌آوری متریک‌های متوسط (API, Model)"""
        try:
            # API Status
            try:
                from core.system import system
                status = system.api.get_status()
                api_status = status.get("status", "unknown") if status else "unknown"
            except Exception as e:
                logger.debug(f"API status error: {e}")
                api_status = "error"
            
            self.metrics_cache["api_status"] = {
                "value": api_status,
                "timestamp": datetime.now().isoformat(),
                "level": "medium"
            }
            
            # API Credits
            try:
                from core.system import system
                credits = system.api.get_credits()
                api_credits = credits.get("remainingCredits", 0) if credits else 0
            except:
                api_credits = 0
            
            self.metrics_cache["api_credits"] = {
                "value": api_credits,
                "timestamp": datetime.now().isoformat(),
                "level": "medium"
            }
            
            # Model Status
            try:
                from core.system import system
                if system.model_manager:
                    loaded = system.model_manager.current_model is not None
                    version = system.model_manager.current_version or "N/A"
                else:
                    loaded = False
                    version = "N/A"
            except:
                loaded = False
                version = "N/A"
            
            self.metrics_cache["model_status"] = {
                "value": {"loaded": loaded, "version": version},
                "timestamp": datetime.now().isoformat(),
                "level": "medium"
            }
            
            logger.debug(f"📊 API: {api_status}, Credits: {api_credits}")
            
        except Exception as e:
            logger.error(f"❌ Medium metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_heavy_metrics(self):
        """جمع‌آوری متریک‌های سنگین (Database, Disk)"""
        try:
            # Database Size
            try:
                from database import get_primary
                db = get_primary()
                if db and db.is_connected():
                    result = db.execute("""
                        SELECT pg_database_size(current_database()) / 1024 / 1024 as size_mb
                    """)
                    db_size = result[0].get('size_mb', 0) if result else 0
                else:
                    db_size = 0
            except:
                db_size = 0
            
            self.metrics_cache["database_size"] = {
                "value": db_size,
                "timestamp": datetime.now().isoformat(),
                "level": "heavy"
            }
            
            # Disk Space
            try:
                usage = psutil.disk_usage('/')
                disk = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                }
            except:
                disk = {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}
            
            self.metrics_cache["disk_space"] = {
                "value": disk,
                "timestamp": datetime.now().isoformat(),
                "level": "heavy"
            }
            
            # Databases Status
            try:
                from database import health_check
                health = health_check()
                dbs = {}
                for name, info in health.items():
                    if name == "postgresql":
                        dbs["postgresql"] = info.get("connected", False)
                    elif name == "redis":
                        dbs["redis"] = info.get("connected", False)
                    elif name == "sqlite":
                        dbs["sqlite"] = info.get("connected", False)
            except:
                dbs = {"postgresql": False, "redis": False, "sqlite": False}
            
            self.metrics_cache["databases"] = {
                "value": dbs,
                "timestamp": datetime.now().isoformat(),
                "level": "heavy"
            }
            
            logger.debug(f"📊 DB Size: {db_size}MB, Disk: {disk.get('percent', 0)}%")
            
        except Exception as e:
            logger.error(f"❌ Heavy metrics error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # کنترل Start/Stop
    # ============================================================
    
    def start(self):
        """شروع Scheduler"""
        if self._is_running:
            logger.info("⏳ Scheduler already running")
            return
        
        # ✅ اطمینان از اینکه jobها ثبت شده‌اند
        self._setup_jobs()
        
        self.scheduler.start()
        self._is_running = True
        logger.info("✅ Metrics Scheduler (APScheduler) started")
        
        # جمع‌آوری اولیه
        self._collect_light_metrics()
        self._collect_medium_metrics()
        self._collect_heavy_metrics()
    
    def stop(self):
        """متوقف کردن Scheduler"""
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("⏹️ Metrics Scheduler stopped")
    
    # ============================================================
    # API
    # ============================================================
    
    def get_metrics(self) -> Dict:
        return {
            "metrics": self.metrics_cache,
            "stats": self.stats,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_summary(self) -> Dict:
        return {
            "status": "running" if self._is_running else "stopped",
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
            "api": {
                "status": cache.get("api_status", {}).get("value", "unknown"),
                "credits": cache.get("api_credits", {}).get("value", 0)
            },
            "model": {
                "loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
                "version": cache.get("model_status", {}).get("value", {}).get("version", "N/A"),
            },
            "database": {
                "size_mb": cache.get("database_size", {}).get("value", 0),
                "status": cache.get("databases", {}).get("value", {})
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
        
        api = cache.get("api_status", {}).get("value", "unknown")
        api_status = "healthy" if api == "ok" else "degraded" if api == "degraded" else "unhealthy"
        
        return {
            "status": "ok" if cpu_status == "healthy" and ram_status == "healthy" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {"status": cpu_status, "value": round(cpu, 1)},
                "ram": {"status": ram_status, "value": round(ram, 1)},
                "api": {"status": api_status},
            }
        }


# ============================================================
# ایجاد نمونه Singleton
# ============================================================

metrics_scheduler = MetricsScheduler()
