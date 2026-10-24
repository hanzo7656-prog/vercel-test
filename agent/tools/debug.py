# agent/tools/debug.py
from .base import call_flask

def check_health() -> dict:
    """بررسی سلامت کلی سیستم."""
    return call_flask("GET", "/api/health")

def get_debug_status() -> dict:
    """دریافت وضعیت CPU/RAM/Disk سیستم."""
    return call_flask("GET", "/api/debug/status")

def get_recent_logs(level: str = "ERROR", limit: int = 20) -> dict:
    """دریافت لاگ‌های اخیر سیستم با فیلتر سطح (DEBUG/INFO/WARNING/ERROR)."""
    return call_flask("GET", "/api/debug/logs", params={"level": level, "limit": limit})

def get_db_health() -> dict:
    """دریافت خلاصه سلامت همه دیتابیس‌ها (PostgreSQL, Redis, SQLite)."""
    return call_flask("GET", "/api/db/health/summary")

def get_apis_health() -> dict:
    """بررسی سلامت APIهای خارجی (Binance, CoinStats, FreeCrypto)."""
    return call_flask("GET", "/api/health/apis")

def get_cache_stats() -> dict:
    """دریافت آمار کش Redis (hits, misses, active_redis)."""
    return call_flask("GET", "/api/debug/cache/stats")
