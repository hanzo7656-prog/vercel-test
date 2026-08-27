# core/metrics.py
# ============================================================
# سیستم زمان‌بندی هوشمند برای جمع‌آوری متریک
# نسخه ۲.۴ - با واتچ‌داگ داخلی و ری‌استارت خودکار
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
    """سطح اهمیت متریک"""
    LIGHT = "light"      # هر ۳ ثانیه
    MEDIUM = "medium"    # هر ۳۰ ثانیه
    HEAVY = "heavy"      # هر ۵ دقیقه


@dataclass
class MetricConfig:
    """تنظیمات هر متریک"""
    name: str
    level: MetricLevel
    interval: int
    enabled: bool = True
    last_collected: Optional[float] = None
    last_value: Any = None


class MetricsScheduler:
    """
    سیستم جامع جمع‌آوری متریک با زمان‌بندی هوشمند
    نسخه ۲.۴ - با واتچ‌داگ داخلی
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._restart_count = 0
        self._last_heartbeat = time.time()
        self._heartbeat_timeout = 30  # ۳۰ ثانیه بدون ضربان = مرده
        self._stop_watchdog = False
        
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
            "restarts": 0,
            "watchdog_restarts": 0,
            "last_collection": None,
            "collections_by_level": {
                "light": 0,
                "medium": 0,
                "heavy": 0
            }
        }
        
        # مقدار شروع برای uptime
        self.start_time = time.time()
        
        # زمان آخرین گزارش دوره‌ای
        self._last_report_time = 0
        self._report_interval = 21600  # ۶ ساعت
        
        logger.info("✅ MetricsScheduler v2.4 initialized")
        
        # ✅ شروع خودکار واتچ‌داگ
        self._start_watchdog()
    
    # ============================================================
    # واتچ‌داگ داخلی (قوی و مستقل)
    # ============================================================
    
    def _start_watchdog(self):
        """شروع واتچ‌داگ داخلی برای نظارت بر سلامت ترد"""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        
        self._stop_watchdog = False
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
        logger.info("✅ Internal Watchdog started")
    
    def _watchdog_loop(self):
        """حلقه واتچ‌داگ - هر ۵ ثانیه چک می‌کند"""
        logger.info("🔄 Watchdog loop started")
        
        while not self._stop_watchdog:
            try:
                time.sleep(5)  # هر ۵ ثانیه چک کن
                
                # اگر Scheduler متوقف شده بود، کاری نکن
                if not self._running:
                    continue
                
                # ۱. بررسی اینکه ترد اصلی زنده است؟
                thread_is_dead = not self._is_thread_alive()
                
                # ۲. بررسی ضربان قلب
                heartbeat_timeout = (time.time() - self._last_heartbeat) > self._heartbeat_timeout
                
                if thread_is_dead or heartbeat_timeout:
                    reason = "thread dead" if thread_is_dead else "heartbeat timeout"
                    logger.warning(f"⚠️ Watchdog detected: {reason}. Restarting...")
                    self._restart_scheduler()
                    
            except Exception as e:
                logger.error(f"❌ Watchdog error: {e}")
                time.sleep(1)
        
        logger.info("⏹️ Watchdog loop stopped")
    
    def _is_thread_alive(self) -> bool:
        """بررسی زنده بودن ترد اصلی"""
        return self._thread is not None and self._thread.is_alive()
    
    def _restart_scheduler(self):
        """ری‌استارت خودکار Scheduler"""
        with self._lock:
            self._restart_count += 1
            self.stats["restarts"] = self._restart_count
            self.stats["watchdog_restarts"] = self.stats.get("watchdog_restarts", 0) + 1
            logger.info(f"🔄 Restarting scheduler (attempt #{self._restart_count})")
            
            # توقف کامل
            old_running = self._running
            self._running = False
            
            if self._thread:
                self._thread.join(timeout=2)
                self._thread = None
            
            # استارت مجدد
            self._running = True
            self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._thread.start()
            self._last_heartbeat = time.time()
            
            logger.info(f"✅ Scheduler restarted successfully (restart #{self._restart_count})")
    
    # ============================================================
    # کنترل Start/Stop
    # ============================================================
    
    def start(self):
        """شروع زمان‌بند"""
        if self._running and self._is_thread_alive():
            logger.info("⏳ Scheduler already running")
            return
        
        with self._lock:
            if self._running and not self._is_thread_alive():
                logger.warning("⚠️ Thread is dead but _running is True. Resetting...")
                self._running = False
                if self._thread:
                    self._thread.join(timeout=1)
                    self._thread = None
            
            self._running = True
            self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._thread.start()
            self._last_heartbeat = time.time()
            logger.info("✅ Metrics Scheduler started")
            
            # جمع‌آوری اولیه
            self._collect_initial_metrics()
    
    def stop(self):
        """متوقف کردن زمان‌بند"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        logger.info("⏹️ Metrics Scheduler stopped")
    
    def shutdown(self):
        """توقف کامل (شامل واتچ‌داگ)"""
        self._stop_watchdog = True
        self.stop()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2)
            self._watchdog_thread = None
        logger.info("⏹️ Metrics Scheduler fully shutdown")
    
    def _collect_initial_metrics(self):
        """جمع‌آوری اولیه متریک‌ها"""
        logger.info("🔄 Collecting initial metrics...")
        for name, config in self.configs.items():
            if config.enabled:
                try:
                    self._collect_metric(name, config)
                    config.last_collected = time.time()
                    self.stats["collections"] += 1
                    self.stats["collections_by_level"][config.level.value] += 1
                except Exception as e:
                    logger.error(f"❌ Initial collection error for {name}: {e}")
        self.stats["last_collection"] = datetime.now().isoformat()
        logger.info(f"✅ Initial collection done. Metrics: {list(self.metrics_cache.keys())}")
    
    # ============================================================
    # حلقه اصلی زمان‌بندی
    # ============================================================
    
    def _scheduler_loop(self):
        """حلقه اصلی - هر ۱ ثانیه چک می‌کند"""
        logger.info("🔄 Scheduler loop started")
        loop_count = 0
        
        while self._running:
            try:
                now = time.time()
                loop_count += 1
                
                # به‌روزرسانی ضربان قلب (هر ۲ سیکل)
                if loop_count % 2 == 0:
                    self._last_heartbeat = now
                
                # جمع‌آوری متریک‌ها
                for name, config in self.configs.items():
                    if not config.enabled:
                        continue
                    
                    if (config.last_collected is None or 
                        now - config.last_collected >= config.interval):
                        
                        self._collect_metric(name, config)
                        config.last_collected = now
                        self.stats["collections"] += 1
                        self.stats["collections_by_level"][config.level.value] += 1
                        
                        # لاگ برای متریک‌های مهم
                        if name in ["cpu", "ram"]:
                            logger.info(f"📊 {name}: {config.last_value}%")
                        elif name == "api_status":
                            logger.info(f"📊 {name}: {config.last_value}")
                
                self.stats["last_collection"] = datetime.now().isoformat()
                
                # گزارش دوره‌ای
                if now - self._last_report_time >= self._report_interval:
                    self._send_periodic_report()
                    self._last_report_time = now
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                self.stats["errors"] += 1
                time.sleep(1)
        
        logger.info("⏹️ Scheduler loop stopped")
    
    # ============================================================
    # جمع‌آوری متریک‌ها
    # ============================================================
    
    def _collect_metric(self, name: str, config: MetricConfig):
        """جمع‌آوری یک متریک خاص"""
        try:
            value = None
            
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
                "databases": self._collect_databases,
            }
            
            if name in collectors:
                value = collectors[name]()
            
            if value is not None:
                self.metrics_cache[name] = {
                    "value": value,
                    "timestamp": datetime.now().isoformat(),
                    "level": config.level.value
                }
                config.last_value = value
                self._add_to_history(name, value)
                
        except Exception as e:
            logger.error(f"❌ Error collecting {name}: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # توابع جمع‌آوری اختصاصی
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
            from core.system import system
            status = system.api.get_status()
            return status.get("status", "unknown") if status else "unknown"
        except:
            return "error"
    
    def _collect_api_credits(self) -> int:
        try:
            from core.system import system
            credits = system.api.get_credits()
            return credits.get("remainingCredits", 0) if credits else 0
        except:
            return 0
    
    def _collect_model_status(self) -> Dict:
        try:
            from core.system import system
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
            from core.system import system
            return system.health_check()
        except:
            return {"status": "error", "message": "Health check failed"}
    
    def _collect_model_accuracy(self) -> float:
        try:
            from core.system import system
            if hasattr(system, 'trainer'):
                stats = system.trainer.get_stats()
                return stats.get('stats', {}).get('last_score', 0)
        except:
            pass
        return 0
    
    def _collect_databases(self) -> Dict:
        try:
            from database import health_check
            health = health_check()
            result = {}
            for name, info in health.items():
                if name == "postgresql":
                    result["postgresql"] = info.get("connected", False)
                elif name == "redis":
                    result["redis"] = info.get("connected", False)
                elif name == "sqlite":
                    result["sqlite"] = info.get("connected", False)
            return result
        except:
            return {"postgresql": False, "redis": False, "sqlite": False}
    
    # ============================================================
    # گزارش دوره‌ای
    # ============================================================
    
    def _send_periodic_report(self):
        """ارسال گزارش دوره‌ای"""
        try:
            cache = self.metrics_cache
            
            report = f"""
📊 *گزارش دوره‌ای سیستم*
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚙️ *مصرف منابع*
- CPU: {cache.get('cpu', {}).get('value', 0)}%
- RAM: {cache.get('ram', {}).get('value', 0)}%

🔌 *وضعیت سرویس‌ها*
- API: {cache.get('api_status', {}).get('value', 'unknown')}
- مدل: {'فعال' if cache.get('model_status', {}).get('value', {}).get('loaded') else 'غیرفعال'}

📊 *آمار جمع‌آوری*
- کل جمع‌آوری‌ها: {self.stats['collections']}
- خطاها: {self.stats['errors']}
- ری‌استارت‌ها: {self.stats['restarts']}
- ری‌استارت توسط واتچ‌داگ: {self.stats.get('watchdog_restarts', 0)}
"""
            
            try:
                from alerter import alerter
                if alerter.telegram_enabled:
                    alerter._send_telegram({
                        "level": "INFO",
                        "source": "system",
                        "message": report,
                        "timestamp": datetime.now().isoformat()
                    })
            except:
                pass
            
            logger.info("📊 Periodic report sent")
            
        except Exception as e:
            logger.error(f"❌ Error sending report: {e}")
    
    # ============================================================
    # ذخیره‌سازی تاریخچه
    # ============================================================
    
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
            "restarts": self.stats["restarts"],
            "watchdog_restarts": self.stats.get("watchdog_restarts", 0),
            "metrics_count": len(self.metrics_cache),
            "history_size": len(self.history),
            "collections_by_level": self.stats["collections_by_level"],
            "last_collection": self.stats["last_collection"],
            "uptime": self._collect_uptime()
        }
    
    def get_alert_metrics(self) -> Dict:
        cache = self.metrics_cache
        return {
            "cpu": cache.get("cpu", {}).get("value", 0),
            "ram": cache.get("ram", {}).get("value", 0),
            "api_status": cache.get("api_status", {}).get("value", "unknown"),
            "api_credits": cache.get("api_credits", {}).get("value", 0),
            "model_loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
            "model_accuracy": cache.get("model_accuracy", {}).get("value", None),
            "databases": cache.get("databases", {}).get("value", {}),
            "uptime": cache.get("uptime", {}).get("value", "0s"),
            "last_update": datetime.now().isoformat()
        }
    
    def get_dashboard_metrics(self) -> Dict:
        cache = self.metrics_cache
        model_status = cache.get("model_status", {}).get("value", {})
        model_accuracy = cache.get("model_accuracy", {}).get("value", 0)
        
        return {
            "system": {
                "cpu": cache.get("cpu", {}).get("value", 0),
                "ram": cache.get("ram", {}).get("value", 0),
                "uptime": cache.get("uptime", {}).get("value", "0s"),
                "processes": cache.get("process_count", {}).get("value", 0)
            },
            "api": {
                "status": cache.get("api_status", {}).get("value", "unknown"),
                "credits": cache.get("api_credits", {}).get("value", 0)
            },
            "model": {
                "loaded": model_status.get("loaded", False),
                "version": model_status.get("version", "N/A"),
                "accuracy": model_accuracy
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
        cpu_status = "healthy" if cpu < 70 else "warning" if cpu < 90 else "critical"
        
        ram = cache.get("ram", {}).get("value", 0)
        ram_status = "healthy" if ram < 70 else "warning" if ram < 90 else "critical"
        
        api = cache.get("api_status", {}).get("value", "unknown")
        api_status = "healthy" if api == "ok" else "degraded" if api == "degraded" else "unhealthy"
        
        model_loaded = cache.get("model_status", {}).get("value", {}).get("loaded", False)
        model_status = "healthy" if model_loaded else "degraded"
        
        db_status = cache.get("databases", {}).get("value", {})
        all_connected = all(db_status.values())
        db_health = "healthy" if all_connected else "degraded"
        
        overall = "ok"
        if cpu_status == "critical" or ram_status == "critical":
            overall = "critical"
        elif any(s in ["degraded", "warning", "unhealthy"] for s in [cpu_status, ram_status, api_status, model_status, db_health]):
            overall = "degraded"
        
        return {
            "status": overall,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {"status": cpu_status, "value": round(cpu, 1)},
                "ram": {"status": ram_status, "value": round(ram, 1)},
                "api": {"status": api_status},
                "model": {"status": model_status, "loaded": model_loaded},
                "database": {"status": db_health, "databases": db_status},
            }
        }
    
    def update_interval(self, metric_name: str, interval: int):
        if metric_name in self.configs:
            self.configs[metric_name].interval = interval
            logger.info(f"✅ {metric_name} interval updated to {interval}s")
    
    def enable_metric(self, metric_name: str, enabled: bool):
        if metric_name in self.configs:
            self.configs[metric_name].enabled = enabled
            logger.info(f"✅ {metric_name} {'enabled' if enabled else 'disabled'}")


# ============================================================
# ایجاد نمونه Singleton
# ============================================================

metrics_scheduler = MetricsScheduler()
