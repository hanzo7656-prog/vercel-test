# database/__init__.py
# ============================================================
# پکیج دیتابیس - با قابلیت توسعه
# ============================================================

from database.registry import registry
from database.router import router
from database.base import DatabaseBase
from database.redis_manager import RedisManager
from database.postgresql_manager import PostgreSQLManager
from database.sqlite_manager import SQLiteManager

# ✅ اجرای دیتابیس فکتوری در زمان import
from database.database_factory import db_factory


def get_db(name: str = None):
    """دریافت دیتابیس با نام"""
    return registry.get(name)


def get_db_for(data_type: str):
    """دریافت دیتابیس مناسب برای نوع داده"""
    return router.get_db_for(data_type)


def get_cache():
    """دریافت دیتابیس کش (Redis)"""
    return router.get_cache_db()


def get_primary():
    """دریافت دیتابیس اصلی (PostgreSQL)"""
    return router.get_primary_db()


def get_backup():
    """دریافت دیتابیس پشتیبان (SQLite)"""
    return router.get_backup_db()


def health_check():
    """بررسی سلامت همه دیتابیس‌ها"""
    return registry.get_health()


__all__ = [
    'registry',
    'router',
    'get_db',
    'get_db_for',
    'get_cache',
    'get_primary',
    'get_backup',
    'health_check',
    'DatabaseBase',
    'RedisManager',
    'PostgreSQLManager',
    'SQLiteManager'
]
