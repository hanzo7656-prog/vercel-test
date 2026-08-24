# database/database_factory.py
# ============================================================
# کارخانه ساخت اتصالات دیتابیس
# ============================================================

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from database.base import DatabaseBase
from database.redis_manager import RedisManager
from database.postgresql_manager import PostgreSQLManager
from database.sqlite_manager import SQLiteManager
from database.registry import registry
from database.router import router

logger = logging.getLogger(__name__)


class DatabaseFactory:
    """کارخانه ساخت و ثبت دیتابیس‌ها"""
    
    _instance = None
    _config = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            self._connect_all()
    
    def _load_config(self):
        """بارگذاری تنظیمات دیتابیس‌ها"""
        config_path = Path("config/databases.json")
        
        if not config_path.exists():
            logger.warning("⚠️ config/databases.json یافت نشد")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            self._config = config_data
            logger.info(f"✅ تنظیمات دیتابیس‌ها بارگذاری شد")

            registry.set_config(config_data)
            # تنظیم مسیریاب
            routing = config_data.get("routing", {})
            router.set_routing(routing)
            
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
    
    def _connect_all(self):
        """اتصال به همه دیتابیس‌ها"""
        databases = self._config.get("databases", {})
        
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                logger.info(f"⏭️ دیتابیس {db_name} غیرفعال است")
                continue
            
            db_type = db_config.get("type", "redis")
            roles = db_config.get("roles", [])
            
            try:
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                elif db_type == "postgresql":
                    db_instance = PostgreSQLManager(db_name, db_config)
                elif db_type == "sqlite":
                    db_instance = SQLiteManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ نوع دیتابیس {db_type} پشتیبانی نمی‌شود")
                    continue
                
                if db_instance.connect():
                    registry.register(db_name, db_instance, roles)
                else:
                    logger.error(f"❌ اتصال {db_name} ناموفق")
                    
            except Exception as e:
                logger.error(f"❌ خطا در راه‌اندازی {db_name}: {e}")


# ایجاد نمونه
db_factory = DatabaseFactory()
