# infrastructure/api/cache_manager.py
# ============================================================
# مدیریت کش یکپارچه با Redis - نسخه ۲.۰ (انتقال به Infrastructure)
# ============================================================

import json
import logging
from typing import Any, Optional, Dict
from datetime import datetime

from infrastructure.database import get_cache

logger = logging.getLogger(__name__)


class CacheManager:
    """
    مدیریت کش با Redis
    جایگزین کش دیکشنری در api_handler.py
    
    ✅ نسخه ۲.۰: انتقال به Infrastructure
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._redis = get_cache()
            self._stats: Dict[str, int] = {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "errors": 0
            }
            logger.info("✅ CacheManager v2.0 initialized with Redis")
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت از کش"""
        try:
            if self._redis and self._redis.is_connected():
                value = self._redis.get(key)
                if value is not None:
                    self._stats["hits"] += 1
                    return value
            self._stats["misses"] += 1
            return None
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """ذخیره در کش"""
        try:
            if self._redis and self._redis.is_connected():
                self._stats["sets"] += 1
                return self._redis.set(key, value, ttl)
            return False
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """حذف از کش"""
        try:
            if self._redis and self._redis.is_connected():
                return self._redis.delete(key)
            return False
        except Exception as e:
            logger.error(f"❌ Cache delete error: {e}")
            return False
    
    def clear(self) -> bool:
        """پاک کردن همه کش"""
        try:
            if self._redis and self._redis.is_connected():
                self._redis.flush()
                logger.info("✅ Cache cleared")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Cache clear error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کش"""
        return {
            **self._stats,
            "connected": self._redis and self._redis.is_connected(),
            "hit_ratio": round(
                self._stats["hits"] / max(self._stats["hits"] + self._stats["misses"], 1) * 100, 
                2
            )
        }


# نمونه Singleton
cache_manager: CacheManager = CacheManager()
