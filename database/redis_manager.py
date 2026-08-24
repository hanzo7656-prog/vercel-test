# database/redis_manager.py
# ============================================================
# مدیریت Redis جدید
# ============================================================

import redis
import json
import logging
from typing import Any, Optional, Dict
from database.base import DatabaseBase

logger = logging.getLogger(__name__)


class RedisManager(DatabaseBase):
    """مدیریت Redis جدید"""
    
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
                decode_responses=True
            )
            self._client.ping()
            self._connected = True
            logger.info(f"✅ Redis ({self.name}) متصل شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در اتصال Redis ({self.name}): {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> bool:
        """قطع اتصال"""
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
        """دریافت مقدار"""
        if not self.is_connected():
            return None
        try:
            value = self._client.get(key)
            if value:
                try:
                    return json.loads(value)
                except:
                    return value
            return None
        except Exception as e:
            logger.error(f"❌ خطا در get {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار"""
        if not self.is_connected():
            return False
        try:
            if not isinstance(value, (str, int, float, bool)):
                value = json.dumps(value)
            if ttl:
                self._client.setex(key, ttl, value)
            else:
                self._client.set(key, value)
            return True
        except Exception as e:
            logger.error(f"❌ خطا در set {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """حذف مقدار"""
        if not self.is_connected():
            return False
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"❌ خطا در delete {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید"""
        if not self.is_connected():
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.error(f"❌ خطا در exists {key}: {e}")
            return False
    
    def flush(self) -> bool:
        """پاک کردن همه داده‌ها"""
        if not self.is_connected():
            return False
        try:
            self._client.flushdb()
            logger.warning(f"⚠️ Redis ({self.name}) پاک شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در flush: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار Redis"""
        try:
            info = self._client.info()
            return {
                "keys": info.get("db0", {}).get("keys", 0),
                "memory": info.get("used_memory_human", "0"),
                "clients": info.get("connected_clients", 0),
                "uptime": info.get("uptime_in_seconds", 0)
            }
        except:
            return {}
            
    def ping(self) -> bool:
        """بررسی سلامت"""
        try:
            return self._client.ping()
        except:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        base = super().health_check()
        try:
            info = self._client.info()
            base["version"] = info.get("redis_version", "unknown")
            base["used_memory"] = info.get("used_memory_human", "unknown")
        except:
            base["version"] = "error"
        return base
