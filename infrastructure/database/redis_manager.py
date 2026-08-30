# infrastructure/database/redis_manager.py
# ============================================================
# مدیریت Redis - نسخه ۲.۰ (آپدیت شده با Fix typing)
# ============================================================

import redis
import json
import logging
from typing import Any, Optional, Dict, List  # ✅ اضافه کردن List
from infrastructure.database.base import DatabaseBase

logger = logging.getLogger(__name__)


class RedisManager(DatabaseBase):
    """
    مدیریت Redis
    
    ویژگی‌ها:
        - اتصال با SSL
        - پشتیبانی از JSON
        - آمار و سلامت
        - TTL خودکار
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._client = None
    
    def connect(self) -> bool:
        """برقراری اتصال به Redis"""
        try:
            self._client = redis.Redis(
                host=self.config.get("host"),
                port=self.config.get("port", 6379),
                password=self.config.get("password"),
                ssl=self.config.get("ssl", True),
                db=self.config.get("database", 0),
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # تست اتصال
            self._client.ping()
            self._connected = True
            logger.info(f"✅ Redis ({self.name}) متصل شد - Host: {self.config.get('host')}")
            return True
        except redis.exceptions.ConnectionError as e:
            logger.error(f"❌ خطا در اتصال Redis ({self.name}): ConnectionError - {e}")
            self._connected = False
            return False
        except redis.exceptions.TimeoutError as e:
            logger.error(f"❌ خطا در اتصال Redis ({self.name}): TimeoutError - {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"❌ خطا در اتصال Redis ({self.name}): {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> bool:
        """قطع اتصال از Redis"""
        try:
            if self._client:
                self._client.close()
            self._connected = False
            logger.info(f"✅ Redis ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع Redis ({self.name}): {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        دریافت مقدار از Redis
        
        پارامترها:
            key: کلید
        
        خروجی:
            مقدار (JSON خودکار parse می‌شود)
        """
        if not self.is_connected():
            logger.warning(f"⚠️ Redis ({self.name}) متصل نیست، تلاش مجدد...")
            if not self.connect():
                return None
        
        try:
            value = self._client.get(key)
            if value:
                try:
                    # تلاش برای parse JSON
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # اگر JSON نبود، همان رشته را برگردان
                    return value
            return None
        except redis.exceptions.TimeoutError as e:
            logger.error(f"❌ Redis timeout در get {key}: {e}")
            return None
        except redis.exceptions.ConnectionError as e:
            logger.error(f"❌ Redis connection error در get {key}: {e}")
            self._connected = False
            return None
        except Exception as e:
            logger.error(f"❌ خطا در get {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        ذخیره مقدار در Redis
        
        پارامترها:
            key: کلید
            value: مقدار
            ttl: زمان انقضا (ثانیه)
        
        خروجی:
            موفقیت عملیات
        """
        if not self.is_connected():
            logger.warning(f"⚠️ Redis ({self.name}) متصل نیست، تلاش مجدد...")
            if not self.connect():
                return False
        
        try:
            # تبدیل به JSON اگر dict یا list باشد
            if not isinstance(value, (str, int, float, bool)):
                value = json.dumps(value, ensure_ascii=False)
            
            if ttl:
                self._client.setex(key, ttl, value)
            else:
                self._client.set(key, value)
            return True
        except redis.exceptions.TimeoutError as e:
            logger.error(f"❌ Redis timeout در set {key}: {e}")
            return False
        except redis.exceptions.ConnectionError as e:
            logger.error(f"❌ Redis connection error در set {key}: {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"❌ خطا در set {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """حذف مقدار از Redis"""
        if not self.is_connected():
            return False
        
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"❌ خطا در delete {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید در Redis"""
        if not self.is_connected():
            return False
        
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.error(f"❌ خطا در exists {key}: {e}")
            return False
    
    def flush(self) -> bool:
        """پاک کردن همه داده‌های Redis (احتیاط!)"""
        if not self.is_connected():
            return False
        
        try:
            self._client.flushdb()
            logger.warning(f"⚠️ Redis ({self.name}) پاک شد!")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در flush: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار Redis
        
        خروجی:
            دیکشنری شامل:
                - version: نسخه Redis
                - keys: تعداد کلیدها
                - memory: مقدار حافظه مصرفی
                - clients: تعداد کلاینت‌ها
                - uptime: زمان آپتایم
        """
        try:
            if not self.is_connected():
                return {"version": "unknown", "connected": False}
            
            info = self._client.info()
            return {
                "version": info.get("redis_version", "unknown"),
                "keys": info.get("db0", {}).get("keys", 0),
                "memory": info.get("used_memory_human", "0"),
                "clients": info.get("connected_clients", 0),
                "uptime": info.get("uptime_in_seconds", 0),
                "connected": True
            }
        except redis.exceptions.TimeoutError:
            logger.warning(f"⚠️ Redis stats timeout for {self.name}")
            return {"version": "unknown", "connected": False, "error": "timeout"}
        except Exception as e:
            logger.warning(f"⚠️ Redis stats error for {self.name}: {e}")
            return {"version": "unknown", "connected": False, "error": str(e)}
    
    def ping(self) -> bool:
        """بررسی سلامت اتصال Redis"""
        try:
            if not self._client:
                return False
            return self._client.ping()
        except redis.exceptions.TimeoutError:
            return False
        except redis.exceptions.ConnectionError:
            return False
        except Exception:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل Redis"""
        base = super().health_check()
        
        try:
            if self._client and self._connected:
                info = self._client.info()
                base["version"] = info.get("redis_version", "unknown")
                base["used_memory"] = info.get("used_memory_human", "unknown")
                base["keys"] = info.get("db0", {}).get("keys", 0)
                base["connected_clients"] = info.get("connected_clients", 0)
            else:
                base["version"] = "disconnected"
                base["error"] = "Not connected"
        except redis.exceptions.TimeoutError:
            base["version"] = "timeout"
            base["error"] = "Connection timeout"
        except redis.exceptions.ConnectionError:
            base["version"] = "connection_error"
            base["error"] = "Connection refused"
        except Exception as e:
            base["version"] = "error"
            base["error"] = str(e)
        
        return base
    
    def keys(self, pattern: str = "*") -> List[str]:
        """
        دریافت لیست کلیدها با الگو
        
        پارامترها:
            pattern: الگوی جستجو (پیش‌فرض: *)
        
        خروجی:
            لیست کلیدها
        """
        if not self.is_connected():
            return []
        
        try:
            return self._client.keys(pattern)
        except Exception as e:
            logger.error(f"❌ خطا در keys {pattern}: {e}")
            return []
    
    def ttl(self, key: str) -> int:
        """
        دریافت زمان باقیمانده انقضا
        
        پارامترها:
            key: کلید
        
        خروجی:
            زمان باقیمانده (ثانیه) یا -1 برای بدون انقضا
        """
        if not self.is_connected():
            return -2
        
        try:
            return self._client.ttl(key)
        except Exception as e:
            logger.error(f"❌ خطا در ttl {key}: {e}")
            return -2
    
    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        افزایش مقدار عددی
        
        پارامترها:
            key: کلید
            amount: مقدار افزایش (پیش‌فرض: 1)
        
        خروجی:
            مقدار جدید
        """
        if not self.is_connected():
            return None
        
        try:
            return self._client.incrby(key, amount)
        except Exception as e:
            logger.error(f"❌ خطا در incr {key}: {e}")
            return None
    
    def expire(self, key: str, ttl: int) -> bool:
        """
        تنظیم زمان انقضا برای کلید
        
        پارامترها:
            key: کلید
            ttl: زمان انقضا (ثانیه)
        
        خروجی:
            موفقیت عملیات
        """
        if not self.is_connected():
            return False
        
        try:
            return self._client.expire(key, ttl)
        except Exception as e:
            logger.error(f"❌ خطا در expire {key}: {e}")
            return False
