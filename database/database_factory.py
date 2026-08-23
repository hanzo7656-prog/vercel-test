# database/database_factory.py
# ============================================================
# کارخانه ساخت اتصالات دیتابیس
# ============================================================

import os
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from database.base import DatabaseBase
from database.redis_manager import RedisManager
from config import get_config


logger = logging.getLogger(__name__)


class DatabaseFactory:
    """کارخانه مدیریت همه دیتابیس‌ها"""
    
    _instance = None
    _databases: Dict[str, DatabaseBase] = {}
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
            logger.warning("⚠️ config/databases.json یافت نشد، استفاده از تنظیمات پیش‌فرض")
            self._config = self._get_default_config()
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # جایگزینی متغیرهای محیطی
            for db_name, db_config in config_data.get("databases", {}).items():
                if "url" in db_config:
                    db_config["url"] = self._replace_env_vars(db_config["url"])
                if "token" in db_config:
                    db_config["token"] = self._replace_env_vars(db_config["token"])
            
            self._config = config_data
            logger.info(f"✅ تنظیمات دیتابیس‌ها بارگذاری شد: {len(self._config.get('databases', {}))} دیتابیس")
            
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
            self._config = self._get_default_config()


    def _get_default_config(self) -> Dict:
        """تنظیمات پیش‌فرض از فایل تنظیمات عمومی"""
        return {
            "databases": {
                "redis_main": {
                    "type": "redis",
                    "protocol": "rest",
                    "url": os.getenv("REDIS_MAIN_URL", ""),
                    "token": os.getenv("REDIS_MAIN_TOKEN", ""),
                    "enabled": True,
                    "description": "دیتابیس اصلی"
                }
            },
            "default_db": get_config("app.environment", "redis_main"),
            "settings": {
                "cache_ttl": get_config("cache.default_ttl", 3600),
                "retry_attempts": get_config("api.retry_attempts", 3),
                "retry_delay": get_config("api.retry_delay", 1)
            }
        }

    def _replace_env_vars(self, text: str) -> str:
        """جایگزینی متغیرهای محیطی در متن"""
        if not text:
            return text
    
        import re
        pattern = r'\${([^}]+)}'
      
        def replace_match(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                logger.warning(f"⚠️ متغیر محیطی {var_name} تنظیم نشده")
                return match.group(0)  # برگردوندن خود متن (با خطا)
            return env_value
    
        return re.sub(pattern, replace_match, text)
    
    def _connect_all(self):
        """اتصال به همه دیتابیس‌های فعال"""
        databases = self._config.get("databases", {})
        
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                logger.info(f"⏭️ دیتابیس {db_name} غیرفعال است")
                continue
            
            db_type = db_config.get("type", "redis")
            
            try:
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ نوع دیتابیس {db_type} پشتیبانی نمی‌شود")
                    continue
                
                if db_instance.connect():
                    self._databases[db_name] = db_instance
                    logger.info(f"✅ دیتابیس {db_name} متصل شد")
                else:
                    logger.error(f"❌ اتصال {db_name} ناموفق")
                    
            except Exception as e:
                logger.error(f"❌ خطا در راه‌اندازی {db_name}: {e}")
    
    def get_db(self, name: Optional[str] = None) -> Optional[DatabaseBase]:
        """دریافت یک دیتابیس خاص"""
        if name is None:
            name = self._config.get("default_db", "redis_main")
        
        return self._databases.get(name)
    
    def get_all_dbs(self) -> Dict[str, DatabaseBase]:
        """دریافت همه دیتابیس‌های متصل"""
        return self._databases
    
    # database/database_factory.py - اصلاح تابع get_health

    def get_health(self) -> Dict[str, Any]:
        """دریافت سلامت همه دیتابیس‌ها با اطلاعات کامل"""
        health = {}
        for name, db in self._databases.items():
            base_health = db.health_check()
            # اضافه کردن اطلاعات بیشتر برای نمایش
            health[name] = {
                **base_health,
                "url": db.config.get("url", ""),
                "token": db.config.get("token", ""),
                "type": db.config.get("type", "redis"),
                "protocol": db.config.get("protocol", "rest")
            }
        return health
        
    def add_database(self, name: str, config: Dict[str, Any]) -> bool:
        """افزودن دیتابیس جدید در زمان اجرا"""
        try:
            db_type = config.get("type", "redis")
            
            if db_type == "redis":
                db_instance = RedisManager(name, config)
            else:
                return False
            
            if db_instance.connect():
                self._databases[name] = db_instance
                # ذخیره در config
                self._config["databases"][name] = config
                self._save_config()
                logger.info(f"✅ دیتابیس جدید {name} اضافه شد")
                return True
            return False
            
        except Exception as e:
            logger.error(f"❌ خطا در افزودن {name}: {e}")
            return False
    
    def _save_config(self):
        """ذخیره تنظیمات (برای افزودن دینامیک)"""
        try:
            config_path = Path("config/databases.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره تنظیمات: {e}")
    
    def reload(self):
        """بارگذاری مجدد تنظیمات"""
        self._databases.clear()
        self._load_config()
        self._connect_all()
        logger.info("🔄 دیتابیس‌ها بارگذاری مجدد شدند")


# ============================================================
# نمونه Singleton
# ============================================================

db_factory = DatabaseFactory()


def get_db(name: Optional[str] = None) -> Optional[DatabaseBase]:
    """راهنمای سریع برای دریافت دیتابیس"""
    return db_factory.get_db(name)


def get_redis() -> Optional[DatabaseBase]:
    """راهنمای سریع برای دریافت Redis اصلی"""
    return db_factory.get_db("redis_main")


def health_check() -> Dict[str, Any]:
    """بررسی سلامت همه دیتابیس‌ها"""
    return db_factory.get_health()
