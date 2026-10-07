# infrastructure/database/base.py
# ============================================================
# کلاس پایه برای همه دیتابیس‌ها - نسخه ۳.۱
# UTC-safe + helpers مشترک
# ============================================================

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Optional, Dict, List, Generator, Callable, TypeVar
from datetime import datetime, timezone
from functools import wraps
import logging
import time

logger = logging.getLogger(__name__)

# ============================================================
# Type Variables
# ============================================================

T = TypeVar('T')


# ============================================================
# Timezone Helpers (مشترک بین همه دیتابیس‌ها)
# ============================================================

def utc_now() -> datetime:
    """
    زمان فعلی UTC به شکل naive.

    چرا naive؟ چون schema فعلی از TIMESTAMP WITHOUT TIME ZONE
    استفاده می‌کند. تمام timestampهای سیستم UTC هستند ولی
    tzinfo ندارند.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    """زمان فعلی UTC با tzinfo (برای جاهایی که لازم است)."""
    return datetime.now(timezone.utc)


def to_utc_naive(dt: Any) -> Optional[datetime]:
    """
    تبدیل هر ورودی تاریخ به UTC naive.

    ورودی‌های ممکن:
        - datetime با tzinfo → تبدیل به UTC، tz حذف
        - datetime naive → فرض UTC
        - pandas Timestamp → to_pydatetime
        - str → تلاش با fromisoformat
    """
    if dt is None:
        return None

    try:
        if hasattr(dt, "to_pydatetime"):
            dt = dt.to_pydatetime()

        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                return None

        if not isinstance(dt, datetime):
            return None

        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)

        return dt

    except Exception:
        return None


def format_uptime(seconds: int) -> str:
    """فرمت کردن آپتایم."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


# ============================================================
# Retry Decorator
# ============================================================

def retry_on_error(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """Decorator برای retry خودکار با exponential backoff"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"⚠️ Attempt {attempt}/{max_attempts} failed for "
                            f"{func.__name__}: {e}. Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"❌ All {max_attempts} attempts failed for {func.__name__}: {e}"
                        )

            if last_exception:
                raise last_exception
            return None  # type: ignore

        return wrapper
    return decorator


# ============================================================
# DatabaseBase
# ============================================================

class DatabaseBase(ABC):
    """
    کلاس پایه برای همه اتصالات دیتابیس

    ارتقاهای نسخه ۳.۱:
        - تمام timestampها UTC naive
        - helpers مشترک در ماژول (utc_now, to_utc_naive, format_uptime)
        - حذف _format_uptime تکراری از زیرکلاس‌ها
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        self.name: str = name
        self.config: Dict[str, Any] = config
        self._connected: bool = False
        self._client: Any = None

        # 🆕 UTC
        self._created_at: datetime = utc_now()
        self._last_ping: Optional[datetime] = None

        self._ping_count: int = 0
        self._error_count: int = 0
        self._query_count: int = 0
        self._write_count: int = 0
        self._read_count: int = 0

        # Quota state
        self._quota_exceeded: bool = False
        self._quota_warning: bool = False
        self._quota_check_count: int = 0

    # ============================================================
    # متدهای انتزاعی
    # ============================================================

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    def flush(self) -> bool:
        pass

    # ============================================================
    # متدهای کمکی
    # ============================================================

    def execute(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            f"execute() not implemented for {self.__class__.__name__}"
        )

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get_client(self) -> Any:
        return self._client

    def ping(self) -> bool:
        """بررسی سلامت اتصال"""
        try:
            if self._client is None:
                return False

            if hasattr(self._client, 'ping'):
                result = self._client.ping()
                if result:
                    self._last_ping = utc_now()  # 🆕 UTC
                    self._ping_count += 1
                    return True
                return False

            return self.is_connected()

        except Exception as e:
            logger.debug(f"⚠️ Ping failed for {self.name}: {e}")
            self._error_count += 1
            return False

    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        now = utc_now()  # 🆕 UTC
        uptime_seconds = int((now - self._created_at).total_seconds())

        quota_info = self._get_quota_summary()

        return {
            "name": self.name,
            "type": self.config.get("type", "unknown"),
            "connected": self.is_connected(),
            "ping": self.ping(),
            "enabled": self.config.get("enabled", True),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": format_uptime(uptime_seconds),  # 🆕 helper
            "last_ping": self._last_ping.isoformat() if self._last_ping else None,
            "stats": {
                "ping_count": self._ping_count,
                "query_count": self._query_count,
                "read_count": self._read_count,
                "write_count": self._write_count,
                "error_count": self._error_count,
            },
            "quota": quota_info,
            "config_summary": {
                "host": self.config.get("connection", {}).get("host") or self.config.get("host"),
                "port": self.config.get("connection", {}).get("port") or self.config.get("port"),
                "database": self.config.get("connection", {}).get("database") or self.config.get("database"),
            },
            "timestamp": now.isoformat() + "Z",  # 🆕 علامت UTC
        }

    def _get_quota_summary(self) -> Dict[str, Any]:
        """خلاصه Quota (قابل override)"""
        quota_config = self.config.get("quota", {})
        return {
            "total_mb": quota_config.get("total_mb", 0),
            "reserved_mb": quota_config.get("reserved_mb", 0),
            "usable_mb": quota_config.get("usable_mb", 0),
            "used_mb": None,
            "used_percent": None,
            "status": "unknown",
            "exceeded": False,
            "warning": False,
        }

    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        uptime_seconds = int((utc_now() - self._created_at).total_seconds())  # 🆕 UTC
        quota_info = self._get_quota_summary()

        return {
            "name": self.name,
            "type": self.config.get("type", "unknown"),
            "connected": self.is_connected(),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": format_uptime(uptime_seconds),  # 🆕 helper
            "query_count": self._query_count,
            "read_count": self._read_count,
            "write_count": self._write_count,
            "error_count": self._error_count,
            "quota": quota_info,
        }

    # ============================================================
    # Quota Hooks
    # ============================================================

    def check_quota(self) -> Dict[str, Any]:
        self._quota_check_count += 1
        return self._get_quota_summary()

    def can_write(self, estimated_size_mb: float = 0) -> bool:
        quota = self.check_quota()
        if quota.get("exceeded", False):
            return False

        used = quota.get("used_mb", 0) or 0
        usable = quota.get("usable_mb", 0)
        if usable > 0 and (used + estimated_size_mb) > usable:
            return False

        return True

    def get_quota_config(self) -> Dict[str, Any]:
        return self.config.get("quota", {}).copy()

    def update_quota_config(self, new_config: Dict[str, Any]) -> bool:
        try:
            if "quota" not in self.config:
                self.config["quota"] = {}

            self.config["quota"].update(new_config)
            logger.info(f"✅ Quota updated for '{self.name}': {new_config}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update quota for '{self.name}': {e}")
            return False

    # ============================================================
    # Context Manager
    # ============================================================

    def __enter__(self) -> 'DatabaseBase':
        if not self.is_connected():
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            logger.error(f"❌ Error in {self.name} context: {exc_val}")
            try:
                self._rollback()
            except Exception:
                pass

    def _rollback(self) -> None:
        if self._client and hasattr(self._client, 'rollback'):
            try:
                self._client.rollback()
            except Exception:
                pass

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        try:
            yield
            self._commit()
        except Exception as e:
            logger.error(f"❌ Transaction failed for {self.name}: {e}")
            self._rollback()
            raise

    def _commit(self) -> None:
        if self._client and hasattr(self._client, 'commit'):
            try:
                self._client.commit()
            except Exception:
                pass

    # ============================================================
    # Bulk
    # ============================================================

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        raise NotImplementedError(
            f"execute_many() not implemented for {self.__class__.__name__}"
        )

    # ============================================================
    # String Representation
    # ============================================================

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.name!r} "
            f"connected={self.is_connected()} "
            f"type={self.config.get('type', 'unknown')!r}>"
        )
