# agent/tools/database.py
from .base import call_flask

def get_predictions(limit: int = 20) -> dict:
    """دریافت آخرین پیش‌بینی‌های ذخیره‌شده در دیتابیس."""
    return call_flask("GET", "/api/predict/history", params={"limit": limit})

def get_prediction_stats() -> dict:
    """دریافت آمار پیش‌بینی‌ها (تعداد BUY/SELL/NEUTRAL و میانگین اطمینان)."""
    return call_flask("GET", "/api/predict/history/stats")

def get_ohlcv(coin: str = "BTC/USDT", interval: str = "1h", range_: str = "1mo") -> dict:
    """دریافت داده‌های OHLCV یک ارز (interval: 5m/15m/1h/4h/1d)."""
    return call_flask("GET", "/api/coinstats/ohlcv",
                      params={"pair": coin, "interval": interval, "range": range_})

def get_db_tables(db_name: str = "primary") -> dict:
    """لیست جداول یک دیتابیس PostgreSQL (primary/backup/analytics/logs)."""
    return call_flask("GET", f"/api/db/postgresql/{db_name}/tables")

def get_table_data(db_name: str, table_name: str, limit: int = 50) -> dict:
    """دریافت داده‌های یک جدول خاص از دیتابیس."""
    return call_flask("GET", f"/api/db/postgresql/{db_name}/tables/{table_name}",
                      params={"limit": limit})

def get_table_sizes(db_name: str = "primary") -> dict:
    """دریافت حجم جداول یک دیتابیس PostgreSQL."""
    return call_flask("GET", f"/api/db/postgresql/{db_name}/table-sizes")
