# infrastructure/database/base.py
# ============================================================
# کلاس پایه برای همه دیتابیس‌ها - نسخه ۳.۰
# رفع باگ + بهبود + ارتقا
# ============================================================

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Optional, Dict, List, Generator, Callable, TypeVar
from datetime import datetime
from functools import wraps
import logging
import time

logger = logging.getLogger(__name__)

# ============================================================
# Type Variables
# ============================================================

T = TypeVar('T')


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
    """
    Decorator برای retry خودکار با exponential backoff
    
    پارامترها:
        max_attempts: حداکثر تلاش
        base_delay: تأخیر اولیه (ثانیه)
        max_delay: حداکثر تأخیر
        backoff_factor: ضریب افزایش
        exceptions: استثناهایی که باید retry شوند
    
    استفاده:
        @retry_on_error(max_attempts=3)
        def my_function():
            ...
    """
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
# DatabaseBase - کلاس پایه انتزاعی
# ============================================================

class DatabaseBase(ABC):
    """
    کلاس پایه برای همه اتصالات دیتابیس
    
    ویژگی‌ها:
        - Interface یکسان برای همه دیتابیس‌ها
        - Context Manager support
        - Transaction support
        - Health check پیشرفته
        - Retry خودکار
        - Quota check integration
    
    ارتقاهای نسخه ۳.۰:
        - Context Manager (with statement)
        - Transaction context manager
        - Health check تفصیلی
        - Type hints کامل
        - Retry decorator
        - Quota integration hooks
    """
    
    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        """
        راه‌اندازی
        
        پارامترها:
            name: نام دیتابیس (primary, backup, ...)
            config: تنظیمات دیتابیس
        """
        self.name: str = name
        self.config: Dict[str, Any] = config
        self._connected: bool = False
        self._client: Any = None
        self._created_at: datetime = datetime.now()
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
        """برقراری اتصال به دیتابیس"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """قطع اتصال از دیتابیس"""
        pass
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از دیتابیس"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار در دیتابیس"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """حذف مقدار از دیتابیس"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید"""
        pass
    
    @abstractmethod
    def flush(self) -> bool:
        """پاک کردن همه داده‌ها"""
        pass
    
    # ============================================================
    # متدهای کمکی
    # ============================================================
    
    def execute(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """اجرای کوئری (پیش‌فرض: پیاده‌سازی نشده)"""
        raise NotImplementedError(
            f"execute() not implemented for {self.__class__.__name__}"
        )
    
    def is_connected(self) -> bool:
        """بررسی وضعیت اتصال"""
        return self._connected and self._client is not None
    
    def get_client(self) -> Any:
        """دریافت کلاینت اصلی"""
        return self._client
    
    def ping(self) -> bool:
        """
        بررسی سلامت اتصال
        
        رفع باگ:
            - Type hints کامل
            - Error handling بهتر
            - ثبت آمار ping
        """
        try:
            if self._client is None:
                return False
            
            if hasattr(self._client, 'ping'):
                result = self._client.ping()
                if result:
                    self._last_ping = datetime.now()
                    self._ping_count += 1
                    return True
                return False
            
            return self.is_connected()
            
        except Exception as e:
            logger.debug(f"⚠️ Ping failed for {self.name}: {e}")
            self._error_count += 1
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """
        بررسی سلامت کامل
        
        خروجی:
            دیکشنری شامل name, type, connected, ping, enabled, uptime, stats, quota
        """
        now = datetime.now()
        uptime_seconds = int((now - self._created_at).total_seconds())
        
        # محاسبه quota status
        quota_info = self._get_quota_summary()
        
        return {
            "name": self.name,
            "type": self.config.get("type", "unknown"),
            "connected": self.is_connected(),
            "ping": self.ping(),
            "enabled": self.config.get("enabled", True),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": self._format_uptime(uptime_seconds),
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
            "timestamp": now.isoformat()
        }
    
    def _get_quota_summary(self) -> Dict[str, Any]:
        """
        خلاصه Quota (قابل override)
        
        خروجی:
            دیکشنری quota
        """
        quota_config = self.config.get("quota", {})
        return {
            "total_mb": quota_config.get("total_mb", 0),
            "reserved_mb": quota_config.get("reserved_mb", 0),
            "usable_mb": quota_config.get("usable_mb", 0),
            "used_mb": None,  # override در زیرکلاس
            "used_percent": None,
            "status": "unknown",
            "exceeded": False,
            "warning": False,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار
        
        ارتقا:
            - Quota info
            - Read/Write count
            - Uptime
        """
        uptime_seconds = int((datetime.now() - self._created_at).total_seconds())
        quota_info = self._get_quota_summary()
        
        return {
            "name": self.name,
            "type": self.config.get("type", "unknown"),
            "connected": self.is_connected(),
            "uptime_seconds": uptime_seconds,
            "uptime_formatted": self._format_uptime(uptime_seconds),
            "query_count": self._query_count,
            "read_count": self._read_count,
            "write_count": self._write_count,
            "error_count": self._error_count,
            "quota": quota_info,
        }
    
    def _format_uptime(self, seconds: int) -> str:
        """فرمت کردن آپتایم"""
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
    # Quota Hooks (قابل override)
    # ============================================================
    
    def check_quota(self) -> Dict[str, Any]:
        """
        بررسی Quota (قابل override)
        
        خروجی:
            دیکشنری وضعیت Quota
        """
        self._quota_check_count += 1
        return self._get_quota_summary()
    
    def can_write(self, estimated_size_mb: float = 0) -> bool:
        """
        بررسی امکان نوشتن (قابل override)
        
        پارامترها:
            estimated_size_mb: حجم تخمینی
        
        خروجی:
            True اگر قابل نوشتن باشد
        """
        quota = self.check_quota()
        if quota.get("exceeded", False):
            return False
        
        # چک اضافی: اگر نوشتن باعث exceeded شود
        used = quota.get("used_mb", 0) or 0
        usable = quota.get("usable_mb", 0)
        if usable > 0 and (used + estimated_size_mb) > usable:
            return False
        
        return True
    
    def get_quota_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات Quota"""
        return self.config.get("quota", {}).copy()
    
    def update_quota_config(self, new_config: Dict[str, Any]) -> bool:
        """
        بروزرسانی تنظیمات Quota (از فرانت‌اند)
        
        پارامترها:
            new_config: تنظیمات جدید
        
        خروجی:
            True اگر موفق
        """
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
        """ورود به context manager"""
        if not self.is_connected():
            self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """خروج از context manager"""
        if exc_type is not None:
            logger.error(f"❌ Error in {self.name} context: {exc_val}")
            try:
                self._rollback()
            except Exception:
                pass
    
    def _rollback(self) -> None:
        """Rollback (قابل override)"""
        if self._client and hasattr(self._client, 'rollback'):
            try:
                self._client.rollback()
            except Exception:
                pass
    
    # ============================================================
    # Transaction Context Manager
    # ============================================================
    
    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """
        Context manager برای transaction
        
        استفاده:
            with db.transaction():
                db.execute("INSERT ...")
                db.execute("UPDATE ...")
        """
        try:
            yield
            self._commit()
        except Exception as e:
            logger.error(f"❌ Transaction failed for {self.name}: {e}")
            self._rollback()
            raise
    
    def _commit(self) -> None:
        """Commit (قابل override)"""
        if self._client and hasattr(self._client, 'commit'):
            try:
                self._client.commit()
            except Exception:
                pass
    
    # ============================================================
    # Bulk Operations (قابل override)
    # ============================================================
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """اجرای کوئری با چند پارامتر"""
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
