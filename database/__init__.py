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
    """دریافت دیتابیس اصلی (PostgreSQL) - با Fallback"""
    db = router.get_primary_db()
    
    # اگر db None بود یا وصل نبود، از registry بگیر
    if db is None or not db.is_connected():
        db = registry.get("postgresql")
    
    # اگر باز هم None بود، یک نمونه جدید بساز
    if db is None:
        try:
            from database.postgresql_manager import PostgreSQLManager
            import json
            from pathlib import Path
            
            with open("config/databases.json") as f:
                config = json.load(f)
            pg_config = config["databases"]["postgresql"]
            db = PostgreSQLManager("postgresql", pg_config)
            if db.connect():
                registry.register("postgresql", db, ["primary", "users", "history", "logs"])
                print("✅ PostgreSQL به صورت خودکار reconnect شد")
        except Exception as e:
            print(f"❌ خطا در reconnect PostgreSQL: {e}")
    
    return db


def get_backup():
    """دریافت دیتابیس پشتیبان (SQLite)"""
    return router.get_backup_db()


def health_check():
    """بررسی سلامت همه دیتابیس‌ها با reconnect خودکار"""
    health = registry.get_health()
    
    # reconnect خودکار برای دیتابیس‌هایی که ورژن unknown دارند
    for db_name, db_info in health.items():
        if db_info.get('version') == 'unknown' or db_info.get('version') is None:
            db = registry.get(db_name)
            if db and not db.is_connected():
                try:
                    db.connect()
                    # به‌روزرسانی اطلاعات
                    if hasattr(db, 'get_stats'):
                        stats = db.get_stats()
                        if stats and stats.get('version'):
                            db_info['version'] = stats.get('version')
                except Exception as e:
                    print(f"⚠️ Reconnect error for {db_name}: {e}")
    
    return health

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
