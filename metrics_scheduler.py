# metrics_scheduler.py
# ============================================================
# سیستم زمان‌بندی هوشمند برای جمع‌آوری متریک
# ============================================================

import time
import threading
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MetricLevel(Enum):
    LIGHT = "light"      # هر ۵ ثانیه
    MEDIUM = "medium"    # هر ۳۰ ثانیه
    HEAVY = "heavy"      # هر ۵ دقیقه


@dataclass
class MetricConfig:
    name: str
    level: MetricLevel
    interval: int
    enabled: bool = True
    last_collected: Optional[float] = None
    last_value: Any = None


class MetricsScheduler:
    """
    سیستم جامع جمع‌آوری متریک با زمان‌بندی هوشمند
    جایگزین MetricsCollector و SystemMonitor
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # تنظیمات متریک‌ها
        self.configs = self._load_configs()
        
        # کش آخرین مقادیر
        self.metrics_cache: Dict[str, Any] = {}
        
        # تاریخچه
        self.history: List[Dict] = []
        self.max_history = 10000
        
        # آمار عملکرد
        self.stats = {
            "collections": 0,
            "errors": 0,
            "last_collection": None,
            "collections_by_level": {
                "light": 0,
                "medium": 0,
                "heavy": 0
            }
        }
        
        # مقدار شروع برای uptime
        self.start_time = time.time()
    
    def _load_configs(self) -> Dict[str, MetricConfig]:
        """بارگذاری تنظیمات از فایل یا پیش‌فرض"""
        return {
            # سبک (هر ۵ ثانیه)
            "cpu": MetricConfig("cpu", MetricLevel.LIGHT, 5),
            "ram": MetricConfig("ram", MetricLevel.LIGHT, 5),
            "uptime": MetricConfig("uptime", MetricLevel.LIGHT, 5),
            "process_count": MetricConfig("process_count", MetricLevel.LIGHT, 5),
            
            # متوسط (هر ۳۰ ثانیه)
            "api_status": MetricConfig("api_status", MetricLevel.MEDIUM, 30),
            "api_credits": MetricConfig("api_credits", MetricLevel.MEDIUM, 30),
            "model_status": MetricConfig("model_status", MetricLevel.MEDIUM, 30),
            "active_users": MetricConfig("active_users", MetricLevel.MEDIUM, 30),
            
            # سنگین (هر ۵ دقیقه)
            "database_size": MetricConfig("database_size", MetricLevel.HEAVY, 300),
            "disk_space": MetricConfig("disk_space", MetricLevel.HEAVY, 300),
            "error_logs": MetricConfig("error_logs", MetricLevel.HEAVY, 300),
            "full_health": MetricConfig("full_health", MetricLevel.HEAVY, 300),
            "model_accuracy": MetricConfig("model_accuracy", MetricLevel.HEAVY, 300),
        }
    
    def start(self):
        """شروع زمان‌بند"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("✅ Metrics Scheduler started")
    
    def stop(self):
        """متوقف کردن زمان‌بند"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("⏹️ Metrics Scheduler stopped")
    
    def _scheduler_loop(self):
        """حلقه اصلی زمان‌بندی (هر ۱ ثانیه چک می‌کند)"""
        while self._running:
            try:
                now = time.time()
                
                for name, config in self.configs.items():
                    if not config.enabled:
                        continue
                    
                    if (config.last_collected is None or 
                        now - config.last_collected >= config.interval):
                        
                        self._collect_metric(name, config)
                        config.last_collected = now
                        self.stats["collections"] += 1
                        self.stats["collections_by_level"][config.level.value] += 1
                
                self.stats["last_collection"] = datetime.now().isoformat()
                time.sleep(0.1)  # هر ۱۰۰ میلی‌ثانیه چک می‌کند
                
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                self.stats["errors"] += 1
                time.sleep(1)
    
    def _collect_metric(self, name: str, config: MetricConfig):
        """جمع‌آوری یک متریک خاص"""
        try:
            value = None
            
            # تابع جمع‌آوری مناسب
            collectors = {
                "cpu": self._collect_cpu,
                "ram": self._collect_ram,
                "uptime": self._collect_uptime,
                "process_count": self._collect_process_count,
                "api_status": self._collect_api_status,
                "api_credits": self._collect_api_credits,
                "model_status": self._collect_model_status,
                "active_users": self._collect_active_users,
                "database_size": self._collect_database_size,
                "disk_space": self._collect_disk_space,
                "error_logs": self._collect_error_logs,
                "full_health": self._collect_full_health,
                "model_accuracy": self._collect_model_accuracy,
            }
            
            if name in collectors:
                value = collectors[name]()
            
            if value is not None:
                self.metrics_cache[name] = {
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "level": config.level.value
                }
                self._add_to_history(name, value)
                
        except Exception as e:
            logger.error(f"❌ Error collecting {name}: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # توابع جمع‌آوری (همانند قبل)
    # ============================================================
    
    def _collect_cpu(self) -> float:
        try:
            return psutil.cpu_percent(interval=0.2)
        except:
            return 0.0
    
    def _collect_ram(self) -> float:
        try:
            return psutil.virtual_memory().percent
        except:
            return 0.0
    
    def _collect_uptime(self) -> str:
        elapsed = int(time.time() - self.start_time)
        if elapsed < 60:
            return f"{elapsed}s"
        elif elapsed < 3600:
            return f"{elapsed // 60}m {elapsed % 60}s"
        else:
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def _collect_process_count(self) -> int:
        try:
            return len(psutil.pids())
        except:
            return 0
    
    def _collect_api_status(self) -> str:
        try:
            from app import system
            status = system.api.get_status()
            return status.get("status", "unknown") if status else "unknown"
        except:
            return "error"
    
    def _collect_api_credits(self) -> int:
        try:
            from app import system
            credits = system.api.get_credits()
            return credits.get("remainingCredits", 0) if credits else 0
        except:
            return 0
    
    def _collect_model_status(self) -> Dict:
        try:
            from app import system
            if system.model_manager:
                return {
                    "loaded": system.model_manager.current_model is not None,
                    "version": system.model_manager.current_version or "N/A"
                }
        except:
            pass
        return {"loaded": False, "version": "N/A"}
    
    def _collect_active_users(self) -> int:
        try:
            from auth_manager import get_auth
            auth = get_auth()
            return len(auth._sessions) if hasattr(auth, '_sessions') else 0
        except:
            return 0
    
    def _collect_database_size(self) -> float:
        try:
            from database import get_primary
            db = get_primary()
            if db and db.is_connected():
                result = db.execute("""
                    SELECT pg_database_size(current_database()) / 1024 / 1024 as size_mb
                """)
                if result:
                    return result[0].get('size_mb', 0)
        except:
            pass
        return 0
    
    def _collect_disk_space(self) -> Dict:
        try:
            usage = psutil.disk_usage('/')
            return {
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": usage.percent
            }
        except:
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "percent": 0}
    
    def _collect_error_logs(self) -> Dict:
        try:
            from logger_config import get_recent_logs
            logs = get_recent_logs("system", 100)
            errors = [l for l in logs if "ERROR" in l or "❌" in l]
            return {
                "total": len(errors),
                "recent": errors[-5:] if errors else []
            }
        except:
            return {"total": 0, "recent": []}
    
    def _collect_full_health(self) -> Dict:
        try:
            from app import system
            return system.health_check()
        except:
            return {"status": "error", "message": "Health check failed"}
    
    def _collect_model_accuracy(self) -> float:
        try:
            from app import system
            if hasattr(system, 'trainer'):
                stats = system.trainer.get_stats()
                return stats.get('stats', {}).get('last_score', 0)
        except:
            pass
        return 0
    
    def _add_to_history(self, name: str, value: Any):
        self.history.append({
            "name": name,
            "value": value,
            "timestamp": datetime.now().isoformat()
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    # ============================================================
    # API برای دسترسی به داده‌ها
    # ============================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics_cache,
            "stats": self.stats,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_history(self, name: Optional[str] = None, limit: int = 100) -> List:
        if name:
            return [h for h in self.history[-limit:] if h["name"] == name]
        return self.history[-limit:]
    
    def get_summary(self) -> Dict:
        return {
            "status": "running" if self._running else "stopped",
            "total_collections": self.stats["collections"],
            "errors": self.stats["errors"],
            "metrics_count": len(self.metrics_cache),
            "history_size": len(self.history),
            "collections_by_level": self.stats["collections_by_level"],
            "last_collection": self.stats["last_collection"]
        }
    
    def get_health(self) -> Dict:
        """بررسی سلامت کامل (جایگزین health_check قدیمی)"""
        metrics = self.metrics_cache
        
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {
                    "status": "healthy" if metrics.get("cpu", {}).get("value", 0) < 80 else "warning",
                    "value": metrics.get("cpu", {}).get("value", 0)
                },
                "ram": {
                    "status": "healthy" if metrics.get("ram", {}).get("value", 0) < 80 else "warning",
                    "value": metrics.get("ram", {}).get("value", 0)
                },
                "api": {
                    "status": "healthy" if metrics.get("api_status", {}).get("value") == "ok" else "degraded",
                    "status_text": metrics.get("api_status", {}).get("value", "unknown")
                },
                "model": {
                    "status": "healthy" if metrics.get("model_status", {}).get("value", {}).get("loaded") else "degraded",
                    "loaded": metrics.get("model_status", {}).get("value", {}).get("loaded", False),
                    "version": metrics.get("model_status", {}).get("value", {}).get("version", "N/A")
                },
                "database": {
                    "status": "healthy",
                    "size_mb": metrics.get("database_size", {}).get("value", 0)
                },
                "disk": {
                    "status": "healthy" if metrics.get("disk_space", {}).get("value", {}).get("percent", 0) < 85 else "warning",
                    "free_gb": metrics.get("disk_space", {}).get("value", {}).get("free_gb", 0)
                }
            }
        }


# ============================================================
# ایجاد نمونه Singleton
# ============================================================

metrics_scheduler = MetricsScheduler()
