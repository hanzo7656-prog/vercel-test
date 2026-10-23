# agent/tools/debug.py
# ============================================================
# ابزارهای دیباگ - پوسته نازک روی Flask
# ============================================================

import os
import requests
from typing import Optional

FLASK_BASE_URL = os.getenv("FLASK_BASE_URL", "https://your-app.com")
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "agent_debugger")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "")

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """لاگین با حساب اختصاصی ایجنت و برگرداندن session."""
    global _session
    if _session is not None:
        return _session
    
    sess = requests.Session()
    resp = sess.post(
        f"{FLASK_BASE_URL}/api/login",
        json={"username": AGENT_USERNAME, "password": AGENT_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    if not resp.json().get("success"):
        raise RuntimeError(f"Agent login failed: {resp.json()}")
    _session = sess
    return sess


def check_health() -> dict:
    """بررسی سلامت کلی سیستم (GET /api/health)."""
    try:
        r = _get_session().get(f"{FLASK_BASE_URL}/api/health", timeout=10)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_debug_status() -> dict:
    """وضعیت CPU/RAM/Disk سیستم (GET /api/debug/status)."""
    try:
        r = _get_session().get(f"{FLASK_BASE_URL}/api/debug/status", timeout=10)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_logs(level: str = "ERROR", limit: int = 50) -> dict:
    """دریافت لاگ‌های سیستم (GET /api/debug/logs)."""
    try:
        r = _get_session().get(
            f"{FLASK_BASE_URL}/api/debug/logs",
            params={"level": level, "limit": limit},
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_db_health_summary() -> dict:
    """خلاصه سلامت دیتابیس‌ها (GET /api/db/health/summary)."""
    try:
        r = _get_session().get(f"{FLASK_BASE_URL}/api/db/health/summary", timeout=10)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_apis_health() -> dict:
    """سلامت APIهای خارجی (GET /api/health/apis)."""
    try:
        r = _get_session().get(f"{FLASK_BASE_URL}/api/health/apis", timeout=10)
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
