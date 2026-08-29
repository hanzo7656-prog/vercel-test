# core/metrics.py
# ============================================================
# سیستم جمع‌آوری متریک - نسخه ۷.۰ (پایدار و دائمی)
# ============================================================

import time
import threading
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from config import get_scheduler_config

logger = logging.getLogger(__name__)


class MetricsScheduler:
    """
    سیستم جمع‌آوری متریک با threading پایدار
    - بدون `daemon=True` برای جلوگیری از مرگ ناگهانی
    - با `threading.Event()` برای کنترل دقیق
    - لاگ کامل برای عیب‌یابی
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
        self.metrics_cache: Dict[str, Any] = {}
        self.stats = {
            "collections": 0,
            "errors": 0,
            "last_collection": None,
            "loop_cycles": 0
        }
        self.start_time = time.time()
        
        # دریافت تنظیمات
        scheduler_config = get_scheduler_config()
        self.light_interval = scheduler_config.get("light_interval", 3)
        self.medium_interval = scheduler_config.get("medium_interval", 30)
        self.heavy_interval = scheduler_config.get("heavy_interval", 300)
        
        logger.info(f"✅ MetricsScheduler v7.0 initialized")
        logger.info(f"⏱️ Light={self.light_interval}s, Medium={self.medium_interval}s, Heavy={self.heavy_interval}s")
    
    # ============================================================
    # ✅ ۱. شروع و توقف (با لاگ کامل)
    # ============================================================
    
    def start(self):
        """شروع Scheduler با جمع‌آوری اولیه"""
        if self._running:
            logger.info("⏳ Scheduler already running")
            return
        
        logger.info("🔄 Starting Scheduler...")
        
        # ریست کردن stop_event
        self._stop_event.clear()
        
        # ایجاد و شروع ترد (بدون daemon)
        self._thread = threading.Thread(
            target=self._scheduler_loop, 
            daemon=False,  # ✅ تغییر: daemon=False
            name="MetricsScheduler"
        )
        self._thread.start()
        self._running = True
        
        logger.info(f"✅ Scheduler started (Thread: {self._thread.name}, Daemon: {self._thread.daemon})")
        
        # ✅ جمع‌آوری اولیه (برای پر کردن cache بلافاصله)
        logger.info("🔄 Collecting initial metrics...")
        try:
            self._collect_light_metrics()
            self._collect_medium_metrics()
            self._collect_heavy_metrics()
            logger.info("✅ Initial collection complete")
        except Exception as e:
            logger.error(f"❌ Initial collection error: {e}")
    
    def stop(self):
        """متوقف کردن Scheduler"""
        if not self._running:
            logger.info("⏳ Scheduler already stopped")
            return
        
        logger.info("🔄 Stopping Scheduler...")
        self._running = False
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            logger.info(f"✅ Thread joined (alive: {self._thread.is_alive()})")
        
        self._thread = None
        logger.info("⏹️ Scheduler stopped")
    
    # ============================================================
    # ✅ ۲. حلقه اصلی (با لاگ و Event)
    # ============================================================
    
    def _scheduler_loop(self):
        """حلقه اصلی - هر ۱ ثانیه چک می‌کند"""
        logger.info("🔄 Scheduler loop started")
        
        last_light = 0
        last_medium = 0
        last_heavy = 0
        cycle_count = 0
        
        # ✅ جمع‌آوری اولیه در حلقه (امنیت بیشتر)
        try:
            self._collect_light_metrics()
            self._collect_medium_metrics()
            self._collect_heavy_metrics()
            last_light = time.time()
            last_medium = time.time()
            last_heavy = time.time()
        except Exception as e:
            logger.error(f"❌ Initial collection in loop error: {e}")
        
        while not self._stop_event.is_set() and self._running:
            try:
                now = time.time()
                cycle_count += 1
                
                # هر ۱۰ سیکل یکبار لاگ
                if cycle_count % 10 == 0:
                    self.stats["loop_cycles"] = cycle_count
                    logger.debug(f"🏃 Loop alive (cycle {cycle_count})")
                
                # ===== Light: هر ۳ ثانیه =====
                if now - last_light >= self.light_interval:
                    self._collect_light_metrics()
                    last_light = now
                    logger.debug(f"📊 Light metrics collected (CPU: {self.metrics_cache.get('cpu', {}).get('value')}%)")
                
                # ===== Medium: هر ۳۰ ثانیه =====
                if now - last_medium >= self.medium_interval:
                    self._collect_medium_metrics()
                    last_medium = now
                    btc = self.metrics_cache.get('btc_price', {}).get('value', 0)
                    logger.info(f"📊 Medium metrics collected (BTC: ${btc:,.2f})")
                
                # ===== Heavy: هر ۵ دقیقه =====
                if now - last_heavy >= self.heavy_interval:
                    self._collect_heavy_metrics()
                    last_heavy = now
                    fear = self.metrics_cache.get('fear_greed', {}).get('value', 50)
                    logger.info(f"📊 Heavy metrics collected (Fear: {fear})")
                
                self.stats["last_collection"] = datetime.now().isoformat()
                
                # ✅ هر ۱ ثانیه چک کن (نه sleep طولانی)
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Scheduler loop error: {e}")
                self.stats["errors"] += 1
                time.sleep(1)
        
        logger.info(f"⏹️ Scheduler loop stopped (after {cycle_count} cycles)")
    
    # ============================================================
    # ✅ ۳. جمع‌آوری‌کننده‌ها (بدون تغییر)
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
            
            with self._lock:
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
                self.metrics_cache["uptime"] = {
                    "value": uptime,
                    "timestamp": datetime.now().isoformat(),
                    "level": "light"
                }
                self.stats["collections"] += 1
            
        except Exception as e:
            logger.error(f"❌ Light metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_medium_metrics(self):
        """قیمت‌ها, API, مدل"""
        try:
            # ===== ۱. قیمت‌ها =====
            try:
                import core.system
                system = core.system.system
                
                btc = system.api.get_coin("bitcoin")
                if btc and "error" not in btc:
                    with self._lock:
                        self.metrics_cache["btc_price"] = {
                            "value": btc.get("price", 0),
                            "change_24h": btc.get("priceChange1d", 0),
                            "timestamp": datetime.now().isoformat(),
                            "level": "medium"
                        }
                
                eth = system.api.get_coin("ethereum")
                if eth and "error" not in eth:
                    with self._lock:
                        self.metrics_cache["eth_price"] = {
                            "value": eth.get("price", 0),
                            "change_24h": eth.get("priceChange1d", 0),
                            "timestamp": datetime.now().isoformat(),
                            "level": "medium"
                        }
            except Exception as e:
                logger.debug(f"Price collection error: {e}")
            
            # ===== ۲. API Status =====
            try:
                import core.system
                system = core.system.system
                status = system.api.get_status()
                api_status = status.get("status", "unknown") if status else "unknown"
                
                with self._lock:
                    self.metrics_cache["api_status"] = {
                        "value": api_status,
                        "timestamp": datetime.now().isoformat(),
                        "level": "medium"
                    }
            except Exception as e:
                logger.debug(f"API status error: {e}")
            
            # ===== ۳. API Credits =====
            try:
                import core.system
                system = core.system.system
                credits = system.api.get_credits()
                api_credits = credits.get("remainingCredits", 0) if credits else 0
                
                with self._lock:
                    self.metrics_cache["api_credits"] = {
                        "value": api_credits,
                        "timestamp": datetime.now().isoformat(),
                        "level": "medium"
                    }
            except Exception as e:
                logger.debug(f"Credits error: {e}")
            
            # ===== ۴. Model Status =====
            try:
                import core.system
                system = core.system.system
                if system.model_manager:
                    loaded = system.model_manager.current_model is not None
                    version = system.model_manager.current_version or "N/A"
                else:
                    loaded = False
                    version = "N/A"
                
                with self._lock:
                    self.metrics_cache["model_status"] = {
                        "value": {"loaded": loaded, "version": version},
                        "timestamp": datetime.now().isoformat(),
                        "level": "medium"
                    }
            except Exception as e:
                logger.debug(f"Model status error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Medium metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_heavy_metrics(self):
        """ترس و طمع, سلطه, اخبار, دیتابیس, دیسک"""
        try:
            # ===== ۱. Fear & Greed =====
            try:
                import core.system
                system = core.system.system
                fg = system.api.get_fear_greed(use_cache=True)
                if fg and "now" in fg:
                    with self._lock:
                        self.metrics_cache["fear_greed"] = {
                            "value": fg["now"].get("value", 50),
                            "classification": fg["now"].get("value_classification", "Neutral"),
                            "timestamp": datetime.now().isoformat(),
                            "level": "heavy"
                        }
            except Exception as e:
                logger.debug(f"Fear & Greed error: {e}")
            
            # ===== ۲. BTC Dominance =====
            try:
                import core.system
                system = core.system.system
                dominance = system.api.get_btc_dominance(use_cache=True)
                if dominance:
                    with self._lock:
                        self.metrics_cache["btc_dominance"] = {
                            "value": dominance.get("dominance", 50),
                            "timestamp": datetime.now().isoformat(),
                            "level": "heavy"
                        }
            except Exception as e:
                logger.debug(f"BTC Dominance error: {e}")
            
            # ===== ۳. News =====
            try:
                import core.system
                system = core.system.system
                news = system.api.get_news(limit=5)
                if news and "error" not in news:
                    with self._lock:
                        self.metrics_cache["news"] = {
                            "value": news,
                            "timestamp": datetime.now().isoformat(),
                            "level": "heavy"
                        }
            except Exception as e:
                logger.debug(f"News error: {e}")
            
            # ===== ۴. Database Size =====
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
                
                with self._lock:
                    self.metrics_cache["database_size"] = {
                        "value": db_size,
                        "timestamp": datetime.now().isoformat(),
                        "level": "heavy"
                    }
            except Exception as e:
                logger.debug(f"Database size error: {e}")
            
            # ===== ۵. Disk Space =====
            try:
                usage = psutil.disk_usage('/')
                disk = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                }
                with self._lock:
                    self.metrics_cache["disk_space"] = {
                        "value": disk,
                        "timestamp": datetime.now().isoformat(),
                        "level": "heavy"
                    }
            except Exception as e:
                logger.debug(f"Disk space error: {e}")
            
            # ===== ۶. Databases Status =====
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
                
                with self._lock:
                    self.metrics_cache["databases"] = {
                        "value": dbs,
                        "timestamp": datetime.now().isoformat(),
                        "level": "heavy"
                    }
            except Exception as e:
                logger.debug(f"Databases status error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Heavy metrics error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # ✅ ۴. API
    # ============================================================
    
    def get_metrics(self) -> Dict:
        with self._lock:
            return {
                "metrics": self.metrics_cache.copy(),
                "stats": self.stats.copy(),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_summary(self) -> Dict:
        with self._lock:
            return {
                "status": "running" if self._running else "stopped",
                "total_collections": self.stats["collections"],
                "errors": self.stats["errors"],
                "metrics_count": len(self.metrics_cache),
                "last_collection": self.stats["last_collection"],
                "loop_cycles": self.stats.get("loop_cycles", 0)
            }
    
    def get_alert_metrics(self) -> Dict:
        with self._lock:
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
        with self._lock:
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
                "database": {
                    "size_mb": cache.get("database_size", {}).get("value", 0),
                    "status": cache.get("databases", {}).get("value", {})
                },
                "disk": cache.get("disk_space", {}).get("value", {}),
                "news": cache.get("news", {}).get("value", []),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_health(self) -> Dict:
        with self._lock:
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
