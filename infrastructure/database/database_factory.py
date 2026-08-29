# infrastructure/database/database_factory.py
# ============================================================
# کارخانه ساخت اتصالات دیتابیس - نسخه ۳.۰ (انتقال به Infrastructure)
# ============================================================

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from infrastructure.database.base import DatabaseBase
from infrastructure.database.redis_manager import RedisManager
from infrastructure.database.postgresql_manager import PostgreSQLManager
from infrastructure.database.sqlite_manager import SQLiteManager
from infrastructure.database.registry import registry
from infrastructure.database.router import router

logger = logging.getLogger(__name__)


class DatabaseFactory:
    """کارخانه ساخت و ثبت دیتابیس‌ها با مکانیزم Retry و Self-Healing"""
    
    _instance = None
    _config: Dict[str, Any] = {}
    _max_retries: int = 3
    _retry_delay: int = 2
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            self._connect_all_with_retry()
            self._start_health_check()
    
    def _load_config(self) -> None:
        """بارگذاری تنظیمات دیتابیس‌ها"""
        config_path: Path = Path("config/databases.json")
        
        if not config_path.exists():
            logger.warning("⚠️ config/databases.json یافت نشد")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data: Dict[str, Any] = json.load(f)
            
            self._config = config_data
            logger.info("✅ تنظیمات دیتابیس‌ها بارگذاری شد")
            
            registry.set_config(config_data)
            routing: Dict[str, str] = config_data.get("routing", {})
            router.set_routing(routing)
            
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
    
    def _connect_all_with_retry(self) -> None:
        """اتصال به همه دیتابیس‌ها با Retry"""
        databases: Dict[str, Any] = self._config.get("databases", {})
        
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                logger.info(f"⏭️ دیتابیس {db_name} غیرفعال است")
                continue
            
            success: bool = self._connect_with_retry(db_name, db_config)
            
            if success:
                logger.info(f"✅ دیتابیس {db_name} با موفقیت ثبت شد")
            else:
                logger.error(f"❌ دیتابیس {db_name} پس از {self._max_retries} تلاش ثبت نشد")
    
    def _connect_with_retry(self, db_name: str, db_config: Dict[str, Any]) -> bool:
        """اتصال به یک دیتابیس با Retry"""
        db_type: str = db_config.get("type", "redis")
        roles: List[str] = db_config.get("roles", [])
        
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"🔄 تلاش {attempt}/{self._max_retries} برای اتصال به {db_name}")
                
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                elif db_type == "postgresql":
                    db_instance = PostgreSQLManager(db_name, db_config)
                elif db_type == "sqlite":
                    db_instance = SQLiteManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ نوع دیتابیس {db_type} پشتیبانی نمی‌شود")
                    return False
                
                if db_instance.connect():
                    registry.register(db_name, db_instance, roles)
                    logger.info(f"✅ دیتابیس {db_name} با نقش‌های {roles} ثبت شد")
                    return True
                else:
                    logger.warning(f"⚠️ تلاش {attempt} برای {db_name} ناموفق بود")
                    
            except Exception as e:
                logger.error(f"❌ خطا در تلاش {attempt} برای {db_name}: {e}")
            
            if attempt < self._max_retries:
                time.sleep(self._retry_delay * attempt)
        
        return False
    
    def _start_health_check(self) -> None:
        """شروع Health Check دوره‌ای برای همه دیتابیس‌ها"""
        def health_check_loop() -> None:
            while True:
                try:
                    for name, db in registry.get_all().items():
                        if not db.is_connected():
                            logger.warning(f"⚠️ Database {name} disconnected, reconnecting...")
                            if db.connect():
                                logger.info(f"✅ Database {name} reconnected")
                            else:
                                logger.error(f"❌ Database {name} reconnect failed")
                    time.sleep(30)
                except Exception as e:
                    logger.error(f"❌ Health check error: {e}")
                    time.sleep(60)
        
        try:
            from core.threading_manager import threading_manager
            threading_manager.register(
                name="db_health_check",
                target=health_check_loop,
                daemon=True,
                auto_restart=True,
                max_restarts=10
            )
            logger.info("✅ Database health check started")
        except ImportError:
            logger.warning("⚠️ ThreadingManager not available, health check disabled")
    
    def force_reconnect(self, db_name: Optional[str] = None) -> Dict[str, bool]:
        """Reconnect اجباری یک یا همه دیتابیس‌ها"""
        results: Dict[str, bool] = {}
        databases: Dict[str, Any] = self._config.get("databases", {})
        
        if db_name:
            if db_name in databases:
                db_config = databases[db_name]
                results[db_name] = self._connect_with_retry(db_name, db_config)
            else:
                results[db_name] = False
                logger.warning(f"⚠️ دیتابیس {db_name} در تنظیمات یافت نشد")
        else:
            for name, config in databases.items():
                if config.get("enabled", True):
                    results[name] = self._connect_with_retry(name, config)
        
        return results


# ایجاد نمونه
db_factory: DatabaseFactory = DatabaseFactory()


def ensure_databases_connected() -> Dict[str, bool]:
    """اطمینان از اتصال دیتابیس‌ها (Self-Healing)"""
    from infrastructure.database import get_primary, get_cache, get_backup
    
    results: Dict[str, bool] = {
        "primary": False,
        "cache": False,
        "backup": False
    }
    
    primary = get_primary()
    if primary is None or not primary.is_connected():
        logger.warning("⚠️ اتصال دیتابیس اصلی برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("postgresql")
        results["primary"] = reconnect_result.get("postgresql", False)
    else:
        results["primary"] = True
    
    cache = get_cache()
    if cache is None or not cache.is_connected():
        logger.warning("⚠️ اتصال Redis برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("redis")
        results["cache"] = reconnect_result.get("redis", False)
    else:
        results["cache"] = True
    
    backup = get_backup()
    if backup is None or not backup.is_connected():
        logger.warning("⚠️ اتصال SQLite برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("sqlite")
        results["backup"] = reconnect_result.get("sqlite", False)
    else:
        results["backup"] = True
    
    all_ok = all(results.values())
    if all_ok:
        logger.info("✅ همه دیتابیس‌ها متصل هستند")
    else:
        logger.warning(f"⚠️ وضعیت دیتابیس‌ها: {results}")
    
    return results
