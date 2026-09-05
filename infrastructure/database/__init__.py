# infrastructure/database/__init__.py
# ============================================================
# پکیج دیتابیس - نسخه ۳.۱ (رفع Circular Import)
# ============================================================

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ============================================================
# Lazy Import برای جلوگیری از Circular Import
# ============================================================

def _get_registry():
    """Lazy import registry"""
    from infrastructure.database.registry import registry
    return registry


def _get_router():
    """Lazy import router"""
    from infrastructure.database.router import router
    return router


def _get_db_factory():
    """Lazy import db_factory"""
    from infrastructure.database.database_factory import db_factory
    return db_factory


def _get_postgresql_manager():
    """Lazy import PostgreSQLManager"""
    from infrastructure.database.postgresql_manager import PostgreSQLManager
    return PostgreSQLManager


def _get_sqlite_manager():
    """Lazy import SQLiteManager"""
    from infrastructure.database.sqlite_manager import SQLiteManager
    return SQLiteManager


def _get_redis_manager():
    """Lazy import RedisManager"""
    from infrastructure.database.redis_manager import RedisManager
    return RedisManager


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
    return _get_registry().get(name)


def get_db_for(data_type: str):
    """
    دریافت دیتابیس مناسب برای نوع داده
    
    پارامترها:
        data_type: نوع داده (users, cache, predictions, ...)
    
    خروجی:
        نمونه دیتابیس مناسب
    """
    return _get_router().get_db_for(data_type)


def get_cache():
    """
    دریافت دیتابیس کش (Redis)
    
    خروجی:
        نمونه RedisManager یا None
    """
    return _get_router().get_cache_db()


def get_primary():
    """
    دریافت دیتابیس اصلی (PostgreSQL) با Fallback خودکار
    
    خروجی:
        نمونه PostgreSQLManager یا None
    """
    router = _get_router()
    db = router.get_primary_db()
    
    if db is None or not db.is_connected():
        db = _get_registry().get("postgresql")
    
    if db is None:
        try:
            import json
            from pathlib import Path
            PostgreSQLManager = _get_postgresql_manager()
            
            with open("config/databases.json") as f:
                config = json.load(f)
            pg_config = config["databases"]["postgresql"]
            db = PostgreSQLManager("postgresql", pg_config)
            if db.connect():
                _get_registry().register("postgresql", db, ["primary", "users", "history", "logs"])
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
    return _get_router().get_backup_db()


def health_check():
    """
    بررسی سلامت همه دیتابیس‌ها با reconnect خودکار
    
    خروجی:
        دیکشنری وضعیت همه دیتابیس‌ها
    """
    registry = _get_registry()
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


def ensure_databases_connected():
    """
    اطمینان از اتصال همه دیتابیس‌ها
    """
    try:
        from infrastructure.database.database_factory import ensure_databases_connected as _ensure
        return _ensure()
    except ImportError:
        logger.warning("⚠️ ensure_databases_connected not available")
        return False


def get_all_databases():
    """
    دریافت همه دیتابیس‌های ثبت شده
    
    خروجی:
        دیکشنری {name: db_instance}
    """
    return _get_registry().get_all()


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
# Export همه توابع
# ============================================================

__all__ = [
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
