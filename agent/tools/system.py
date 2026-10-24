# agent/tools/system.py
from .base import call_flask

def get_app_stats() -> dict:
    """دریافت آمار اپلیکیشن (RAM, CPU, uptime)."""
    return call_flask("GET", "/api/app/stats")

def get_metrics() -> dict:
    """دریافت متریک‌های لحظه‌ای سیستم."""
    return call_flask("GET", "/api/metrics")

def get_metrics_dashboard() -> dict:
    """دریافت متریک‌های داشبورد (همه داده‌ها یکجا)."""
    return call_flask("GET", "/api/metrics/dashboard")

def get_thread_status() -> dict:
    """دریافت وضعیت Threadهای سیستم."""
    return call_flask("GET", "/api/metrics/threads")
