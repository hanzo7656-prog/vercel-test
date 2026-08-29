# infrastructure/database/__init__.py
# ============================================================
# پکیج دیتابیس - نسخه ۳.۰ (نهایی)
# ============================================================

from infrastructure.database.registry import registry
from infrastructure.database.router import router
from infrastructure.database.base import DatabaseBase
from infrastructure.database.redis_manager import RedisManager
from infrastructure.database.postgresql_manager import PostgreSQLManager
from infrastructure.database.sqlite_manager import SQLiteManager
from infrastructure.database.database_factory import db_factory, ensure_databases_connected

import logging
logger = logging.getLogger(__name__)


# ============================================================
# توابع کمکی برای دسترسی سریع به دیتابیس‌ها
# ============================================================

def get_db(name: str = None):
    """
    دریافت دیتابیس با نام
    
    پارامترها:
        name: نام دیتابیس (پیش‌فرض: دیتابیس پیش‌فرض از config)
    
    خروجی:
        نمونه دیتابیس یا None
    """
    return registry.get(name)


def get_db_for(data_type: str):
    """
    دریافت دیتابیس مناسب برای نوع داده
    
    پارامترها:
        data_type: نوع داده (users, cache, predictions, ...)
    
    خروجی:
        نمونه دیتابیس مناسب
    """
    return router.get_db_for(data_type)


def get_cache():
    """
    دریافت دیتابیس کش (Redis)
    
    خروجی:
        نمونه RedisManager یا None
    """
    return router.get_cache_db()


def get_primary():
    """
    دریافت دیتابیس اصلی (PostgreSQL) با Fallback خودکار
    
    خروجی:
        نمونه PostgreSQLManager یا None
    """
    db = router.get_primary_db()
    
    if db is None or not db.is_connected():
        db = registry.get("postgresql")
    
    if db is None:
        try:
            import json
            from pathlib import Path
            
            with open("config/databases.json") as f:
                config = json.load(f)
            pg_config = config["databases"]["postgresql"]
            db = PostgreSQLManager("postgresql", pg_config)
            if db.connect():
                registry.register("postgresql", db, ["primary", "users", "history", "logs"])
                logger.info("✅ PostgreSQL reconnected automatically")
        except FileNotFoundError:
            logger.error("❌ config/databases.json not found")
        except Exception as e:
            logger.error(f"❌ PostgreSQL reconnect error: {e}")
    
    return db


def get_backup():
    """
    دریافت دیتابیس پشتیبان (SQLite)
    
    خروجی:
        نمونه SQLiteManager یا None
    """
    return router.get_backup_db()


def health_check():
    """
    بررسی سلامت همه دیتابیس‌ها با reconnect خودکار
    
    خروجی:
        دیکشنری وضعیت همه دیتابیس‌ها
    """
    health = registry.get_health()
    
    for db_name, db_info in health.items():
        if db_info.get('version') == 'unknown' or db_info.get('version') is None:
            db = registry.get(db_name)
            if db and not db.is_connected():
                try:
                    db.connect()
                    if hasattr(db, 'get_stats'):
                        stats = db.get_stats()
                        if stats and stats.get('version'):
                            db_info['version'] = stats.get('version')
                except Exception as e:
                    logger.warning(f"⚠️ Reconnect error for {db_name}: {e}")
    
    return health


def get_all_databases():
    """
    دریافت همه دیتابیس‌های ثبت شده
    
    خروجی:
        دیکشنری {name: db_instance}
    """
    return registry.get_all()


def get_database_status():
    """
    دریافت وضعیت خلاصه همه دیتابیس‌ها
    
    خروجی:
        دیکشنری وضعیت
    """
    health = health_check()
    summary = {
        "total": len(health),
        "online": 0,
        "offline": 0,
        "unknown": 0,
        "details": {}
    }
    
    for name, info in health.items():
        if info.get("connected") and info.get("ping"):
            summary["online"] += 1
        elif info.get("connected"):
            summary["unknown"] += 1
        else:
            summary["offline"] += 1
        
        summary["details"][name] = {
            "type": info.get("type", "unknown"),
            "status": "online" if (info.get("connected") and info.get("ping")) else "offline",
            "version": info.get("version", "unknown")
        }
    
    return summary


# ============================================================
# Export همه توابع و کلاس‌ها
# ============================================================

__all__ = [
    # کلاس‌ها
    'DatabaseBase',
    'RedisManager',
    'PostgreSQLManager',
    'SQLiteManager',
    
    # نمونه‌های Singleton
    'registry',
    'router',
    'db_factory',
    
    # توابع اصلی
    'get_db',
    'get_db_for',
    'get_cache',
    'get_primary',
    'get_backup',
    'health_check',
    'ensure_databases_connected',
    'get_all_databases',
    'get_database_status',
]
