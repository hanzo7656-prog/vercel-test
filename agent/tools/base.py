# agent/tools/base.py
import os
import requests
from typing import Optional, Dict, Any

BASE_URL = os.getenv("BASE_URL", "https://vercel-test-f4bv.onrender.com")
AGENT_USERNAME = "agent_debugger"  # hardcode
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
        json={"username": AGENT_USERNAME, "password": AGENT_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Agent login failed: {data}")
    _session = sess
    return sess


def call_flask(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """فراخوانی یک اندپوینت Flask با session ایجنت."""
    try:
        sess = _get_session()
        resp = sess.request(
            method=method,
            url=f"{BASE_URL}{path}",
            params=params,
            json=json_body,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
