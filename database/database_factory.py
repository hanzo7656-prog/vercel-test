# database/database_factory.py
# ============================================================
# کارخانه ساخت اتصالات دیتابیس - نسخه ۲.۰ با Retry و Self-Healing
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

logger = logging.getLogger(__name__)


class DatabaseFactory:
    """کارخانه ساخت و ثبت دیتابیس‌ها با مکانیزم Retry"""
    
    _instance = None
    _config = {}
    _max_retries = 3
    _retry_delay = 2  # ثانیه
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            self._connect_all_with_retry()
    
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
            routing = config_data.get("routing", {})
            router.set_routing(routing)
            
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
    
    def _connect_all_with_retry(self):
        """اتصال به همه دیتابیس‌ها با Retry"""
        databases = self._config.get("databases", {})
        
        for db_name, db_config in databases.items():
            if not db_config.get("enabled", True):
                logger.info(f"⏭️ دیتابیس {db_name} غیرفعال است")
                continue
            
            # تلاش برای اتصال با Retry
            success = self._connect_with_retry(db_name, db_config)
            
            if success:
                logger.info(f"✅ دیتابیس {db_name} با موفقیت ثبت شد")
            else:
                logger.error(f"❌ دیتابیس {db_name} پس از {self._max_retries} تلاش ثبت نشد")
    
    def _connect_with_retry(self, db_name: str, db_config: Dict) -> bool:
        """اتصال به یک دیتابیس با Retry"""
        db_type = db_config.get("type", "redis")
        roles = db_config.get("roles", [])
        
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"🔄 تلاش {attempt}/{self._max_retries} برای اتصال به {db_name}")
                
                # ساخت نمونه دیتابیس
                if db_type == "redis":
                    db_instance = RedisManager(db_name, db_config)
                elif db_type == "postgresql":
                    db_instance = PostgreSQLManager(db_name, db_config)
                elif db_type == "sqlite":
                    db_instance = SQLiteManager(db_name, db_config)
                else:
                    logger.warning(f"⚠️ نوع دیتابیس {db_type} پشتیبانی نمی‌شود")
                    return False
                
                # اتصال
                if db_instance.connect():
                    # ثبت در registry
                    registry.register(db_name, db_instance, roles)
                    logger.info(f"✅ دیتابیس {db_name} با نقش‌های {roles} ثبت شد")
                    return True
                else:
                    logger.warning(f"⚠️ تلاش {attempt} برای {db_name} ناموفق بود")
                    
            except Exception as e:
                logger.error(f"❌ خطا در تلاش {attempt} برای {db_name}: {e}")
            
            # اگر آخرین تلاش نبود، صبر کن
            if attempt < self._max_retries:
                time.sleep(self._retry_delay * attempt)  # افزایش تدریجی Delay
        
        return False
    
    def force_reconnect(self, db_name: str = None) -> Dict[str, bool]:
        """
       强制 reconnect یک یا همه دیتابیس‌ها (برای Self-Healing)
        
        پارامترها:
            db_name: نام دیتابیس (اگر None باشد، همه دیتابیس‌ها)
        
        خروجی:
            دیکشنری از وضعیت reconnect
        """
        results = {}
        databases = self._config.get("databases", {})
        
        if db_name:
            # فقط یک دیتابیس
            if db_name in databases:
                db_config = databases[db_name]
                success = self._connect_with_retry(db_name, db_config)
                results[db_name] = success
            else:
                results[db_name] = False
                logger.warning(f"⚠️ دیتابیس {db_name} در تنظیمات یافت نشد")
        else:
            # همه دیتابیس‌ها
            for name, config in databases.items():
                if config.get("enabled", True):
                    success = self._connect_with_retry(name, config)
                    results[name] = success
        
        return results


# ایجاد نمونه
db_factory = DatabaseFactory()


def ensure_databases_connected():
    """
    تابع کمکی برای اطمینان از اتصال دیتابیس‌ها (Self-Healing)
    
    این تابع رو می‌تونید در app.py یا هر جای دیگه صدا بزنید
    """
    from database import get_primary, get_cache, get_backup, registry
    
    results = {
        "primary": False,
        "cache": False,
        "backup": False
    }
    
    # بررسی دیتابیس اصلی
    primary = get_primary()
    if primary is None or not primary.is_connected():
        logger.warning("⚠️ اتصال دیتابیس اصلی برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("postgresql")
        results["primary"] = reconnect_result.get("postgresql", False)
    else:
        results["primary"] = True
    
    # بررسی کش
    cache = get_cache()
    if cache is None or not cache.is_connected():
        logger.warning("⚠️ اتصال Redis برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("redis")
        results["cache"] = reconnect_result.get("redis", False)
    else:
        results["cache"] = True
    
    # بررسی بک‌آپ
    backup = get_backup()
    if backup is None or not backup.is_connected():
        logger.warning("⚠️ اتصال SQLite برقرار نیست، تلاش برای reconnect...")
        reconnect_result = db_factory.force_reconnect("sqlite")
        results["backup"] = reconnect_result.get("sqlite", False)
    else:
        results["backup"] = True
    
    # گزارش نهایی
    all_ok = all(results.values())
    if all_ok:
        logger.info("✅ همه دیتابیس‌ها متصل هستند")
    else:
        logger.warning(f"⚠️ وضعیت دیتابیس‌ها: {results}")
    
    return results
