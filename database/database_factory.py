# database/database_factory.py
# ============================================================
# کارخانه دیتابیس - نسخه ۳.۰ با Self-Healing
# ============================================================

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from database.base import DatabaseBase
from database.redis_manager import RedisManager
from database.postgresql_manager import PostgreSQLManager
from database.sqlite_manager import SQLiteManager
from database.registry import registry
from database.router import router
from core.threading_manager import threading_manager

logger = logging.getLogger(__name__)


class DatabaseFactory:
    """کارخانه ساخت دیتابیس با Self-Healing"""
    
    _instance = None
    _config = {}
    _max_retries = 3
    _retry_delay = 2
    _health_check_thread = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            self._connect_all_with_retry()
            self._start_health_check()
    
    def _load_config(self):
        config_path = Path("config/databases.json")
        if not config_path.exists():
            logger.warning("⚠️ config/databases.json not found")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            self._config = config_data
            registry.set_config(config_data)
            router.set_routing(config_data.get("routing", {}))
            logger.info("✅ Database config loaded")
        except Exception as e:
            logger.error(f"❌ Config load error: {e}")
    
    def _connect_all_with_retry(self):
        databases = self._config.get("databases", {})
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                continue
            success = self._connect_with_retry(db_name, db_config)
            if success:
                logger.info(f"✅ Database {db_name} registered")
            else:
                logger.error(f"❌ Database {db_name} registration failed")
    
    def _connect_with_retry(self, db_name: str, db_config: Dict) -> bool:
        db_type = db_config.get("type", "redis")
        roles = db_config.get("roles", [])
        
        for attempt in range(1, self._max_retries + 1):
            try:
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                elif db_type == "postgresql":
                    db_instance = PostgreSQLManager(db_name, db_config)
                elif db_type == "sqlite":
                    db_instance = SQLiteManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ Unsupported type: {db_type}")
                    return False
                
                if db_instance.connect():
                    registry.register(db_name, db_instance, roles)
                    return True
                else:
                    logger.warning(f"⚠️ Attempt {attempt} failed for {db_name}")
                    
            except Exception as e:
                logger.error(f"❌ Attempt {attempt} error: {e}")
            
            if attempt < self._max_retries:
                time.sleep(self._retry_delay * attempt)
        
        return False
    
    def _start_health_check(self):
        """شروع Health Check دوره‌ای برای همه دیتابیس‌ها"""
        def health_check_loop():
            while True:
                try:
                    # بررسی سلامت همه دیتابیس‌ها
                    for name, db in registry.get_all().items():
                        if not db.is_connected():
                            logger.warning(f"⚠️ Database {name} disconnected, reconnecting...")
                            if db.connect():
                                logger.info(f"✅ Database {name} reconnected")
                            else:
                                logger.error(f"❌ Database {name} reconnect failed")
                    time.sleep(30)  # هر ۳۰ ثانیه
                except Exception as e:
                    logger.error(f"❌ Health check error: {e}")
                    time.sleep(60)
        
        # استفاده از ThreadingManager
        from core.threading_manager import threading_manager
        threading_manager.register(
            name="db_health_check",
            target=health_check_loop,
            daemon=True,
            auto_restart=True,
            max_restarts=10
        )
        logger.info("✅ Database health check started")
    
    def force_reconnect(self, db_name: str = None) -> Dict[str, bool]:
        """Reconnect اجباری"""
        results = {}
        databases = self._config.get("databases", {})
        
        if db_name:
            if db_name in databases:
                db_config = databases[db_name]
                results[db_name] = self._connect_with_retry(db_name, db_config)
            else:
                results[db_name] = False
        else:
            for name, config in databases.items():
                if config.get("enabled", True):
                    results[name] = self._connect_with_retry(name, config)
        
        return results


# نمونه Singleton
db_factory = DatabaseFactory()


def ensure_databases_connected():
    """اطمینان از اتصال همه دیتابیس‌ها"""
    from database import get_primary, get_cache, get_backup
    
    results = {
        "primary": False,
        "cache": False,
        "backup": False
    }
    
    primary = get_primary()
    if not primary or not primary.is_connected():
        logger.warning("⚠️ Primary disconnected, reconnecting...")
        results["primary"] = db_factory.force_reconnect("postgresql").get("postgresql", False)
    else:
        results["primary"] = True
    
    cache = get_cache()
    if not cache or not cache.is_connected():
        logger.warning("⚠️ Cache disconnected, reconnecting...")
        results["cache"] = db_factory.force_reconnect("redis").get("redis", False)
    else:
        results["cache"] = True
    
    backup = get_backup()
    if not backup or not backup.is_connected():
        logger.warning("⚠️ Backup disconnected, reconnecting...")
        results["backup"] = db_factory.force_reconnect("sqlite").get("sqlite", False)
    else:
        results["backup"] = True
    
    return results
