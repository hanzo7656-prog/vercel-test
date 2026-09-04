# core/metrics.py
# ============================================================
# سیستم جمع‌آوری متریک - نسخه نهایی با Self-Healer مقاوم
# ============================================================

import time
import psutil
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MetricsScheduler:
    """
    سیستم جمع‌آوری متریک با Self-Healer یکپارچه
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._running = False
        self._stop_event = None
        
        self.metrics_cache: Dict[str, Any] = {}
        self.stats = {
            "collections": 0,
            "errors": 0,
            "last_collection": None,
            "healing_actions": 0,
            "last_healing": None
        }
        self.start_time = time.time()
        
        # فواصل
        self.light_interval = 3
        self.medium_interval = 60
        self.heavy_interval = 300
        self.healing_interval = 30
        
        # ===== Self-Healer =====
        self.healer = None
        self._init_self_healer()
        
        # ===== بررسی نهایی =====
        if self.healer is not None:
            logger.info("✅ SelfHealer initialized successfully")
        else:
            logger.warning("⚠️ SelfHealer could not be initialized")
        
        logger.info("✅ MetricsScheduler v10.0 initialized")
    
    def _init_self_healer(self):
        """راه‌اندازی Self-Healer با مدیریت کامل خطاها"""
        try:
            from models.manager.model_manager import ModelManager
            from models.trainer.auto_trainer import AutoTrainer
            from infrastructure.api.coinstats_client import coinstats_client
            from application.services.self_healer import SelfHealer
            
            logger.info("✅ All SelfHealer imports successful")
            
            # ===== ایجاد ModelManager =====
            model_manager = ModelManager(api=coinstats_client)
            logger.info("✅ ModelManager created")
            
            # ===== ایجاد AutoTrainer =====
            trainer = AutoTrainer(
                api=coinstats_client,
                model_manager=model_manager
            )
            logger.info("✅ AutoTrainer created")
            
            # ===== ایجاد SelfHealer =====
            self.healer = SelfHealer(
                model_manager=model_manager,
                trainer=trainer,
                api_client=coinstats_client
            )
            logger.info("✅ SelfHealer created")
            
            # ===== تست =====
            if self.healer:
                status = self.healer.get_healing_status()
                logger.info(f"📊 SelfHealer status: {status}")
            
        except Exception as e:
            logger.error(f"❌ SelfHealer init error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.healer = None
    
    def _run_self_healing(self):
        """اجرای Self-Healing"""
        if self.healer is None:
            logger.warning("⚠️ SelfHealer not available")
            return
        
        try:
            metrics = self.get_alert_metrics()
            actions = self.healer.check_and_heal(metrics)
            
            if any(actions.values()):
                self.stats["healing_actions"] += 1
                self.stats["last_healing"] = datetime.now().isoformat()
                logger.info(f"🔄 Self-healing actions: {actions}")
                
                if actions.get("model_restored"):
                    self._collect_medium_metrics()
            
        except Exception as e:
            logger.error(f"❌ Self-healing error: {e}")
            self.stats["errors"] += 1
    
    # ============================================================
    # بقیه متدها (بدون تغییر)
    # ============================================================
    
    def _collect_light_metrics(self):
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
            
            self.metrics_cache["cpu"] = {"value": cpu, "timestamp": datetime.now().isoformat()}
            self.metrics_cache["ram"] = {"value": ram, "timestamp": datetime.now().isoformat()}
            self.metrics_cache["uptime"] = {"value": uptime, "timestamp": datetime.now().isoformat()}
            self.stats["collections"] += 1
            
        except Exception as e:
            logger.error(f"❌ Light metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_medium_metrics(self):
        try:
            from infrastructure.api.coinstats_client import coinstats_client
            from models.manager.model_manager import ModelManager
            from infrastructure.database import health_check
            
            # قیمت‌ها
            try:
                btc = coinstats_client.get_coin("bitcoin")
                if btc and "error" not in btc:
                    self.metrics_cache["btc_price"] = {
                        "value": btc.get("price", 0),
                        "change_24h": btc.get("priceChange1d", 0),
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.warning(f"⚠️ BTC price error: {e}")
            
            try:
                eth = coinstats_client.get_coin("ethereum")
                if eth and "error" not in eth:
                    self.metrics_cache["eth_price"] = {
                        "value": eth.get("price", 0),
                        "change_24h": eth.get("priceChange1d", 0),
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.warning(f"⚠️ ETH price error: {e}")
            
            # API status
            try:
                status = coinstats_client.get_status()
                api_status = status.get("status", "unknown") if status else "unknown"
                self.metrics_cache["api_status"] = {"value": api_status, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                logger.warning(f"⚠️ API status error: {e}")
            
            # Credits
            try:
                credits = coinstats_client.get_credits()
                api_credits = credits.get("remainingCredits", 0) if credits else 0
                self.metrics_cache["api_credits"] = {"value": api_credits, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                logger.warning(f"⚠️ Credits error: {e}")
            
            # Model status
            try:
                model_manager = ModelManager(coinstats_client)
                loaded = model_manager.current_model is not None
                version = model_manager.current_version or "N/A"
                
                accuracy = None
                if model_manager.db and model_manager.db.is_connected():
                    try:
                        result = model_manager.db.execute(
                            "SELECT accuracy FROM models WHERE version = %s",
                            (version if version != "N/A" else None,)
                        )
                        if result:
                            accuracy = result[0].get("accuracy")
                    except:
                        pass
                
                self.metrics_cache["model_status"] = {
                    "value": {"loaded": loaded, "version": version},
                    "timestamp": datetime.now().isoformat()
                }
                self.metrics_cache["model_accuracy"] = {
                    "value": accuracy,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.warning(f"⚠️ Model status error: {e}")
            
            # Databases
            try:
                health = health_check()
                dbs = {}
                for name, info in health.items():
                    dbs[name] = info.get("connected", False)
                self.metrics_cache["databases"] = {
                    "value": dbs,
                    "timestamp": datetime.now().isoformat()
                }
                logger.debug(f"✅ Databases: {dbs}")
            except Exception as e:
                logger.warning(f"⚠️ Databases error: {e}")
            
            # Request count
            try:
                stats = coinstats_client.get_stats()
                self.metrics_cache["request_count"] = {
                    "value": stats.get("total_requests", 0),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.warning(f"⚠️ Request count error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Medium metrics error: {e}")
            self.stats["errors"] += 1
    
    def _collect_heavy_metrics(self):
        try:
            from infrastructure.api.coinstats_client import coinstats_client
            
            # Fear & Greed
            try:
                fg = coinstats_client.get_fear_greed(use_cache=True)
                if fg and "now" in fg:
                    self.metrics_cache["fear_greed"] = {
                        "value": fg["now"].get("value", 50),
                        "classification": fg["now"].get("value_classification", "Neutral"),
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.warning(f"⚠️ Fear & Greed error: {e}")
            
            # BTC Dominance
            try:
                dominance = coinstats_client.get_btc_dominance(use_cache=True)
                if dominance:
                    self.metrics_cache["btc_dominance"] = {
                        "value": dominance.get("dominance", 50),
                        "timestamp": datetime.now().isoformat()
                    }
            except Exception as e:
                logger.warning(f"⚠️ BTC Dominance error: {e}")
            
            # News
            try:
                news = coinstats_client.get_news(limit=5)
                if news and "error" not in news:
                    self.metrics_cache["news"] = {"value": news, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                logger.warning(f"⚠️ News error: {e}")
            
            # Disk space
            try:
                usage = psutil.disk_usage('/')
                disk = {
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent
                }
                self.metrics_cache["disk_space"] = {"value": disk, "timestamp": datetime.now().isoformat()}
            except Exception as e:
                logger.warning(f"⚠️ Disk space error: {e}")
            
        except Exception as e:
            logger.error(f"❌ Heavy metrics error: {e}")
            self.stats["errors"] += 1
    
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
            "healing_actions": self.stats["healing_actions"],
            "last_healing": self.stats["last_healing"],
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
            "model_accuracy": cache.get("model_accuracy", {}).get("value", None),
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
                "accuracy": cache.get("model_accuracy", {}).get("value", None),
            },
            "databases": cache.get("databases", {}).get("value", {}),
            "disk": cache.get("disk_space", {}).get("value", {}),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_health(self) -> Dict:
        cache = self.metrics_cache
        cpu = cache.get("cpu", {}).get("value", 0)
        ram = cache.get("ram", {}).get("value", 0)
        databases = cache.get("databases", {}).get("value", {})
        
        cpu_status = "healthy" if cpu < 70 else "warning" if cpu < 90 else "critical"
        ram_status = "healthy" if ram < 70 else "warning" if ram < 90 else "critical"
        
        db_status = {}
        all_connected = True
        for name, connected in databases.items():
            db_status[name] = {"connected": connected, "status": "online" if connected else "offline"}
            if not connected:
                all_connected = False
        
        overall_status = "ok" if (cpu_status == "healthy" and ram_status == "healthy" and all_connected) else "degraded"
        
        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "cpu": {"status": cpu_status, "value": round(cpu, 1)},
                "ram": {"status": ram_status, "value": round(ram, 1)},
                "databases": db_status,
                "model": {
                    "loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
                    "version": cache.get("model_status", {}).get("value", {}).get("version", "N/A"),
                }
            }
        }
    
    def set_stop_event(self, event):
        self._stop_event = event
    
    def start(self):
        if self._running:
            return
        
        self._running = True
        logger.info("🔄 Metrics Scheduler started")
        
        try:
            self._collect_light_metrics()
            self._collect_medium_metrics()
            self._collect_heavy_metrics()
            self._run_self_healing()
            logger.info("✅ Initial all-level collection complete")
        except Exception as e:
            logger.error(f"❌ Initial collection error: {e}")
        
        last_light = time.time()
        last_medium = time.time()
        last_heavy = time.time()
        last_healing = time.time()
        cycle_count = 0
        
        while self._running and not (self._stop_event and self._stop_event.is_set()):
            try:
                now = time.time()
                cycle_count += 1
                
                if now - last_light >= self.light_interval:
                    self._collect_light_metrics()
                    last_light = now
                
                if now - last_medium >= self.medium_interval:
                    self._collect_medium_metrics()
                    last_medium = now
                    logger.debug(f"📊 Medium collected (cycle {cycle_count})")
                
                if now - last_heavy >= self.heavy_interval:
                    self._collect_heavy_metrics()
                    last_heavy = now
                    logger.debug(f"📊 Heavy collected (cycle {cycle_count})")
                
                if now - last_healing >= self.healing_interval:
                    self._run_self_healing()
                    last_healing = now
                
                self.stats["last_collection"] = datetime.now().isoformat()
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Scheduler error: {e}")
                self.stats["errors"] += 1
                time.sleep(5)
        
        logger.info("⏹️ Metrics Scheduler stopped")
    
    def stop(self):
        self._running = False
        logger.info("⏹️ Metrics Scheduler stopping")


# ============================================================
# ایجاد نمونه
# ============================================================
metrics_scheduler = MetricsScheduler()
