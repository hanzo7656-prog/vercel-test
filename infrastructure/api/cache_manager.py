# infrastructure/api/cache_manager.py
# ============================================================
# مدیریت کش با دو Redis - نسخه ۳.۴
# Dual Redis + Auto-Failover + Session Migration 
# + Management API برای آمار ماهانه دقیق
# ============================================================

import base64
import json
import logging
import os
import threading
import time
from typing import Any, Optional, Dict, List
from datetime import datetime, timezone

import requests

from infrastructure.database.registry import registry

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

SAFE_COMMAND_LIMIT = 480_000
FAILOVER_CHECK_INTERVAL = 300
PRIMARY_CACHE_NAME = "cache"
BACKUP_CACHE_NAME = "cache_backup"
MGMT_CACHE_TTL = 300  # ۵ دقیقه cache برای Management API


# ============================================================
# Upstash Configuration
# ============================================================

UPSTASH_CONFIG = {
    PRIMARY_CACHE_NAME: {
        "endpoint": "chief-buck-93038.upstash.io",
        "rest_url": os.getenv("UPSTASH_PRIMARY_REST_URL", "https://chief-buck-93038.upstash.io"),
        "rest_token": os.getenv("UPSTASH_PRIMARY_REST_TOKEN", ""),
        "mgmt_email": os.getenv("UPSTASH_PRIMARY_MGMT_EMAIL", ""),
        "mgmt_api_key": os.getenv("UPSTASH_PRIMARY_MGMT_API_KEY", ""),
        "mgmt_db_id": os.getenv("UPSTASH_PRIMARY_DB_ID", ""),
        "commands_limit": 500_000,
        "memory_limit_mb": 256,
        "bandwidth_limit_gb": 10,
    },
    BACKUP_CACHE_NAME: {
        "endpoint": "hardy-tahr-212869.upstash.io",
        "rest_url": os.getenv("UPSTASH_BACKUP_REST_URL", "https://hardy-tahr-212869.upstash.io"),
        "rest_token": os.getenv("UPSTASH_BACKUP_REST_TOKEN", ""),
        "mgmt_email": os.getenv("UPSTASH_BACKUP_MGMT_EMAIL", ""),
        "mgmt_api_key": os.getenv("UPSTASH_BACKUP_MGMT_API_KEY", ""),
        "mgmt_db_id": os.getenv("UPSTASH_BACKUP_DB_ID", ""),
        "commands_limit": 500_000,
        "memory_limit_mb": 256,
        "bandwidth_limit_gb": 10,
    },
}


# ============================================================
# 🆕 Management API Cache
# ============================================================

_mgmt_cache: Dict[str, Dict[str, Any]] = {}
_mgmt_cache_lock = threading.Lock()


def _fetch_mgmt_stats(name: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    گرفتن آمار ماهانه از Upstash Management API.
    
    این آمار دقیقاً همون عددی است که توی داشبورد Upstash می‌بینی.
    cache ۵ دقیقه‌ای دارد تا از rate limit جلوگیری شود.
    """
    config = UPSTASH_CONFIG.get(name, {})
    db_id = config.get("mgmt_db_id")
    email = config.get("mgmt_email")
    api_key = config.get("mgmt_api_key")

    if not all([db_id, email, api_key]):
        logger.debug(f"⚠️ Management API not configured for '{name}'")
        return {}

    # ─── چک cache ───
    with _mgmt_cache_lock:
        now = time.time()
        cached = _mgmt_cache.get(name)
        if cached and not force_refresh:
            age = now - cached.get("_cached_at", 0)
            if age < MGMT_CACHE_TTL:
                return cached.get("data", {})

    # ─── درخواست به Management API ───
    try:
        auth = base64.b64encode(f"{email}:{api_key}".encode()).decode()
        response = requests.get(
            f"https://api.upstash.com/v2/redis/stats/{db_id}",
            headers={"Authorization": f"Basic {auth}"},
            timeout=10,
        )

        if response.status_code == 401:
            logger.error(f"❌ Mgmt API 401 for '{name}': invalid credentials")
            return {}
        if response.status_code == 403:
            logger.error(f"❌ Mgmt API 403 for '{name}': not native account")
            return {}
        if response.status_code != 200:
            logger.warning(f"⚠️ Mgmt API {response.status_code} for '{name}'")
            return {}

        data = response.json()

        # ─── ذخیره در cache ───
        with _mgmt_cache_lock:
            _mgmt_cache[name] = {
                "_cached_at": now,
                "data": data,
            }

        return data

    except Exception as e:
        logger.warning(f"⚠️ Mgmt API error for '{name}': {e}")
        return {}


# ============================================================
# REST API helpers (fallback)
# ============================================================

def _fetch_upstash_info(name: str) -> Dict[str, str]:
    """گرفتن INFO از REST API (fallback)"""
    config = UPSTASH_CONFIG.get(name)
    if not config or not config["rest_token"]:
        return {}

    try:
        response = requests.post(
            config["rest_url"],
            headers={
                "Authorization": f"Bearer {config['rest_token']}",
                "Content-Type": "application/json",
            },
            json=["INFO"],
            timeout=5,
        )
        response.raise_for_status()

        data = response.json()
        info_text = data.get("result", "")

        if not info_text:
            return {}

        info = {}
        for line in info_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()

        return info
    except Exception as e:
        logger.warning(f"⚠️ Upstash {name} info error: {e}")
        return {}


def _fetch_upstash_dbsize(name: str) -> int:
    """گرفتن تعداد کلیدها از REST API"""
    config = UPSTASH_CONFIG.get(name)
    if not config or not config["rest_token"]:
        return 0

    try:
        response = requests.post(
            config["rest_url"],
            headers={
                "Authorization": f"Bearer {config['rest_token']}",
                "Content-Type": "application/json",
            },
            json=["DBSIZE"],
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
        return int(result.get("result", 0))
    except Exception:
        return 0


def _get_upstash_commands(name: str) -> int:
    """
    گرفتن تعداد commands مصرف‌شده‌ی واقعی.
    
    ⭐ اولویت ۱: Management API (دقیق مثل داشبورد)
    ⭐ اولویت ۲: REST INFO (fallback ناقص)
    """
    # ─── اول Management API ───
    mgmt = _fetch_mgmt_stats(name)
    if mgmt and "total_monthly_requests" in mgmt:
        try:
            return int(mgmt["total_monthly_requests"])
        except (ValueError, TypeError):
            pass

    # ─── fallback به REST INFO ───
    info = _fetch_upstash_info(name)
    if not info:
        return -1
    try:
        return int(info.get("total_commands_processed", 0))
    except (ValueError, TypeError):
        return -1


# ============================================================
# DualRedisClient
# ============================================================

class DualRedisClient:
    """Wrapper روی دو RedisManager که سوئیچ خودکار انجام می‌دهد."""

    def __init__(self):
        self._active_name: str = PRIMARY_CACHE_NAME
        self._client: Optional[Any] = None
        self._lock: threading.Lock = threading.Lock()

        self._command_count: int = 0
        self._command_reset_at: float = time.time()

        self._last_failover_check: float = 0
        self._failover_count: int = 0
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[float] = None
        self._last_switch_at: Optional[float] = None

        self._stats: Dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "failovers": 0,
            "primary_uses": 0,
            "backup_uses": 0,
            "manual_switches": 0,
            "sessions_migrated": 0,
        }

        self._startup_check()
        logger.info("✅ DualRedisClient v3.4 initialized")

    # ------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------

    def _startup_check(self) -> None:
        try:
            db = registry.get(PRIMARY_CACHE_NAME, auto_reconnect=False)
            if db is None:
                logger.warning(f"⚠️ Cache: '{PRIMARY_CACHE_NAME}' not in registry")
                self._active_name = BACKUP_CACHE_NAME
                self._client = registry.get(BACKUP_CACHE_NAME, auto_reconnect=False)
                return

            if not db.is_connected():
                logger.warning("⚠️ Cache: primary not connected at startup")
                other = registry.get(BACKUP_CACHE_NAME, auto_reconnect=False)
                if other is not None and other.is_connected():
                    self._active_name = BACKUP_CACHE_NAME
                    self._client = other
                    self._failover_count += 1
                    self._stats["failovers"] += 1
                return

            # ⭐ از Management API می‌خونیم (عدد واقعی)
            remote_commands = _get_upstash_commands(PRIMARY_CACHE_NAME)

            if remote_commands < 0:
                # fallback
                try:
                    info = db._client.info()
                    remote_commands = info.get("total_commands_processed", 0)
                except Exception:
                    remote_commands = 0

            if remote_commands >= SAFE_COMMAND_LIMIT:
                logger.warning(
                    f"⚠️ Cache: primary full ({remote_commands:,} commands), "
                    f"switching to '{BACKUP_CACHE_NAME}'"
                )
                self._migrate_sessions(db, registry.get(BACKUP_CACHE_NAME, auto_reconnect=False))
                other = registry.get(BACKUP_CACHE_NAME, auto_reconnect=False)
                if other is not None and other.is_connected():
                    self._active_name = BACKUP_CACHE_NAME
                    self._client = other
                    self._failover_count += 1
                    self._stats["failovers"] += 1
                    self._last_switch_at = time.time()
            else:
                self._command_count = remote_commands
                percent = round(remote_commands / SAFE_COMMAND_LIMIT * 100, 1)
                logger.info(f"✅ Cache: primary OK ({remote_commands:,} commands, {percent}%)")
        except Exception as e:
            logger.error(f"❌ Cache: startup check error: {e}")

    # ------------------------------------------------------------
    # Session migration
    # ------------------------------------------------------------

    def _migrate_sessions(self, old_db: Any, new_db: Any) -> int:
        if old_db is None or new_db is None:
            return 0
        try:
            if not old_db.is_connected() or not new_db.is_connected():
                return 0
            session_keys = old_db.scan_keys("session:*", count=200)
            if not session_keys:
                return 0
            logger.info(f"🔄 Cache: migrating {len(session_keys)} sessions")
            migrated = 0
            for key in session_keys:
                try:
                    value = old_db.get(key)
                    ttl = old_db.ttl(key)
                    if value is not None:
                        if ttl and ttl > 0:
                            new_db.set(key, value, ttl)
                        else:
                            new_db.set(key, value, 86400)
                        migrated += 1
                except Exception:
                    continue
            self._stats["sessions_migrated"] += migrated
            logger.info(f"✅ Cache: migrated {migrated} sessions")
            return migrated
        except Exception as e:
            logger.warning(f"⚠️ Cache: session migration failed: {e}")
            return 0

    # ------------------------------------------------------------
    # Client resolution
    # ------------------------------------------------------------

    def _resolve_client(self) -> Optional[Any]:
        try:
            db = registry.get(self._active_name, auto_reconnect=False)
            if db is None:
                other = self._get_other_name()
                db = registry.get(other, auto_reconnect=False)
                if db is not None:
                    self._active_name = other
                    self._stats["failovers"] += 1
            return db
        except Exception as e:
            logger.error(f"❌ Cache: resolve client error: {e}")
            return None

    def _get_other_name(self) -> str:
        if self._active_name == PRIMARY_CACHE_NAME:
            return BACKUP_CACHE_NAME
        return PRIMARY_CACHE_NAME

    # ------------------------------------------------------------
    # Failover
    # ------------------------------------------------------------

    def _should_switch_preemptive(self) -> bool:
        return self._command_count >= SAFE_COMMAND_LIMIT

    def _is_quota_error(self, err: Exception) -> bool:
        msg = str(err).lower()
        keywords = [
            "max requests", "command limit", "quota", "limit exceeded",
            "too many requests", "rate limit", "oom command", "maxmemory",
            "out of memory", "used memory", "bandwidth", "traffic exceeded",
        ]
        return any(k in msg for k in keywords)

    def _switch_to_other(self, reason: str) -> bool:
        other = self._get_other_name()
        try:
            old_db = self._client or self._resolve_client()
            new_db = registry.get(other, auto_reconnect=True)
            if new_db is None or not new_db.is_connected():
                return False
            if old_db is not None:
                self._migrate_sessions(old_db, new_db)
            with self._lock:
                old = self._active_name
                self._active_name = other
                self._client = new_db
                self._failover_count += 1
                self._stats["failovers"] += 1
                self._command_count = 0
                self._command_reset_at = time.time()
                self._last_switch_at = time.time()
            logger.warning(f"⚠️ Cache: failover '{old}' → '{other}' ({reason})")
            return True
        except Exception as e:
            logger.error(f"❌ Cache: failover error: {e}")
            return False

    def _check_periodic_failover(self) -> None:
        if self._failover_count == 0:
            return
        now = time.time()
        if now - self._last_failover_check < FAILOVER_CHECK_INTERVAL:
            return
        self._last_failover_check = now
        other = self._get_other_name()
        try:
            db = registry.get(other, auto_reconnect=False)
            if db is None:
                return
            if not db.is_connected():
                if not db.connect():
                    return

            # ⭐ آمار واقعی از Mgmt API
            remote_commands = _get_upstash_commands(other)

            if remote_commands < 0:
                try:
                    info = db._client.info()
                    remote_commands = info.get("total_commands_processed", 0)
                except Exception:
                    return

            commands_ok = remote_commands < SAFE_COMMAND_LIMIT

            # memory check از Mgmt API
            mgmt = _fetch_mgmt_stats(other)
            memory_ok = True
            if mgmt:
                try:
                    used = int(mgmt.get("total_monthly_storage", 0))
                    limit_bytes = 256 * 1024 * 1024
                    memory_ok = (used / limit_bytes) < 0.9
                except (ValueError, TypeError):
                    pass

            if commands_ok and memory_ok:
                if self._switch_to_other("periodic_check"):
                    logger.info(f"✅ Cache: recovered to '{other}'")
        except Exception as e:
            logger.debug(f"⚠️ Cache: periodic check error: {e}")

    # ------------------------------------------------------------
    # Safe operation
    # ------------------------------------------------------------

    def _safe_operation(self, op_name: str, func, *args, **kwargs) -> Any:
        self._check_periodic_failover()

        if self._should_switch_preemptive():
            logger.warning(
                f"⚠️ Cache: command threshold reached ({self._command_count:,}), "
                f"preemptive failover"
            )
            if not self._switch_to_other("preemptive_threshold"):
                logger.error("❌ Cache: preemptive failover failed")

        db = self._client or self._resolve_client()
        if db is None:
            self._stats["errors"] += 1
            return None

        try:
            result = func(db, *args, **kwargs)
            self._command_count += 1

            if self._active_name == PRIMARY_CACHE_NAME:
                self._stats["primary_uses"] += 1
            else:
                self._stats["backup_uses"] += 1

            return result

        except Exception as e:
            self._stats["errors"] += 1
            self._last_error = str(e)
            self._last_error_at = time.time()

            if self._is_quota_error(e):
                logger.warning(f"⚠️ Cache: quota error on '{self._active_name}': {e}")
                if self._switch_to_other(f"quota_error: {op_name}"):
                    new_db = self._client
                    if new_db is not None:
                        try:
                            result = func(new_db, *args, **kwargs)
                            self._command_count += 1
                            return result
                        except Exception as e2:
                            logger.error(f"❌ Cache: retry failed: {e2}")
                            return None
            else:
                logger.error(f"❌ Cache: {op_name} error: {e}")

            return None

    # ------------------------------------------------------------
    # Basic operations
    # ------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        def _do(db): return db.get(key)
        result = self._safe_operation("get", _do)
        if result is not None:
            self._stats["hits"] += 1
        else:
            self._stats["misses"] += 1
        return result

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        def _do(db): return db.set(key, value, ttl)
        result = self._safe_operation("set", _do)
        if result:
            self._stats["sets"] += 1
        return bool(result)

    def delete(self, key: str) -> bool:
        def _do(db): return db.delete(key)
        result = self._safe_operation("delete", _do)
        if result:
            self._stats["deletes"] += 1
        return bool(result)

    def exists(self, key: str) -> bool:
        def _do(db): return db.exists(key)
        return bool(self._safe_operation("exists", _do))

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        def _do(db): return db.get_many(keys)
        return self._safe_operation("get_many", _do) or {}

    def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        def _do(db): return db.set_many(data, ttl)
        return bool(self._safe_operation("set_many", _do))

    def scan_keys(self, pattern: str = "*", count: int = 100) -> List[str]:
        def _do(db): return db.scan_keys(pattern, count)
        return self._safe_operation("scan_keys", _do) or []

    def ttl(self, key: str) -> int:
        def _do(db): return db.ttl(key)
        result = self._safe_operation("ttl", _do)
        return result if isinstance(result, int) else -2

    def expire(self, key: str, ttl: int) -> bool:
        def _do(db): return db.expire(key, ttl)
        return bool(self._safe_operation("expire", _do))

    def flush(self) -> bool:
        def _do(db): return db.flush()
        logger.warning("⚠️ Cache: FLUSH requested!")
        return bool(self._safe_operation("flush", _do))

    def is_connected(self) -> bool:
        db = self._client or self._resolve_client()
        if db is None:
            return False
        return db.is_connected()

    # ------------------------------------------------------------
    # Type-specific operations
    # ------------------------------------------------------------

    def type(self, key: str) -> str:
        def _do(db):
            result = db._client.type(key)
            return result.decode() if isinstance(result, bytes) else result
        result = self._safe_operation("type", _do)
        return result if result else "none"

    def hgetall(self, key: str) -> Dict[str, Any]:
        def _do(db): return db._client.hgetall(key)
        result = self._safe_operation("hgetall", _do)
        return result or {}

    def hget(self, key: str, field: str) -> Optional[str]:
        def _do(db): return db._client.hget(key, field)
        result = self._safe_operation("hget", _do)
        if isinstance(result, bytes):
            return result.decode()
        return result

    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        def _do(db): return db._client.lrange(key, start, end)
        return self._safe_operation("lrange", _do) or []

    def llen(self, key: str) -> int:
        def _do(db): return db._client.llen(key)
        result = self._safe_operation("llen", _do)
        return result if isinstance(result, int) else 0

    def smembers(self, key: str) -> List[Any]:
        def _do(db): return db._client.smembers(key)
        result = self._safe_operation("smembers", _do)
        return list(result) if result else []

    def scard(self, key: str) -> int:
        def _do(db): return db._client.scard(key)
        result = self._safe_operation("scard", _do)
        return result if isinstance(result, int) else 0

    def zrange(self, key: str, start: int = 0, end: int = -1, withscores: bool = False) -> List[Any]:
        def _do(db): return db._client.zrange(key, start, end, withscores=withscores)
        return self._safe_operation("zrange", _do) or []

    def zcard(self, key: str) -> int:
        def _do(db): return db._client.zcard(key)
        result = self._safe_operation("zcard", _do)
        return result if isinstance(result, int) else 0

    # ------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------

    def force_switch(self, target: str) -> Dict[str, Any]:
        if target == "auto":
            target = self._get_other_name()
        if target not in (PRIMARY_CACHE_NAME, BACKUP_CACHE_NAME):
            return {"success": False, "error": f"Invalid target: {target}"}
        if target == self._active_name:
            return {"success": True, "message": f"Already on '{target}'", "active": self._active_name}

        new_db = registry.get(target, auto_reconnect=True)
        if new_db is None or not new_db.is_connected():
            return {"success": False, "error": f"Target '{target}' not available"}

        old_db = self._client or self._resolve_client()
        self._migrate_sessions(old_db, new_db)

        with self._lock:
            old = self._active_name
            self._active_name = target
            self._client = new_db
            self._failover_count += 1
            self._stats["failovers"] += 1
            self._stats["manual_switches"] += 1
            self._command_count = 0
            self._command_reset_at = time.time()
            self._last_switch_at = time.time()

        logger.warning(f"🔧 Cache: MANUAL switch '{old}' → '{target}'")
        return {"success": True, "from": old, "to": target, "active": self._active_name}

    # ------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        hit_ratio = 0.0
        total = self._stats["hits"] + self._stats["misses"]
        if total > 0:
            hit_ratio = round(self._stats["hits"] / total * 100, 2)

        # آمار active Redis
        active_commands = _get_upstash_commands(self._active_name)
        if active_commands < 0:
            active_commands = self._command_count

        return {
            **self._stats,
            "connected": self.is_connected(),
            "hit_ratio": hit_ratio,
            "active_redis": self._active_name,
            "command_count": active_commands,
            "command_limit": SAFE_COMMAND_LIMIT,
            "command_usage_percent": round(active_commands / SAFE_COMMAND_LIMIT * 100, 2),
            "failover_count": self._failover_count,
            "last_error": self._last_error,
            "last_error_at": (
                datetime.fromtimestamp(self._last_error_at, tz=timezone.utc).isoformat()
                if self._last_error_at else None
            ),
            "last_switch_at": (
                datetime.fromtimestamp(self._last_switch_at, tz=timezone.utc).isoformat()
                if self._last_switch_at else None
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_detailed_stats(self) -> Dict[str, Any]:
        """
        آمار دقیق از هر دو Redis.
        
        ⭐ از Management API استفاده می‌کند → عدد واقعی مثل داشبورد Upstash
        """
        result = {
            "active": self._active_name,
            "failover_count": self._failover_count,
            "last_switch": (
                datetime.fromtimestamp(self._last_switch_at, tz=timezone.utc).isoformat()
                if self._last_switch_at else None
            ),
            "primary": None,
            "backup": None,
        }

        for name, key in [(PRIMARY_CACHE_NAME, "primary"), (BACKUP_CACHE_NAME, "backup")]:
            config = UPSTASH_CONFIG.get(name, {})
            commands_limit = config.get("commands_limit", 500_000)
            memory_limit_mb = config.get("memory_limit_mb", 256)
            bandwidth_limit_gb = config.get("bandwidth_limit_gb", 10)

            info_block = {
                "name": name,
                "endpoint": config.get("endpoint", "?"),
                "registered": False,
                "connected": False,
                "is_active": (name == self._active_name),
                "commands_limit": commands_limit,
                "max_memory_mb": memory_limit_mb,
                "bandwidth_limit_gb": bandwidth_limit_gb,
            }

            # ─── registry check ───
            try:
                db = registry.get(name, auto_reconnect=False)
                if db is not None:
                    info_block["registered"] = True
                    info_block["connected"] = db.is_connected()
            except Exception as e:
                info_block["error"] = str(e)

            # ═══ آمار واقعی از Management API ═══
            mgmt = _fetch_mgmt_stats(name)

            if mgmt and "total_monthly_requests" in mgmt:
                try:
                    commands = int(mgmt.get("total_monthly_requests", 0))
                    used_memory = int(mgmt.get("current_storage", 0) or 0)
                    bandwidth = int(mgmt.get("total_monthly_bandwidth", 0) or 0)

                    info_block.update({
                        "commands_processed": commands,
                        "commands_percent": round(commands / commands_limit * 100, 2),
                        "used_memory_bytes": used_memory,
                        "used_memory_mb": round(used_memory / (1024 * 1024), 2),
                        "used_memory_human": _format_bytes(used_memory),
                        "memory_limit_bytes": memory_limit_mb * 1024 * 1024,
                        "bandwidth_bytes": bandwidth,
                        "bandwidth_gb": round(bandwidth / (1024 ** 3), 3),
                        "bandwidth_human": _format_bytes(bandwidth),
                        "monthly_read_requests": mgmt.get("total_monthly_read_requests", 0),
                        "monthly_write_requests": mgmt.get("total_monthly_write_requests", 0),
                        "monthly_billing_usd": mgmt.get("total_monthly_billing", 0),
                        "daily_net_commands": mgmt.get("daily_net_commands", 0),
                        "daily_bandwidth": mgmt.get("dailybandwidth", 0),
                        "source": "management_api",  # ⭐ منبع معتبر
                    })

                    # تعداد کلید از REST
                    info_block["keys_count"] = _fetch_upstash_dbsize(name)

                except (ValueError, TypeError) as e:
                    info_block["error"] = f"parse error: {e}"

            else:
                # ─── fallback: REST INFO ───
                info_block["source"] = "rest_fallback"

                rest_info = _fetch_upstash_info(name)
                if rest_info:
                    try:
                        commands = int(rest_info.get("total_commands_processed", 0))
                        used_memory = int(rest_info.get("used_memory", 0))

                        info_block.update({
                            "commands_processed": commands,
                            "commands_percent": round(commands / commands_limit * 100, 2),
                            "used_memory_human": rest_info.get("used_memory_human", "0B"),
                            "used_memory_mb": round(used_memory / (1024 * 1024), 2),
                            "used_memory_bytes": used_memory,
                            "memory_limit_bytes": memory_limit_mb * 1024 * 1024,
                            "bandwidth_bytes": 0,
                            "bandwidth_gb": 0,
                            "connected_clients": int(rest_info.get("connected_clients", 0)),
                            "redis_version": rest_info.get("redis_version", "unknown"),
                            "keys_count": _fetch_upstash_dbsize(name),
                        })
                    except (ValueError, TypeError) as e:
                        info_block["error"] = str(e)
                elif db is not None and db.is_connected():
                    try:
                        raw_info = db._client.info()
                        commands = raw_info.get("total_commands_processed", 0)
                        info_block.update({
                            "commands_processed": commands,
                            "commands_percent": round(commands / commands_limit * 100, 2),
                            "used_memory_human": raw_info.get("used_memory_human", "0B"),
                            "used_memory_mb": round(raw_info.get("used_memory", 0) / (1024 * 1024), 2),
                            "keys_count": raw_info.get("db0", {}).get("keys", 0),
                            "connected_clients": raw_info.get("connected_clients", 0),
                            "redis_version": raw_info.get("redis_version", "unknown"),
                        })
                    except Exception as e:
                        info_block["error"] = str(e)

            result[key] = info_block

        return result


# ============================================================
# Helper: format bytes
# ============================================================

def _format_bytes(b: int) -> str:
    if not b:
        return "0B"
    if b >= 1024 ** 3:
        return f"{b / (1024**3):.2f}GB"
    if b >= 1024 ** 2:
        return f"{b / (1024**2):.2f}MB"
    if b >= 1024:
        return f"{b / 1024:.2f}KB"
    return f"{b}B"


# ============================================================
# CacheManager (public interface)
# ============================================================

class CacheManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._redis = DualRedisClient()
            logger.info("✅ CacheManager v3.4 initialized (Management API stats)")

    # ─── Basic ───
    def get(self, key: str) -> Optional[Any]:
        try:
            return self._redis.get(key)
        except Exception as e:
            logger.error(f"❌ Cache get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        try:
            return self._redis.set(key, value, ttl)
        except Exception as e:
            logger.error(f"❌ Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        try:
            return self._redis.delete(key)
        except Exception as e:
            logger.error(f"❌ Cache delete error: {e}")
            return False

    def clear(self) -> bool:
        try:
            result = self._redis.flush()
            if result:
                logger.info("✅ Cache cleared")
            return result
        except Exception as e:
            logger.error(f"❌ Cache clear error: {e}")
            return False

    def is_connected(self) -> bool:
        try:
            return self._redis.is_connected()
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        try:
            return self._redis.exists(key)
        except Exception:
            return False

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        try:
            return self._redis.get_many(keys)
        except Exception:
            return {}

    def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        try:
            return self._redis.set_many(data, ttl)
        except Exception:
            return False

    def scan_keys(self, pattern: str = "*", count: int = 100) -> List[str]:
        try:
            return self._redis.scan_keys(pattern, count)
        except Exception:
            return []

    def ttl(self, key: str) -> int:
        try:
            return self._redis.ttl(key)
        except Exception:
            return -2

    def expire(self, key: str, ttl: int) -> bool:
        try:
            return self._redis.expire(key, ttl)
        except Exception:
            return False

    # ─── Type-specific ───
    def type(self, key: str) -> str:
        try:
            return self._redis.type(key)
        except Exception:
            return "none"

    def hgetall(self, key: str) -> Dict[str, Any]:
        try:
            return self._redis.hgetall(key)
        except Exception:
            return {}

    def hget(self, key: str, field: str) -> Optional[str]:
        try:
            return self._redis.hget(key, field)
        except Exception:
            return None

    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        try:
            return self._redis.lrange(key, start, end)
        except Exception:
            return []

    def llen(self, key: str) -> int:
        try:
            return self._redis.llen(key)
        except Exception:
            return 0

    def smembers(self, key: str) -> List[Any]:
        try:
            return self._redis.smembers(key)
        except Exception:
            return []

    def scard(self, key: str) -> int:
        try:
            return self._redis.scard(key)
        except Exception:
            return 0

    def zrange(self, key: str, start: int = 0, end: int = -1, withscores: bool = False) -> List[Any]:
        try:
            return self._redis.zrange(key, start, end, withscores=withscores)
        except Exception:
            return []

    def zcard(self, key: str) -> int:
        try:
            return self._redis.zcard(key)
        except Exception:
            return 0

    # ─── Stats ───
    def get_stats(self) -> Dict[str, Any]:
        try:
            return self._redis.get_stats()
        except Exception as e:
            logger.error(f"❌ Cache stats error: {e}")
            return {
                "hits": 0, "misses": 0, "sets": 0, "deletes": 0,
                "errors": 1, "connected": False, "hit_ratio": 0.0,
            }

    def get_detailed_stats(self) -> Dict[str, Any]:
        try:
            return self._redis.get_detailed_stats()
        except Exception as e:
            logger.error(f"❌ Cache detailed stats error: {e}")
            return {"error": str(e)}

    def force_switch(self, target: str) -> Dict[str, Any]:
        try:
            return self._redis.force_switch(target)
        except Exception as e:
            logger.error(f"❌ Cache force switch error: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# Singleton
# ============================================================

cache_manager: CacheManager = CacheManager()
