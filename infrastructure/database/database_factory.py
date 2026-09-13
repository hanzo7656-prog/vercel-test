# infrastructure/database/database_factory.py
# ============================================================
# کارخانه ساخت دیتابیس‌ها - نسخه ۳.۰
# Init هوشمند + Graceful Shutdown + Health Loop
# ============================================================

import os
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from infrastructure.database.base import DatabaseBase
from infrastructure.database.postgresql_manager import PostgreSQLManager
from infrastructure.database.redis_manager import RedisManager
from infrastructure.database.sqlite_manager import SQLiteManager
from infrastructure.database.registry import registry
from infrastructure.database.router import router

logger = logging.getLogger(__name__)


class DatabaseFactory:
    """
    کارخانه ساخت و ثبت دیتابیس‌ها
    
    ویژگی‌ها:
        - Init هوشمند با Retry
        - Health check periodic
        - Graceful shutdown
        - Config از فایل + ENV
        - Thread-safe
    
    رفع باگ‌ها:
        - Retry منطق مبهم → پیاده‌سازی واضح
        - بدون graceful shutdown → اضافه شد
        - Health check بدون jitter → jitter اضافه شد
    
    ارتقاها:
        - ENV override برای credentials
        - Health check با jitter
        - Graceful shutdown
        - Config validation
        - آمار کامل
    """
    
    _instance: Optional['DatabaseFactory'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'DatabaseFactory':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._config: Dict[str, Any] = {}
        self._config_path: Path = Path("config/databases.json")
        
        # Health check
        self._health_thread: Optional[threading.Thread] = None
        self._health_stop_event: threading.Event = threading.Event()
        self._health_check_interval: int = 30
        self._health_check_jitter: int = 5
        self._health_enabled: bool = False
        
        # آمار
        self._init_started_at: Optional[datetime] = None
        self._init_completed_at: Optional[datetime] = None
        self._total_retries: int = 0
        self._failed_connections: List[str] = []
        
        # تنظیمات
        self._max_retries: int = 3
        self._retry_delay: float = 2.0
        
        # Init
        self._load_config()
        self._connect_all_with_retry()
        self._start_health_check()
    
    # ============================================================
    # Config Loading
    # ============================================================
    
    def _load_config(self) -> None:
        """بارگذاری تنظیمات از فایل + ENV override"""
        try:
            if not self._config_path.exists():
                logger.error(f"❌ Config file not found: {self._config_path}")
                self._config = {"databases": {}, "default": "primary"}
                return
            
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            
            # ENV override برای credentials
            self._apply_env_overrides()
            
            # تنظیم در registry و router
            registry.set_config(self._config)
            router.set_routing(self._config.get("routing", {}))
            
            # تنظیم read/write split
            rw_split = self._config.get("settings", {}).get(
                "read_write_split", False
            )
            router.set_read_write_split(rw_split)
            
            # تنظیم health check interval
            settings = self._config.get("settings", {})
            self._health_check_interval = settings.get(
                "health_check_interval", 30
            )
            
            logger.info(
                f"✅ Config loaded: "
                f"{len(self._config.get('databases', {}))} databases"
            )
            
        except Exception as e:
            logger.error(f"❌ Config load error: {e}")
            self._config = {"databases": {}, "default": "primary"}
    
    def _apply_env_overrides(self) -> None:
        """
        اعمال ENV overrides
        
        ENV variables:
            DB_PRIMARY_HOST, DB_PRIMARY_PASSWORD, ...
            یا
            NEON_PRIMARY_URL, UPSTASH_REDIS_TOKEN, ...
        """
        env_mapping = {
            "primary": {
                "host": "NEON_PRIMARY_HOST",
                "password": "NEON_PRIMARY_PASSWORD",
                "user": "NEON_PRIMARY_USER",
                "database": "NEON_PRIMARY_DB",
            },
            "backup": {
                "host": "NEON_BACKUP_HOST",
                "password": "NEON_BACKUP_PASSWORD",
                "user": "NEON_BACKUP_USER",
                "database": "NEON_BACKUP_DB",
            },
            "analytics": {
                "host": "NEON_ANALYTICS_HOST",
                "password": "NEON_ANALYTICS_PASSWORD",
                "user": "NEON_ANALYTICS_USER",
                "database": "NEON_ANALYTICS_DB",
            },
            "logs": {
                "host": "NEON_LOGS_HOST",
                "password": "NEON_LOGS_PASSWORD",
                "user": "NEON_LOGS_USER",
                "database": "NEON_LOGS_DB",
            },
            "archive": {
                "host": "LAYERBASE_HOST",
                "password": "LAYERBASE_PASSWORD",
                "user": "LAYERBASE_USER",
                "database": "LAYERBASE_DB",
            },
            "cache": {
                "url": "UPSTASH_REDIS_URL",
                "token": "UPSTASH_REDIS_TOKEN",
                "redis_url": "UPSTASH_REDIS_URL_FULL",
            },
        }
        
        databases = self._config.get("databases", {})
        applied = 0
        
        for db_name, mapping in env_mapping.items():
            if db_name not in databases:
                continue
            
            conn_config = databases[db_name].get("connection", {})
            
            for config_key, env_key in mapping.items():
                env_value = os.getenv(env_key)
                if env_value:
                    conn_config[config_key] = env_value
                    applied += 1
        
        if applied > 0:
            logger.info(f"✅ Applied {applied} ENV overrides")
    
    # ============================================================
    # Connection
    # ============================================================
    
    def _connect_all_with_retry(self) -> None:
        """اتصال به همه دیتابیس‌ها با Retry"""
        self._init_started_at = datetime.now()
        databases = self._config.get("databases", {})
        
        logger.info(f"🔄 Initializing {len(databases)} databases...")
        
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                logger.info(f"⏭️ Database '{db_name}' is disabled")
                continue
            
            success = self._connect_with_retry(db_name, db_config)
            
            if success:
                logger.info(f"✅ Database '{db_name}' registered")
            else:
                logger.error(
                    f"❌ Database '{db_name}' failed after "
                    f"{self._max_retries} attempts"
                )
                self._failed_connections.append(db_name)
        
        self._init_completed_at = datetime.now()
        
        duration = (
            self._init_completed_at - self._init_started_at
        ).total_seconds()
        
        logger.info(
            f"✅ Initialization complete in {duration:.2f}s "
            f"(failed: {len(self._failed_connections)})"
        )
    
    def _connect_with_retry(
        self,
        db_name: str,
        db_config: Dict[str, Any]
    ) -> bool:
        """اتصال به یک دیتابیس با Retry"""
        db_type = db_config.get("type", "postgresql")
        roles = db_config.get("roles", [])
        
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(
                    f"🔄 Connecting to '{db_name}' "
                    f"(attempt {attempt}/{self._max_retries})"
                )
                
                # ساخت نمونه بر اساس نوع
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                elif db_type == "sqlite_via_postgresql":
                    db_instance = SQLiteManager(db_name, db_config)
                elif db_type == "postgresql":
                    db_instance = PostgreSQLManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ Unsupported type: {db_type}")
                    return False
                
                # اتصال
                if db_instance.connect():
                    registry.register(db_name, db_instance, roles)
                    return True
                
                logger.warning(
                    f"⚠️ Attempt {attempt} failed for '{db_name}'"
                )
                
            except Exception as e:
                logger.error(
                    f"❌ Attempt {attempt} error for '{db_name}': {e}"
                )
            
            if attempt < self._max_retries:
                delay = self._retry_delay * attempt
                logger.info(f"⏳ Retry in {delay:.1f}s...")
                time.sleep(delay)
                self._total_retries += 1
        
        return False
    
    # ============================================================
    # Health Check
    # ============================================================
    
    def _start_health_check(self) -> None:
        """شروع Health Check دوره‌ای"""
        if self._health_enabled:
            return
        
        self._health_enabled = True
        self._health_stop_event.clear()
        
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="DatabaseHealthCheck"
        )
        self._health_thread.start()
        
        logger.info(
            f"✅ Health check started "
            f"(interval: {self._health_check_interval}s)"
        )
    
    def _health_check_loop(self) -> None:
        """حلقه Health Check"""
        import random
        
        while not self._health_stop_event.is_set():
            try:
                # Jitter برای جلوگیری از همزمانی
                jitter = random.uniform(0, self._health_check_jitter)
                
                # بررسی همه دیتابیس‌ها
                with registry._lock:
                    databases = dict(registry._databases)
                
                for name, db in databases.items():
                    if not db.is_connected():
                        logger.warning(
                            f"⚠️ Database '{name}' disconnected, "
                            f"attempting reconnect..."
                        )
                        try:
                            if db.connect():
                                logger.info(f"✅ '{name}' reconnected")
                            else:
                                logger.error(f"❌ '{name}' reconnect failed")
                        except Exception as e:
                            logger.error(f"❌ '{name}' reconnect error: {e}")
                
                # Sleep با jitter
                sleep_time = self._health_check_interval + jitter
                self._health_stop_event.wait(sleep_time)
                
            except Exception as e:
                logger.error(f"❌ Health check error: {e}")
                self._health_stop_event.wait(60)
        
        logger.info("⏹️ Health check stopped")
    
    def _stop_health_check(self) -> None:
        """توقف Health Check"""
        self._health_enabled = False
        self._health_stop_event.set()
        
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=5)
        
        logger.info("⏹️ Health check stopped")
    
    # ============================================================
    # Public API
    # ============================================================
    
    def force_reconnect(
        self,
        db_name: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Reconnect اجباری
        
        پارامترها:
            db_name: نام دیتابیس (None = همه)
        
        خروجی:
            دیکشنری {name: success}
        """
        results: Dict[str, bool] = {}
        
        if db_name:
            db = registry.get(db_name, auto_reconnect=False)
            if db:
                try:
                    if db.is_connected():
                        results[db_name] = True
                    else:
                        results[db_name] = db.connect()
                except Exception as e:
                    logger.error(f"❌ Reconnect error for '{db_name}': {e}")
                    results[db_name] = False
            else:
                results[db_name] = False
                logger.warning(f"⚠️ Database '{db_name}' not found")
        else:
            # همه
            databases = self._config.get("databases", {})
            
            for name, db_config in databases.items():
                if not db_config.get("enabled", True):
                    continue
                
                success = self._connect_with_retry(name, db_config)
                results[name] = success
        
        return results
    
    def reload_config(self) -> Dict[str, Any]:
        """
        بارگذاری مجدد تنظیمات
        
        خروجی:
            دیکشنری نتیجه
        """
        try:
            # ذخیره دیتابیس‌های فعلی
            old_databases = registry.get_all()
            
            # بارگذاری جدید
            self._load_config()
            
            # بررسی تغییرات
            new_config = self._config.get("databases", {})
            changes: List[str] = []
            
            for name, config in new_config.items():
                if config.get("enabled", True):
                    if name not in old_databases:
                        changes.append(f"added:{name}")
            
            for name in old_databases:
                if name not in new_config:
                    changes.append(f"removed:{name}")
                    registry.unregister(name)
            
            # اتصال به جدیدها
            for name, config in new_config.items():
                if name not in old_databases and config.get("enabled", True):
                    self._connect_with_retry(name, config)
            
            logger.info(f"✅ Config reloaded (changes: {changes})")
            
            return {
                "success": True,
                "changes": changes,
                "databases_count": len(new_config),
            }
            
        except Exception as e:
            logger.error(f"❌ Config reload error: {e}")
            return {"success": False, "error": str(e)}
    
    def shutdown(self) -> None:
        """
        خاموش کردن کامل
        
        - توقف health check
        - قطع همه اتصالات
        """
        logger.info("⏹️ Shutting down DatabaseFactory...")
        
        # توقف health check
        self._stop_health_check()
        
        # قطع همه دیتابیس‌ها
        for name, db in registry.get_all().items():
            try:
                db.disconnect()
                logger.debug(f"✅ '{name}' disconnected")
            except Exception as e:
                logger.error(f"❌ Disconnect error for '{name}': {e}")
        
        logger.info("✅ DatabaseFactory shutdown complete")
    
    # ============================================================
    # Status & Stats
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت کامل
        
        خروجی:
            دیکشنری شامل:
                - initialized: آیا init شده
                - health: سلامت دیتابیس‌ها
                - summary: خلاصه
                - router_stats: آمار router
        """
        return {
            "initialized": self._init_completed_at is not None,
            "init_started_at": (
                self._init_started_at.isoformat()
                if self._init_started_at else None
            ),
            "init_completed_at": (
                self._init_completed_at.isoformat()
                if self._init_completed_at else None
            ),
            "total_retries": self._total_retries,
            "failed_connections": list(self._failed_connections),
            "health": registry.get_health(),
            "summary": registry.get_summary(),
            "router_stats": router.get_stats(),
            "health_check_enabled": self._health_enabled,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """خلاصه سلامت"""
        return registry.get_health_summary()
    
    def get_databases_info(self) -> List[Dict[str, Any]]:
        """اطلاعات همه دیتابیس‌ها برای فرانت‌اند"""
        health = registry.get_health()
        
        result = []
        for name, info in health.items():
            db = registry.get(name, auto_reconnect=False)
            
            result.append({
                "name": name,
                "type": info.get("type", "unknown"),
                "host": info.get("host", ""),
                "database": info.get("database", ""),
                "connected": info.get("connected", False),
                "enabled": info.get("enabled", True),
                "version": info.get("version", "unknown"),
                "used_mb": info.get("used_mb", 0),
                "uptime_formatted": info.get("uptime_formatted", "0s"),
                "quota": info.get("quota", {}),
                "roles": db.config.get("roles", []) if db else [],
                "description": db.config.get("description", "") if db else "",
            })
        
        return result
    
    def is_ready(self) -> bool:
        """
        بررسی آماده بودن
        
        خروجی:
            True اگر init کامل و primary متصل باشد
        """
        if self._init_completed_at is None:
            return False
        
        primary = registry.get_by_role("primary")
        if primary is None:
            return False
        
        return primary.is_connected()


# ============================================================
# Singleton
# ============================================================

db_factory: DatabaseFactory = DatabaseFactory()


# ============================================================
# Helper Functions
# ============================================================

def ensure_databases_connected() -> Dict[str, bool]:
    """
    اطمینان از اتصال دیتابیس‌ها (Self-Healing)
    
    خروجی:
        دیکشنری {name: connected}
    """
    results: Dict[str, bool] = {}
    
    for name, db in registry.get_all().items():
        try:
            if db.is_connected():
                results[name] = True
            else:
                logger.warning(f"⚠️ '{name}' disconnected, reconnecting...")
                results[name] = db.connect()
        except Exception as e:
            logger.error(f"❌ Reconnect error for '{name}': {e}")
            results[name] = False
    
    all_ok = all(results.values())
    
    if all_ok:
        logger.debug("✅ All databases connected")
    else:
        failed = [k for k, v in results.items() if not v]
        logger.warning(f"⚠️ Failed databases: {failed}")
    
    return results


def get_factory_status() -> Dict[str, Any]:
    """دریافت وضعیت factory"""
    return db_factory.get_status()


def shutdown_databases() -> None:
    """خاموش کردن کامل"""
    db_factory.shutdown()
