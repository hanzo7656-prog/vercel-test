# infrastructure/ai/agent_tools.py
# ============================================================
# ابزارهای ایجنت - اتصال به Flask
# ============================================================

import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any

BASE_URL = os.getenv("BASE_URL", "https://vercel-test-f4bv.onrender.com")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "")

_session: Optional[requests.Session] = None

def _get_session() -> requests.Session:
    """لاگین با حساب agent_debugger و برگرداندن session."""
    global _session
    if _session is not None:
        return _session
    
    sess = requests.Session()
    resp = sess.post(
        f"{BASE_URL}/api/login",
        json={"username": "agent_debugger", "password": AGENT_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Agent login failed: {data}")
    _session = sess
    return sess

def _call_flask(method: str, path: str, **kwargs) -> Dict[str, Any]:
    """فراخوانی امن اندپوینت Flask."""
    try:
        sess = _get_session()
        resp = sess.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================
# ابزارهای دیباگ
# ============================================================

def check_health() -> dict:
    """بررسی سلامت کلی سیستم."""
    return _call_flask("GET", "/api/health")

def get_debug_status() -> dict:
    """دریافت وضعیت CPU/RAM/Disk."""
    return _call_flask("GET", "/api/debug/status")

def get_recent_logs(level: str = "ERROR", limit: int = 20) -> dict:
    """دریافت لاگ‌های اخیر سیستم."""
    return _call_flask("GET", "/api/debug/logs", params={"level": level, "limit": limit})

def get_db_health() -> dict:
    """دریافت خلاصه سلامت دیتابیس‌ها."""
    return _call_flask("GET", "/api/db/health/summary")

# ============================================================
# ابزارهای بازار
# ============================================================

def get_price(coin: str = "bitcoin") -> dict:
    """دریافت قیمت لحظه‌ای یک ارز (مثلا bitcoin)."""
    return _call_flask("GET", f"/api/coinstats/price/{coin}")

def get_fear_greed() -> dict:
    """دریافت شاخص ترس و طمع بازار."""
    return _call_flask("GET", "/api/coinstats/fear-greed")

def get_btc_dominance() -> dict:
    """دریافت سلطه بیت‌کوین."""
    return _call_flask("GET", "/api/coinstats/btc-dominance")

# لیست نهایی ابزارها برای دادن به Agent
ALL_TOOLS = [
    check_health,
    get_debug_status,
    get_recent_logs,
    get_db_health,
    get_price,
    get_fear_greed,
    get_btc_dominance,
]
