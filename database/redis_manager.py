# database/redis_manager.py
# ============================================================
# مدیریت Redis با پشتیبانی از هر دو پروتکل
# ============================================================

import json
import logging
from typing import Any, Optional, Dict
from datetime import datetime

from database.base import DatabaseBase

logger = logging.getLogger(__name__)


class RedisManager(DatabaseBase):
    """مدیریت Redis با پشتیبانی از REST و TCP"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._protocol = config.get("protocol", "rest")
        self._client = None
    
    def connect(self) -> bool:
        """برقراری اتصال به Redis"""
        try:
            protocol = self._protocol
            url = self.config.get("url")
            token = self.config.get("token")
            
            if not url:
                logger.error(f"❌ URL برای {self.name} تنظیم نشده")
                return False
            
            # انتخاب پروتکل
            if protocol == "rest":
                # پروتکل REST (Upstash)
                try:
                    from upstash_redis import Redis
                    self._client = Redis(url=url, token=token)
                    self._connected = True
                    logger.info(f"✅ Redis ({self.name}) با پروتکل REST متصل شد")
                    return True
                except ImportError:
                    logger.warning("⚠️ upstash_redis نصب نیست، تلاش با redis-py...")
                    # Fallback به TCP
                    protocol = "tcp"
            
            if protocol == "tcp":
                # پروتکل TCP (redis-py)
                try:
                    import redis
                    # تبدیل URL به فرمت مناسب
                    if not url.startswith("redis"):
                        url = f"rediss://default:{token}@{url.replace('https://', '')}:6379"
                    self._client = redis.Redis.from_url(url)
                    self._client.ping()
                    self._connected = True
                    logger.info(f"✅ Redis ({self.name}) با پروتکل TCP متصل شد")
                    return True
                except ImportError:
                    logger.error("❌ redis-py نصب نیست")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ خطا در اتصال Redis ({self.name}): {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> bool:
        """قطع اتصال Redis"""
        try:
            if self._client:
                if hasattr(self._client, 'close'):
                    self._client.close()
                elif hasattr(self._client, 'connection_pool'):
                    self._client.connection_pool.disconnect()
            self._connected = False
            self._client = None
            logger.info(f"✅ Redis ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع Redis ({self.name}): {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از Redis"""
        if not self.is_connected():
            logger.warning(f"⚠️ Redis ({self.name}) متصل نیست")
            return None
        
        try:
            value = self._client.get(key)
            if value:
                # تلاش برای دیکد JSON
                try:
                    return json.loads(value)
                except:
                    return value
            return None
        except Exception as e:
            logger.error(f"❌ خطا در get {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار در Redis"""
        if not self.is_connected():
            logger.warning(f"⚠️ Redis ({self.name}) متصل نیست")
            return False
        
        try:
            # تبدیل به JSON
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
        """پاک کردن همه داده‌ها (احتیاط!)"""
        if not self.is_connected():
            return False
        
        try:
            self._client.flushall()
            logger.warning(f"⚠️ همه داده‌های Redis ({self.name}) پاک شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در flush {self.name}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار Redis"""
        try:
            info = self._client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "0"),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "keys": info.get("db0", {}).get("keys", 0)
            }
        except:
            return {"error": "Unable to get stats"}
