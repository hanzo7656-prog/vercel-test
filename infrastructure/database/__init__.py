# infrastructure/database/__init__.py
# ============================================================
# پکیج دیتابیس - نسخه ۳.۰
# Export کامل + Context managers + Helpers
# ============================================================

import logging
from typing import Optional, Any, Dict, List, Generator, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager

logger = logging.getLogger(__name__)


# ============================================================
# Lazy Imports (جلوگیری از Circular Import)
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


def _get_quota_manager():
    """Lazy import quota_manager"""
    from infrastructure.database.quota_manager import quota_manager
    return quota_manager


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
# توابع دسترسی سریع
# ============================================================

def get_db(name: Optional[str] = None):
    """
    دریافت دیتابیس با نام
    
    پارامترها:
        name: نام دیتابیس (پیش‌فرض: default از config)
    
    خروجی:
        نمونه دیتابیس یا None
    """
    return _get_registry().get(name, auto_reconnect=True)


def get_db_for(data_type: str):
    """
    دریافت دیتابیس مناسب برای نوع داده
    
    پارامترها:
        data_type: نوع داده (users, cache, predictions, ...)
    
    خروجی:
        نمونه دیتابیس
    """
    return _get_router().get_db_for(data_type)


def get_db_for_role(role: str, auto_reconnect: bool = True):
    """
    دریافت دیتابیس بر اساس نقش
    
    پارامترها:
        role: نقش (primary, backup, cache, analytics, logs, archive)
        auto_reconnect: تلاش برای reconnect
    
    خروجی:
        نمونه دیتابیس
    """
    return _get_router().get_db_for_role(role, auto_reconnect)


def get_primary():
    """
    دریافت دیتابیس اصلی (PostgreSQL primary)
    
    خروجی:
        PostgreSQLManager یا None
    """
    return _get_router().get_primary_db()


def get_cache():
    """
    دریافت دیتابیس کش (Redis)
    
    خروجی:
        RedisManager یا None
    """
    return _get_router().get_cache_db()


def get_backup():
    """
    دریافت دیتابیس پشتیبان (Neon backup)
    
    خروجی:
        PostgreSQLManager یا None
    """
    return _get_router().get_backup_db()


def get_analytics():
    """
    دریافت دیتابیس تحلیل (Neon analytics)
    
    خروجی:
        PostgreSQLManager یا None
    """
    return _get_router().get_analytics_db()


def get_logs_db():
    """
    دریافت دیتابیس لاگ (Neon logs)
    
    خروجی:
        PostgreSQLManager یا None
    """
    return _get_router().get_logs_db()


def get_archive():
    """
    دریافت دیتابیس آرشیو (Layerbase SQLite)
    
    خروجی:
        SQLiteManager یا None
    """
    return _get_router().get_archive_db()


# ============================================================
# توابع کمکی
# ============================================================

def health_check() -> Dict[str, Any]:
    """
    بررسی سلامت همه دیتابیس‌ها با reconnect خودکار
    
    خروجی:
        دیکشنری وضعیت
    """
    return _get_registry().get_health()


def health_summary() -> Dict[str, Any]:
    """
    خلاصه سلامت دیتابیس‌ها
    
    خروجی:
        دیکشنری خلاصه
    """
    return _get_registry().get_health_summary()


def ensure_databases_connected() -> Dict[str, bool]:
    """
    اطمینان از اتصال همه دیتابیس‌ها
    
    خروجی:
        دیکشنری {name: success}
    """
    try:
        from infrastructure.database.database_factory import (
            ensure_databases_connected as _ensure
        )
        return _ensure()
    except ImportError:
        logger.warning("⚠️ ensure_databases_connected not available")
        return {}


def get_all_databases() -> Dict[str, Any]:
    """
    دریافت همه دیتابیس‌های ثبت شده
    
    خروجی:
        دیکشنری {name: db_instance}
    """
    return _get_registry().get_all()


def get_database_status() -> Dict[str, Any]:
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
        "details": {},
    }
    
    for name, info in health.items():
        if info.get("connected") and info.get("ping"):
            summary["online"] += 1
            status = "online"
        elif info.get("connected"):
            summary["unknown"] += 1
            status = "unknown"
        else:
            summary["offline"] += 1
            status = "offline"
        
        summary["details"][name] = {
            "type": info.get("type", "unknown"),
            "status": status,
            "version": info.get("version", "unknown"),
            "used_mb": info.get("used_mb", 0),
            "quota": info.get("quota", {}),
        }
    
    return summary


def get_factory_status() -> Dict[str, Any]:
    """دریافت وضعیت کامل factory"""
    return _get_db_factory().get_status()


def get_databases_info() -> List[Dict[str, Any]]:
    """
    اطلاعات همه دیتابیس‌ها برای فرانت‌اند
    
    خروجی:
        لیست دیکشنری‌ها با اطلاعات کامل
    """
    return _get_db_factory().get_databases_info()


def is_ready() -> bool:
    """بررسی آماده بودن سیستم"""
    return _get_db_factory().is_ready()


def force_reconnect(db_name: Optional[str] = None) -> Dict[str, bool]:
    """
    Reconnect اجباری
    
    پارامترها:
        db_name: نام دیتابیس (None = همه)
    
    خروجی:
        دیکشنری {name: success}
    """
    return _get_db_factory().force_reconnect(db_name)


def reload_config() -> Dict[str, Any]:
    """بارگذاری مجدد تنظیمات"""
    return _get_db_factory().reload_config()


def shutdown_databases() -> None:
    """خاموش کردن کامل"""
    _get_db_factory().shutdown()


# ============================================================
# Quota Functions
# ============================================================

def get_quota(db_name: str) -> Dict[str, Any]:
    """
    دریافت Quota یک دیتابیس
    
    پارامترها:
        db_name: نام دیتابیس
    
    خروجی:
        دیکشنری Quota
    """
    return _get_quota_manager().get_quota(db_name)


def get_all_quotas() -> Dict[str, Dict[str, Any]]:
    """دریافت Quota همه دیتابیس‌ها"""
    return _get_quota_manager().get_all_quotas()


def set_database_limit(
    db_name: str,
    total_mb: Optional[int] = None,
    reserved_mb: Optional[int] = None,
    warn_threshold: Optional[int] = None,
    critical_threshold: Optional[int] = None,
    auto_cleanup: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    تنظیم محدودیت دیتابیس (از فرانت‌اند)
    
    پارامترها:
        db_name: نام دیتابیس
        total_mb: حجم کل
        reserved_mb: حجم رزرو
        warn_threshold: آستانه هشدار (درصد)
        critical_threshold: آستانه بحرانی (درصد)
        auto_cleanup: فعال بودن auto-cleanup
    
    خروجی:
        دیکشنری نتیجه
    """
    return _get_quota_manager().set_database_limit(
        db_name=db_name,
        total_mb=total_mb,
        reserved_mb=reserved_mb,
        warn_threshold=warn_threshold,
        critical_threshold=critical_threshold,
        auto_cleanup=auto_cleanup,
    )


def set_table_limit(
    db_name: str,
    table_name: str,
    max_mb: Optional[int] = None,
    retention_days: Optional[int] = None,
    keep_last_n: Optional[int] = None,
) -> Dict[str, Any]:
    """
    تنظیم محدودیت یک جدول خاص
    
    پارامترها:
        db_name: نام دیتابیس
        table_name: نام جدول
        max_mb: حداکثر حجم
        retention_days: مدت نگهداری (روز)
        keep_last_n: نگه‌داشتن n رکورد آخر
    
    خروجی:
        دیکشنری نتیجه
    """
    return _get_quota_manager().set_table_limit(
        db_name=db_name,
        table_name=table_name,
        max_mb=max_mb,
        retention_days=retention_days,
        keep_last_n=keep_last_n,
    )


def get_quota_status(db_name: str, used_mb: float) -> Dict[str, Any]:
    """
    بررسی Quota یک دیتابیس
    
    پارامترها:
        db_name: نام دیتابیس
        used_mb: حجم استفاده‌شده
    
    خروجی:
        دیکشنری وضعیت
    """
    return _get_quota_manager().check_quota(db_name, used_mb)


def get_quota_manager_stats() -> Dict[str, Any]:
    """آمار QuotaManager"""
    return _get_quota_manager().get_stats()


def reset_quota_overrides(db_name: Optional[str] = None) -> Dict[str, Any]:
    """
    بازنشانی overrides
    
    پارامترها:
        db_name: نام دیتابیس (None = همه)
    
    خروجی:
        دیکشنری نتیجه
    """
    return _get_quota_manager().reset_overrides(db_name)


# ============================================================
# Context Managers
# ============================================================

@contextmanager
def primary_transaction() -> Generator[Any, None, None]:
    """
    Context manager برای transaction روی primary
    
    استفاده:
        with primary_transaction() as db:
            db.execute("INSERT ...")
            db.execute("UPDATE ...")
    """
    db = get_primary()
    if db is None:
        raise RuntimeError("Primary database not available")
    
    with db.transaction():
        yield db


@contextmanager
def get_db_context(name: Optional[str] = None) -> Generator[Any, None, None]:
    """
    Context manager برای یک دیتابیس
    
    استفاده:
        with get_db_context("primary") as db:
            db.execute(...)
    """
    db = get_db(name)
    if db is None:
        raise RuntimeError(f"Database '{name}' not available")
    
    yield db


@contextmanager
def cache_context() -> Generator[Any, None, None]:
    """
    Context manager برای cache
    
    استفاده:
        with cache_context() as cache:
            cache.set("key", "value", ttl=60)
    """
    cache = get_cache()
    if cache is None:
        raise RuntimeError("Cache not available")
    
    yield cache


# ============================================================
# Async Support (آینده)
# ============================================================

@asynccontextmanager
async def get_async_db(name: Optional[str] = None) -> AsyncGenerator[Any, None]:
    """
    Context manager Async برای دیتابیس
    
    توجه: فعلاً sync است، در آینده async می‌شود
    
    استفاده:
        async with get_async_db("primary") as db:
            await db.execute_async(...)
    """
    db = get_db(name)
    if db is None:
        raise RuntimeError(f"Database '{name}' not available")
    
    yield db


# ============================================================
# Debug & Info
# ============================================================

def get_registry_stats() -> Dict[str, Any]:
    """آمار Registry"""
    return _get_registry().get_summary()


def get_router_stats() -> Dict[str, Any]:
    """آمار Router"""
    return _get_router().get_stats()


def get_all_stats() -> Dict[str, Any]:
    """
    همه آمارها در یک جا
    
    خروجی:
        دیکشنری شامل:
            - factory: آمار factory
            - registry: آمار registry
            - router: آمار router
            - quota: آمار quota
    """
    return {
        "factory": get_factory_status(),
        "registry": get_registry_stats(),
        "router": get_router_stats(),
        "quota": get_quota_manager_stats(),
    }


def print_status() -> None:
    """چاپ وضعیت در کنسول (برای debug)"""
    status = get_database_status()
    
    print("=" * 70)
    print("📊 Database Status")
    print("=" * 70)
    print(f"Total: {status['total']}")
    print(f"Online: {status['online']}")
    print(f"Offline: {status['offline']}")
    print()
    
    for name, info in status["details"].items():
        emoji = "✅" if info["status"] == "online" else "❌"
        print(
            f"{emoji} {name:12s} | {info['type']:20s} | "
            f"v{info['version']:10s} | {info['used_mb']:>8.2f} MB"
        )
    
    print("=" * 70)


# ============================================================
# Export
# ============================================================

__all__ = [
    # Database Access
    "get_db",
    "get_db_for",
    "get_db_for_role",
    "get_primary",
    "get_cache",
    "get_backup",
    "get_analytics",
    "get_logs_db",
    "get_archive",
    
    # Health
    "health_check",
    "health_summary",
    "ensure_databases_connected",
    "get_all_databases",
    "get_database_status",
    "get_factory_status",
    "get_databases_info",
    "is_ready",
    "force_reconnect",
    "reload_config",
    "shutdown_databases",
    
    # Quota
    "get_quota",
    "get_all_quotas",
    "set_database_limit",
    "set_table_limit",
    "get_quota_status",
    "get_quota_manager_stats",
    "reset_quota_overrides",
    
    # Context Managers
    "primary_transaction",
    "get_db_context",
    "cache_context",
    "get_async_db",
    
    # Debug
    "get_registry_stats",
    "get_router_stats",
    "get_all_stats",
    "print_status",
]


# ============================================================
# Auto-check on import (اختیاری، فقط در dev)
# ============================================================

logger.info("✅ infrastructure.database package loaded")
