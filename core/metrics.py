# core/metrics.py
# ============================================================
# سیستم جمع‌آوری متریک - نسخه ۱۲.۱
# Gemini-aware + Self-Healing
# ============================================================
# 
# تغییرات نسخه ۱۲.۱:
#   - _get_healer اضافه شد (Lazy)
#   - _run_self_healing اضافه شد
#   - healing_interval اضافه شد
#   - stats.healing_actions, last_healing اضافه شد
# ============================================================

import time
import psutil
import logging
import threading
import random
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ============================================================
# MetricsScheduler
# ============================================================

class MetricsScheduler:
    """
    سیستم جمع‌آوری متریک - Gemini-aware + Self-Healing
    """
    
    _instance: Optional['MetricsScheduler'] = None
    _instance_lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'MetricsScheduler':
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # State
        self._running = False
        self._stop_event: Optional[threading.Event] = None
        self.metrics_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        
        # آمار
        self.stats: Dict[str, Any] = {
            "collections": 0,
            "errors": 0,
            "last_collection": None,
            "healing_actions": 0,      # 🆕
            "last_healing": None,       # 🆕
        }
        
        self.start_time = time.time()
        
        # Intervals
        self.light_interval = 3
        self.medium_interval = 60
        self.heavy_interval = 300
        self.healing_interval = 30      # 🆕
        
        # Jitter range
        self.jitter_range = 2
        
        # Healer (Lazy) 🆕
        self.healer = None
        
        logger.info("✅ MetricsScheduler v12.1 initialized (Gemini + Self-Healing)")
    
    # ============================================================
    # Self-Healing 🆕
    # ============================================================
    
    def _get_healer(self):
        """دریافت healer (Lazy)"""
        if self.healer is not None:
            return self.healer
        
        try:
            from container import container
            self.healer = container.get('self_healer')
            logger.info("✅ SelfHealer initialized (lazy)")
            return self.healer
        except Exception as e:
            logger.debug(f"⚠️ SelfHealer not available: {e}")
            return None
    
    def _run_self_healing(self) -> None:
        """اجرای self-healing"""
        healer = self._get_healer()
        
        if healer is None:
            return
        
        try:
            metrics = self.get_alert_metrics()
            actions = healer.check_and_heal(metrics)
            
            if any(actions.values()):
                self.stats["healing_actions"] += 1
                self.stats["last_healing"] = datetime.now().isoformat()
                logger.info(f"🔄 Self-healing actions: {actions}")
                
        except Exception as e:
            logger.error(f"❌ Self-healing error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # Light Metrics (۳ ثانیه)
    # ============================================================
    
    def _collect_light_metrics(self) -> None:
        """متریک‌های سبک: CPU، RAM، Uptime"""
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
            
            with self._cache_lock:
                now = datetime.now().isoformat()
                self.metrics_cache["cpu"] = {"value": cpu, "timestamp": now}
                self.metrics_cache["ram"] = {"value": ram, "timestamp": now}
                self.metrics_cache["uptime"] = {"value": uptime, "timestamp": now}
            
            self.stats["collections"] += 1
            
        except Exception as e:
            logger.error(f"❌ Light metrics error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # Medium Metrics (۶۰ ثانیه)
    # ============================================================
    
    def _collect_medium_metrics(self) -> None:
        """متریک‌های متوسط: قیمت‌ها، API، AI، دیتابیس"""
        try:
            from infrastructure.api.coinstats_client import coinstats_client
            from infrastructure.database import health_check as db_health
            
            self._collect_prices(coinstats_client)
            self._collect_api_status(coinstats_client)
            self._collect_ai_status()
            self._collect_db_status(db_health)
            
        except Exception as e:
            logger.error(f"❌ Medium metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_prices(self, coinstats_client) -> None:
        """دریافت قیمت BTC/ETH"""
        try:
            btc = coinstats_client.get_coin("bitcoin")
            if btc and "error" not in btc:
                with self._cache_lock:
                    self.metrics_cache["btc_price"] = {
                        "value": btc.get("price", 0),
                        "change_24h": btc.get("priceChange1d", 0),
                        "timestamp": datetime.now().isoformat(),
                    }
        except Exception as e:
            logger.debug(f"⚠️ BTC price error: {e}")
        
        try:
            eth = coinstats_client.get_coin("ethereum")
            if eth and "error" not in eth:
                with self._cache_lock:
                    self.metrics_cache["eth_price"] = {
                        "value": eth.get("price", 0),
                        "change_24h": eth.get("priceChange1d", 0),
                        "timestamp": datetime.now().isoformat(),
                    }
        except Exception as e:
            logger.debug(f"⚠️ ETH price error: {e}")
    
    def _collect_api_status(self, coinstats_client) -> None:
        """وضعیت API و Credits"""
        try:
            status = coinstats_client.get_status()
            api_status = status.get("status", "unknown") if status else "unknown"
            
            with self._cache_lock:
                self.metrics_cache["api_status"] = {
                    "value": api_status,
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.debug(f"⚠️ API status error: {e}")
        
        try:
            credits = coinstats_client.get_credits()
            api_credits = credits.get("remainingCredits", 0) if credits else 0
            
            with self._cache_lock:
                self.metrics_cache["api_credits"] = {
                    "value": api_credits,
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.debug(f"⚠️ Credits error: {e}")
    
    def _collect_ai_status(self) -> None:
        """وضعیت Gemini"""
        try:
            from container import container
            gemini = container.get('gemini_client')
            if gemini is None:
                return
            
            stats = gemini.get_stats()
            
            with self._cache_lock:
                self.metrics_cache["ai_status"] = {
                    "value": {
                        "available": gemini.is_available,
                        "total_requests": stats.get("total_requests", 0),
                        "success_rate": stats.get("success_rate", 0),
                        "last_error": stats.get("last_error"),
                    },
                    "timestamp": datetime.now().isoformat(),
                }
        except Exception as e:
            logger.debug(f"⚠️ AI status error: {e}")
    
    def _collect_db_status(self, db_health) -> None:
        """وضعیت دیتابیس‌ها"""
        try:
            health = db_health()
            dbs = {}
            
            for name, info in health.items():
                dbs[name] = info.get("connected", False)
            
            with self._cache_lock:
                self.metrics_cache["databases"] = {
                    "value": dbs,
                    "timestamp": datetime.now().isoformat(),
                }
            
            logger.debug(f"✅ Databases: {dbs}")
            
        except Exception as e:
            logger.debug(f"⚠️ Databases error: {e}")
    
    # ============================================================
    # Heavy Metrics (۳۰۰ ثانیه)
    # ============================================================
    
    def _collect_heavy_metrics(self) -> None:
        """متریک‌های سنگین: ترس و طمع، سلطه، اخبار، دیسک"""
        try:
            from infrastructure.api.coinstats_client import coinstats_client
            
            # ترس و طمع
            try:
                fg = coinstats_client.get_fear_greed(use_cache=True)
                if fg and "now" in fg:
                    with self._cache_lock:
                        self.metrics_cache["fear_greed"] = {
                            "value": fg["now"].get("value", 50),
                            "classification": fg["now"].get("value_classification", "Neutral"),
                            "timestamp": datetime.now().isoformat(),
                        }
            except Exception as e:
                logger.debug(f"⚠️ Fear & Greed error: {e}")
            
            # سلطه BTC
            try:
                dominance = coinstats_client.get_btc_dominance(use_cache=True)
                if dominance:
                    with self._cache_lock:
                        self.metrics_cache["btc_dominance"] = {
                            "value": dominance.get("dominance", 50),
                            "timestamp": datetime.now().isoformat(),
                        }
            except Exception as e:
                logger.debug(f"⚠️ BTC Dominance error: {e}")
            
            # اخبار
            try:
                news = coinstats_client.get_news(limit=5)
                if news and "error" not in news:
                    with self._cache_lock:
                        self.metrics_cache["news"] = {
                            "value": news,
                            "timestamp": datetime.now().isoformat(),
                        }
            except Exception as e:
                logger.debug(f"⚠️ News error: {e}")
            
            # دیسک
            try:
                usage = psutil.disk_usage("/")
                disk = {
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                }
                with self._cache_lock:
                    self.metrics_cache["disk_space"] = {
                        "value": disk,
                        "timestamp": datetime.now().isoformat(),
                    }
            except Exception as e:
                logger.debug(f"⚠️ Disk space error: {e}")
                
        except Exception as e:
            logger.error(f"❌ Heavy metrics error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # Public API
    # ============================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """دریافت همه متریک‌ها"""
        with self._cache_lock:
            cache_copy = dict(self.metrics_cache)
        
        return {
            "metrics": cache_copy,
            "stats": dict(self.stats),
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """خلاصه وضعیت"""
        with self._cache_lock:
            cache_len = len(self.metrics_cache)
        
        return {
            "status": "running" if self._running else "stopped",
            "total_collections": self.stats["collections"],
            "errors": self.stats["errors"],
            "healing_actions": self.stats.get("healing_actions", 0),   # 🆕
            "last_healing": self.stats.get("last_healing"),             # 🆕
            "metrics_count": cache_len,
            "last_collection": self.stats["last_collection"],
        }
    
    def get_alert_metrics(self) -> Dict[str, Any]:
        """متریک‌های لازم برای alerts"""
        with self._cache_lock:
            cache = dict(self.metrics_cache)
        
        return {
            "cpu": cache.get("cpu", {}).get("value", 0),
            "ram": cache.get("ram", {}).get("value", 0),
            "api_status": cache.get("api_status", {}).get("value", "unknown"),
            "api_credits": cache.get("api_credits", {}).get("value", 0),
            "ai_status": cache.get("ai_status", {}).get("value", {}),
            "databases": cache.get("databases", {}).get("value", {}),
            "uptime": cache.get("uptime", {}).get("value", "0s"),
        }
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """متریک‌های داشبورد (همه در یک جا)"""
        with self._cache_lock:
            cache = dict(self.metrics_cache)
        
        return {
            "system": {
                "cpu": cache.get("cpu", {}).get("value", 0),
                "ram": cache.get("ram", {}).get("value", 0),
                "uptime": cache.get("uptime", {}).get("value", "0s"),
            },
            "prices": {
                "btc": cache.get("btc_price", {}).get("value", 0),
                "btc_change": cache.get("btc_price", {}).get("change_24h", 0),
                "eth": cache.get("eth_price", {}).get("value", 0),
                "eth_change": cache.get("eth_price", {}).get("change_24h", 0),
            },
            "api": {
                "status": cache.get("api_status", {}).get("value", "unknown"),
                "credits": cache.get("api_credits", {}).get("value", 0),
            },
            "ai": cache.get("ai_status", {}).get("value", {}),
            "market": {
                "fear_greed": cache.get("fear_greed", {}).get("value", 50),
                "fear_greed_label": cache.get("fear_greed", {}).get("classification", "Neutral"),
                "btc_dominance": cache.get("btc_dominance", {}).get("value", 50),
            },
            "databases": cache.get("databases", {}).get("value", {}),
            "disk": cache.get("disk_space", {}).get("value", {}),
            "healing": {
                "actions": self.stats.get("healing_actions", 0),
                "last": self.stats.get("last_healing"),
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_health(self) -> Dict[str, Any]:
        """بررسی سلامت سیستم"""
        with self._cache_lock:
            cache = dict(self.metrics_cache)
        
        cpu = cache.get("cpu", {}).get("value", 0)
        ram = cache.get("ram", {}).get("value", 0)
        databases = cache.get("databases", {}).get("value", {})
        ai_status = cache.get("ai_status", {}).get("value", {})
        
        cpu_status = "healthy" if cpu < 70 else "warning" if cpu < 90 else "critical"
        ram_status = "healthy" if ram < 70 else "warning" if ram < 90 else "critical"
        
        db_status = {}
        all_connected = True
        for name, connected in databases.items():
            db_status[name] = {
                "connected": connected,
                "status": "online" if connected else "offline",
            }
            if not connected:
                all_connected = False
        
        overall = "ok"
        if cpu_status != "healthy" or ram_status != "healthy" or not all_connected:
            overall = "degraded"
        if ai_status and not ai_status.get("available", True):
            overall = "degraded"
        
        return {
            "status": overall,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {"status": cpu_status, "value": round(cpu, 1)},
                "ram": {"status": ram_status, "value": round(ram, 1)},
                "databases": db_status,
                "ai": {
                    "available": ai_status.get("available", False),
                    "success_rate": ai_status.get("success_rate", 0),
                },
            },
        }
    
    # ============================================================
    # Start / Stop
    # ============================================================
    
    def set_stop_event(self, event: threading.Event) -> None:
        """تنظیم stop event"""
        self._stop_event = event
    
    def start(self) -> None:
        """شروع Scheduler"""
        if self._running:
            return
        
        self._running = True
        logger.info("🔄 Metrics Scheduler v12.1 started (Gemini + Self-Healing)")
        
        # Collection اولیه
        try:
            self._collect_light_metrics()
            self._collect_medium_metrics()
            self._collect_heavy_metrics()
            self._run_self_healing()
            logger.info("✅ Initial collection complete")
        except Exception as e:
            logger.error(f"❌ Initial collection error: {e}")
        
        last_light = time.time()
        last_medium = time.time()
        last_heavy = time.time()
        last_healing = time.time()      # 🆕
        cycle_count = 0
        
        while self._running and not (
            self._stop_event and self._stop_event.is_set()
        ):
            try:
                now = time.time()
                cycle_count += 1
                
                jitter = random.uniform(-self.jitter_range, self.jitter_range)
                
                # Light
                if now - last_light >= self.light_interval + jitter:
                    self._collect_light_metrics()
                    last_light = now
                
                # Medium
                if now - last_medium >= self.medium_interval + jitter:
                    self._collect_medium_metrics()
                    last_medium = now
                    logger.debug(f"📊 Medium collected (cycle {cycle_count})")
                
                # Heavy
                if now - last_heavy >= self.heavy_interval + jitter:
                    self._collect_heavy_metrics()
                    last_heavy = now
                    logger.debug(f"📊 Heavy collected (cycle {cycle_count})")
                
                # Self-Healing 🆕
                if now - last_healing >= self.healing_interval + jitter:
                    self._run_self_healing()
                    last_healing = now
                
                self.stats["last_collection"] = datetime.now().isoformat()
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                self.stats["errors"] += 1
                time.sleep(5)
        
        logger.info("⏹️ Metrics Scheduler stopped")
    
    def stop(self) -> None:
        """توقف Scheduler"""
        self._running = False
        logger.info("⏹️ Metrics Scheduler stopping")


# ============================================================
# Singleton
# ============================================================

metrics_scheduler: MetricsScheduler = MetricsScheduler()
