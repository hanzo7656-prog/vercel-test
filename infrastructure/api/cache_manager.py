# infrastructure/api/cache_manager.py
# ============================================================
# مدیریت کش با دو Redis - نسخه ۳.۰
# Dual Redis + Auto-Failover + Startup Check + Command Tracking
# ============================================================

import json
import logging
import threading
import time
from typing import Any, Optional, Dict, List
from datetime import datetime, timezone

from infrastructure.database.registry import registry

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

SAFE_COMMAND_LIMIT = 480_000
FAILOVER_CHECK_INTERVAL = 300  # ۵ دقیقه
PRIMARY_CACHE_NAME = "cache"
BACKUP_CACHE_NAME = "cache_backup"


# ============================================================
# DualRedisClient
# ============================================================

class DualRedisClient:
    """
    Wrapper روی دو RedisManager که سوئیچ خودکار انجام می‌دهد.
    """

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
        }

        # ⚡ Startup check
        self._startup_check()

        logger.info("✅ DualRedisClient initialized")

    # ------------------------------------------------------------
    # Startup check
    # ------------------------------------------------------------

    def _startup_check(self) -> None:
        """چک کردن Redis اولیه در startup"""
        try:
            db = registry.get(PRIMARY_CACHE_NAME, auto_reconnect=False)
            if db is None:
                logger.warning(
                    f"⚠️ Cache: '{PRIMARY_CACHE_NAME}' not in registry, "
                    f"using '{BACKUP_CACHE_NAME}'"
                )
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

            try:
                info = db._client.info()
                remote_commands = info.get("total_commands_processed", 0)

                if remote_commands >= SAFE_COMMAND_LIMIT:
                    logger.warning(
                        f"⚠️ Cache: primary full "
                        f"({remote_commands} commands), "
                        f"switching to '{BACKUP_CACHE_NAME}' at startup"
                    )

                    other = registry.get(BACKUP_CACHE_NAME, auto_reconnect=False)
                    if other is not None and other.is_connected():
                        self._active_name = BACKUP_CACHE_NAME
                        self._client = other
                        self._failover_count += 1
                        self._stats["failovers"] += 1
                    else:
                        logger.error("❌ Cache: backup not available either")
                else:
                    self._command_count = remote_commands
                    percent = round(remote_commands / SAFE_COMMAND_LIMIT * 100, 1)
                    logger.info(
                        f"✅ Cache: primary OK at startup "
                        f"({remote_commands} commands, {percent}% used)"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Cache: startup INFO failed: {e}")

        except Exception as e:
            logger.error(f"❌ Cache: startup check error: {e}")

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
                    logger.warning(
                        f"⚠️ Cache: switched to '{other}' "
                        f"(original not available)"
                    )
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
        """تشخیص خطاهای محدودیت (Command / Storage / Bandwidth)"""
        msg = str(err).lower()
        keywords = [
            # Command Limit
            "max requests",
            "command limit",
            "quota",
            "limit exceeded",
            "too many requests",
            "rate limit",
            # Storage (OOM)
            "oom command",
            "maxmemory",
            "out of memory",
            "used memory",
            # Bandwidth
            "bandwidth",
            "traffic exceeded",
        ]
        return any(k in msg for k in keywords)

    def _switch_to_other(self, reason: str) -> bool:
        other = self._get_other_name()

        try:
            db = registry.get(other, auto_reconnect=True)
            if db is None or not db.is_connected():
                logger.error(
                    f"❌ Cache: cannot switch to '{other}' — not connected"
                )
                return False

            with self._lock:
                old = self._active_name
                self._active_name = other
                self._client = db
                self._failover_count += 1
                self._stats["failovers"] += 1
                self._command_count = 0
                self._command_reset_at = time.time()

            logger.warning(
                f"⚠️ Cache: failover '{old}' → '{other}' "
                f"(reason: {reason})"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Cache: failover error: {e}")
            return False

    def _check_periodic_failover(self) -> None:
        # فقط اگر قبلاً سوئیچ کرده‌ایم (یعنی یکی پر شده)
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

            try:
                info = db._client.info()
                remote_commands = info.get("total_commands_processed", 0)
                used_memory = info.get("used_memory", 0)
                max_memory = info.get("maxmemory", 0)

                commands_ok = remote_commands < SAFE_COMMAND_LIMIT

                memory_ok = True
                if max_memory > 0:
                    memory_usage = used_memory / max_memory
                    memory_ok = memory_usage < 0.9

                if commands_ok and memory_ok:
                    if self._switch_to_other("periodic_check"):
                        logger.info(
                            f"✅ Cache: recovered to '{other}' "
                            f"(commands: {remote_commands})"
                        )
            except Exception as e:
                logger.debug(f"⚠️ Cache: periodic INFO error: {e}")

        except Exception as e:
            logger.debug(f"⚠️ Cache: periodic check error: {e}")

    # ------------------------------------------------------------
    # Safe operation
    # ------------------------------------------------------------

    def _safe_operation(self, op_name: str, func, *args, **kwargs) -> Any:
        self._check_periodic_failover()

        if self._should_switch_preemptive():
            logger.warning(
                f"⚠️ Cache: command threshold reached "
                f"({self._command_count}), preemptive failover"
            )
            if not self._switch_to_other("preemptive_threshold"):
                logger.error(
                    "❌ Cache: preemptive failover failed, "
                    "continuing with current"
                )

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
                logger.warning(
                    f"⚠️ Cache: quota error on '{self._active_name}': {e}"
                )
                if self._switch_to_other(f"quota_error: {op_name}"):
                    new_db = self._client
                    if new_db is not None:
                        try:
                            result = func(new_db, *args, **kwargs)
                            self._command_count += 1
                            return result
                        except Exception as e2:
                            logger.error(
                                f"❌ Cache: retry on new Redis failed: {e2}"
                            )
                            return None
            else:
                logger.error(f"❌ Cache: {op_name} error: {e}")

            return None

    # ------------------------------------------------------------
    # Operations
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
    # Manual control
    # ------------------------------------------------------------

    def force_switch(self, target: str) -> Dict[str, Any]:
        """
        سوئیچ دستی بین دو Redis
        
        Args:
            target: 'cache' یا 'cache_backup' یا 'auto' (سوئیچ به دیگری)
        """
        if target == "auto":
            target = self._get_other_name()

        if target not in (PRIMARY_CACHE_NAME, BACKUP_CACHE_NAME):
            return {
                "success": False,
                "error": f"Invalid target: {target}",
            }

        if target == self._active_name:
            return {
                "success": True,
                "message": f"Already on '{target}'",
                "active": self._active_name,
            }

        db = registry.get(target, auto_reconnect=True)
        if db is None or not db.is_connected():
            return {
                "success": False,
                "error": f"Target '{target}' not available",
            }

        with self._lock:
            old = self._active_name
            self._active_name = target
            self._client = db
            self._failover_count += 1
            self._stats["failovers"] += 1
            self._stats["manual_switches"] += 1
            self._command_count = 0
            self._command_reset_at = time.time()

        logger.warning(
            f"🔧 Cache: MANUAL switch '{old}' → '{target}'"
        )

        return {
            "success": True,
            "from": old,
            "to": target,
            "active": self._active_name,
        }

    # ------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        hit_ratio = 0.0
        total = self._stats["hits"] + self._stats["misses"]
        if total > 0:
            hit_ratio = round(self._stats["hits"] / total * 100, 2)

        now_iso = datetime.now(timezone.utc).isoformat()

        return {
            **self._stats,
            "connected": self.is_connected(),
            "hit_ratio": hit_ratio,
            "active_redis": self._active_name,
            "command_count": self._command_count,
            "command_limit": SAFE_COMMAND_LIMIT,
            "command_usage_percent": round(
                self._command_count / SAFE_COMMAND_LIMIT * 100, 2
            ),
            "failover_count": self._failover_count,
            "last_error": self._last_error,
            "last_error_at": (
                datetime.fromtimestamp(
                    self._last_error_at, tz=timezone.utc
                ).isoformat()
                if self._last_error_at else None
            ),
            "timestamp": now_iso,
        }

    def get_detailed_stats(self) -> Dict[str, Any]:
        """آمار دقیق از هر دو Redis"""
        result = {
            "active": self._active_name,
            "failover_count": self._failover_count,
            "primary": None,
            "backup": None,
        }

        for name in (PRIMARY_CACHE_NAME, BACKUP_CACHE_NAME):
            try:
                db = registry.get(name, auto_reconnect=False)
                if db is None:
                    result[name if name == PRIMARY_CACHE_NAME else "backup"] = {
                        "name": name,
                        "registered": False,
                    }
                    continue

                info_block = {
                    "name": name,
                    "registered": True,
                    "connected": db.is_connected(),
                }

                if db.is_connected():
                    try:
                        info = db._client.info()
                        remote_commands = info.get("total_commands_processed", 0)
                        used_memory = info.get("used_memory", 0)
                        max_memory = info.get("maxmemory", 0)

                        info_block.update({
                            "used_memory_human": info.get("used_memory_human", "0"),
                            "used_memory_mb": round(used_memory / (1024 * 1024), 2),
                            "max_memory_mb": round(max_memory / (1024 * 1024), 2) if max_memory else 0,
                            "commands_processed": remote_commands,
                            "commands_percent": round(
                                remote_commands / SAFE_COMMAND_LIMIT * 100, 2
                            ),
                            "keys_count": info.get("db0", {}).get("keys", 0),
                            "connected_clients": info.get("connected_clients", 0),
                            "uptime_seconds": info.get("uptime_in_seconds", 0),
                            "redis_version": info.get("redis_version", "unknown"),
                        })
                    except Exception as e:
                        info_block["error"] = str(e)

                key = "primary" if name == PRIMARY_CACHE_NAME else "backup"
                result[key] = info_block

            except Exception as e:
                key = "primary" if name == PRIMARY_CACHE_NAME else "backup"
                result[key] = {
                    "name": name,
                    "error": str(e),
                }

        return result


# ============================================================
# CacheManager (public interface — همان قبلی)
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
            logger.info("✅ CacheManager v3.0 initialized (Dual Redis)")

    # ------------------------------------------------------------
    # ۵ متد قبلی (بدون تغییر)
    # ------------------------------------------------------------

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

    def get_stats(self) -> Dict[str, Any]:
        try:
            return self._redis.get_stats()
        except Exception as e:
            logger.error(f"❌ Cache stats error: {e}")
            return {
                "hits": 0, "misses": 0, "sets": 0, "deletes": 0,
                "errors": 1, "connected": False, "hit_ratio": 0.0,
            }

    # ------------------------------------------------------------
    # متدهای جدید (اختیاری)
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # ادمین
    # ------------------------------------------------------------

    def get_detailed_stats(self) -> Dict[str, Any]:
        """آمار دقیق از هر دو Redis"""
        try:
            return self._redis.get_detailed_stats()
        except Exception as e:
            logger.error(f"❌ Cache detailed stats error: {e}")
            return {"error": str(e)}

    def force_switch(self, target: str) -> Dict[str, Any]:
        """سوئیچ دستی بین Redis ها"""
        try:
            return self._redis.force_switch(target)
        except Exception as e:
            logger.error(f"❌ Cache force switch error: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# Singleton
# ============================================================

cache_manager: CacheManager = CacheManager()
