# infrastructure/database/__init__.py
# ============================================================
# پکیج دیتابیس - نسخه ۳.۰ (انتقال به Infrastructure)
# ============================================================

from infrastructure.database.registry import registry
from infrastructure.database.router import router
from infrastructure.database.base import DatabaseBase
from infrastructure.database.redis_manager import RedisManager
from infrastructure.database.postgresql_manager import PostgreSQLManager
from infrastructure.database.sqlite_manager import SQLiteManager
from infrastructure.database.database_factory import db_factory, ensure_databases_connected


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
    """دریافت دیتابیس اصلی (PostgreSQL) - با Fallback"""
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
        except Exception as e:
            logger.error(f"❌ PostgreSQL reconnect error: {e}")
    
    return db


def get_backup():
    """دریافت دیتابیس پشتیبان (SQLite)"""
    return router.get_backup_db()


def health_check():
    """بررسی سلامت همه دیتابیس‌ها با reconnect خودکار"""
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


# ایمپورت‌های لازم برای logger
import logging
logger = logging.getLogger(__name__)

__all__ = [
    'registry',
    'router',
    'get_db',
    'get_db_for',
    'get_cache',
    'get_primary',
    'get_backup',
    'health_check',
    'db_factory',
    'ensure_databases_connected',
    'DatabaseBase',
    'RedisManager',
    'PostgreSQLManager',
    'SQLiteManager'
]
