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

def get_ai_status() -> dict:
    """بررسی وضعیت کلی سرویس‌های هوش مصنوعی (مدل متنی و ایجنت Live)."""
    return call_flask("GET", "/api/ai/status")

def get_agent_tools_list() -> dict:
    """دریافت لیست تمام ابزارهای موجود برای ایجنت."""
    return call_flask("GET", "/api/ai/debug/tools")

def test_agent_tool(tool_name: str, kwargs: dict = None) -> dict:
    """
    تست یک ابزار خاص به صورت مستقیم (بدون دخالت مدل).
    استفاده: tool_name="get_price", kwargs={"coin": "bitcoin"}
    """
    return call_flask("POST", "/api/ai/debug/test-tool", json_body={
        "tool_name": tool_name,
        "kwargs": kwargs or {}
    })
