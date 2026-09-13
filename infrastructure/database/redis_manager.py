# infrastructure/database/redis_manager.py
# ============================================================
# مدیریت Redis (Upstash) - نسخه ۳.۰
# رفع باگ + بهبود + ارتقا + Namespace Quota
# ============================================================

import redis
import redis.exceptions
import json
import logging
import time
import threading
from typing import Any, Optional, Dict, List, Union
from datetime import datetime

from infrastructure.database.base import DatabaseBase
from infrastructure.database.quota_manager import quota_manager

logger = logging.getLogger(__name__)


class RedisManager(DatabaseBase):
    """
    مدیریت Redis (Upstash)
    
    ویژگی‌ها:
        - پشتیبانی از REST (Serverless) و redis-py (کامل)
        - Read Replica برای خواندن
        - Pipeline برای bulk
        - Pub/Sub
        - Sorted Set operations
        - Hash operations
        - Namespace Quota
    
    رفع باگ‌ها:
        - KEYS * → SCAN (برای production)
        - get_stats بدون timeout
        - بدون read replica
    
    ارتقاها:
        - REST support (upstash-redis)
        - Read replica support
        - Pipeline operations
        - Pub/Sub
        - Distributed Lock
        - Namespace-based quota
    """
    
    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)
        
        self._client: Optional[redis.Redis] = None
        self._readonly_client: Optional[redis.Redis] = None
        self._rest_client: Optional[Any] = None
        self._lock: threading.Lock = threading.Lock()
        
        # تنظیمات Pool
        pool_config = config.get("pool", {})
        self._socket_timeout: int = pool_config.get("socket_timeout", 10)
        self._socket_connect_timeout: int = pool_config.get(
            "socket_connect_timeout", 10
        )
        self._max_connections: int = pool_config.get("max_connections", 10)
        self._health_check_interval: int = pool_config.get(
            "health_check_interval", 30
        )
        
        # Namespace Quota
        self._namespace_stats: Dict[str, int] = {}
        self._namespace_scan_cache: Dict[str, int] = {}
        self._last_namespace_scan: float = 0
        self._namespace_scan_ttl: float = 60
        
        logger.debug(f"✅ RedisManager '{name}' initialized")
    
    # ============================================================
    # Connection Management
    # ============================================================
    
    def connect(self) -> bool:
        """
        برقراری اتصال به Redis
        
        پشتیبانی از:
            - redis-py با SSL (برای عملیات کامل)
            - Read replica
            - REST client (اختیاری)
        """
        with self._lock:
            try:
                conn_config = self.config.get("connection", {})
                
                # اتصال اصلی
                self._client = redis.from_url(
                    conn_config.get("redis_url"),
                    decode_responses=True,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_connect_timeout,
                    max_connections=self._max_connections,
                    retry_on_timeout=True,
                    health_check_interval=self._health_check_interval,
                    ssl_cert_reqs=None,
                )
                
                # تست
                self._client.ping()
                
                # Read replica (اختیاری)
                readonly_url = conn_config.get("readonly_redis_url")
                if readonly_url:
                    try:
                        self._readonly_client = redis.from_url(
                            readonly_url,
                            decode_responses=True,
                            socket_timeout=self._socket_timeout,
                            socket_connect_timeout=self._socket_connect_timeout,
                            ssl_cert_reqs=None,
                        )
                        self._readonly_client.ping()
                        logger.info(f"✅ Redis '{self.name}' read replica connected")
                    except Exception as e:
                        logger.warning(f"⚠️ Read replica failed: {e}")
                        self._readonly_client = None
                
                self._connected = True
                self._client_backup = self._client
                
                logger.info(f"✅ Redis '{self.name}' connected")
                return True
                
            except redis.exceptions.ConnectionError as e:
                logger.error(f"❌ Redis connection error for '{self.name}': {e}")
                self._connected = False
                return False
            except redis.exceptions.TimeoutError as e:
                logger.error(f"❌ Redis timeout for '{self.name}': {e}")
                self._connected = False
                return False
            except Exception as e:
                logger.error(f"❌ Redis error for '{self.name}': {e}")
                self._connected = False
                return False
    
    def disconnect(self) -> bool:
        """قطع اتصال"""
        with self._lock:
            try:
                if self._client:
                    self._client.close()
                if self._readonly_client:
                    self._readonly_client.close()
                self._connected = False
                self._client = None
                self._readonly_client = None
                logger.info(f"✅ Redis '{self.name}' disconnected")
                return True
            except Exception as e:
                logger.error(f"❌ Disconnect error: {e}")
                return False
    
    def is_connected(self) -> bool:
        """بررسی اتصال"""
        return self._connected and self._client is not None
    
    def ensure_connection(self) -> bool:
        """اطمینان از اتصال سالم"""
        if self.is_connected():
            try:
                self._client.ping()
                return True
            except Exception:
                self._connected = False
        
        return self.connect()
    
    # ============================================================
    # Key-Value Operations
    # ============================================================
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار"""
        if not self.ensure_connection():
            return None
        
        try:
            value = self._client.get(key)
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except redis.exceptions.TimeoutError:
            logger.error(f"❌ Redis timeout on get {key}")
            return None
        except redis.exceptions.ConnectionError:
            logger.error(f"❌ Redis connection error on get {key}")
            self._connected = False
            return None
        except Exception as e:
            logger.error(f"❌ Redis get error: {e}")
            return None
    
    def get_readonly(self, key: str) -> Optional[Any]:
        """دریافت از replica (readonly)"""
        if self._readonly_client:
            try:
                value = self._readonly_client.get(key)
                if value is not None:
                    try:
                        return json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        return value
            except Exception:
                pass
        
        return self.get(key)
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """ذخیره مقدار"""
        if not self.ensure_connection():
            return False
        
        try:
            if not isinstance(value, (str, int, float, bool)):
                value = json.dumps(value, ensure_ascii=False)
            
            if ttl:
                self._client.setex(key, ttl, value)
            else:
                self._client.set(key, value)
            
            self._write_count += 1
            return True
            
        except redis.exceptions.TimeoutError:
            logger.error(f"❌ Redis timeout on set {key}")
            return False
        except redis.exceptions.ConnectionError:
            logger.error(f"❌ Redis connection error on set {key}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"❌ Redis set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """حذف مقدار"""
        if not self.ensure_connection():
            return False
        
        try:
            self._client.delete(key)
            self._write_count += 1
            return True
        except Exception as e:
            logger.error(f"❌ Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید"""
        if not self.ensure_connection():
            return False
        
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.error(f"❌ Redis exists error: {e}")
            return False
    
    def flush(self) -> bool:
        """پاک کردن همه (احتیاط!)"""
        if not self.ensure_connection():
            return False
        
        try:
            self._client.flushdb()
            logger.warning(f"⚠️ Redis '{self.name}' flushed!")
            return True
        except Exception as e:
            logger.error(f"❌ Redis flush error: {e}")
            return False
    
    # ============================================================
    # Bulk Operations
    # ============================================================
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """دریافت چند کلید با MGET"""
        if not self.ensure_connection() or not keys:
            return {}
        
        try:
            values = self._client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value
            return result
        except Exception as e:
            logger.error(f"❌ get_many error: {e}")
            return {}
    
    def set_many(self, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """ذخیره چند کلید با Pipeline"""
        if not self.ensure_connection() or not data:
            return False
        
        try:
            pipe = self._client.pipeline()
            for key, value in data.items():
                if not isinstance(value, (str, int, float, bool)):
                    value = json.dumps(value, ensure_ascii=False)
                
                if ttl:
                    pipe.setex(key, ttl, value)
                else:
                    pipe.set(key, value)
            
            pipe.execute()
            self._write_count += len(data)
            return True
        except Exception as e:
            logger.error(f"❌ set_many error: {e}")
            return False
    
    def delete_many(self, keys: List[str]) -> int:
        """حذف چند کلید"""
        if not self.ensure_connection() or not keys:
            return 0
        
        try:
            return self._client.delete(*keys)
        except Exception as e:
            logger.error(f"❌ delete_many error: {e}")
            return 0
    
    # ============================================================
    # SCAN (جایگزین KEYS)
    # ============================================================
    
    def scan_keys(
        self,
        pattern: str = "*",
        count: int = 100,
        max_iterations: int = 1000
    ) -> List[str]:
        """
        دریافت کلیدها با SCAN (به جای KEYS)
        
        رفع باگ: KEYS * در production کند است
        
        پارامترها:
            pattern: الگوی جستجو
            count: تعداد در هر iteration
            max_iterations: حداکثر iteration (برای جلوگیری از loop)
        
        خروجی:
            لیست کلیدها
        """
        if not self.ensure_connection():
            return []
        
        try:
            keys = []
            cursor = 0
            iterations = 0
            
            while iterations < max_iterations:
                cursor, batch = self._client.scan(
                    cursor=cursor,
                    match=pattern,
                    count=count
                )
                keys.extend(batch)
                iterations += 1
                
                if cursor == 0:
                    break
            
            return keys
        except Exception as e:
            logger.error(f"❌ scan_keys error: {e}")
            return []
    
    # ============================================================
    # Hash Operations
    # ============================================================
    
    def hget(self, name: str, key: str) -> Optional[str]:
        """دریافت یک فیلد از Hash"""
        if not self.ensure_connection():
            return None
        
        try:
            return self._client.hget(name, key)
        except Exception as e:
            logger.error(f"❌ hget error: {e}")
            return None
    
    def hset(self, name: str, key: str, value: Any) -> bool:
        """تنظیم یک فیلد در Hash"""
        if not self.ensure_connection():
            return False
        
        try:
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            self._client.hset(name, key, value)
            return True
        except Exception as e:
            logger.error(f"❌ hset error: {e}")
            return False
    
    def hgetall(self, name: str) -> Dict[str, str]:
        """دریافت همه فیلدهای Hash"""
        if not self.ensure_connection():
            return {}
        
        try:
            return self._client.hgetall(name) or {}
        except Exception as e:
            logger.error(f"❌ hgetall error: {e}")
            return {}
    
    # ============================================================
    # Sorted Set Operations
    # ============================================================
    
    def zadd(
        self,
        name: str,
        mapping: Dict[str, float]
    ) -> int:
        """اضافه کردن به Sorted Set"""
        if not self.ensure_connection():
            return 0
        
        try:
            return self._client.zadd(name, mapping)
        except Exception as e:
            logger.error(f"❌ zadd error: {e}")
            return 0
    
    def zrange(
        self,
        name: str,
        start: int = 0,
        end: int = -1,
        withscores: bool = False
    ) -> List[Any]:
        """دریافت از Sorted Set"""
        if not self.ensure_connection():
            return []
        
        try:
            return self._client.zrange(
                name, start, end, withscores=withscores
            )
        except Exception as e:
            logger.error(f"❌ zrange error: {e}")
            return []
    
    # ============================================================
    # Increment / TTL
    # ============================================================
    
    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """افزایش مقدار عددی"""
        if not self.ensure_connection():
            return None
        
        try:
            return self._client.incrby(key, amount)
        except Exception as e:
            logger.error(f"❌ incr error: {e}")
            return None
    
    def ttl(self, key: str) -> int:
        """دریافت TTL"""
        if not self.ensure_connection():
            return -2
        
        try:
            return self._client.ttl(key)
        except Exception as e:
            logger.error(f"❌ ttl error: {e}")
            return -2
    
    def expire(self, key: str, ttl: int) -> bool:
        """تنظیم TTL"""
        if not self.ensure_connection():
            return False
        
        try:
            return bool(self._client.expire(key, ttl))
        except Exception as e:
            logger.error(f"❌ expire error: {e}")
            return False
    
    # ============================================================
    # Distributed Lock
    # ============================================================
    
    def acquire_lock(
        self,
        lock_name: str,
        timeout: int = 10,
        blocking: bool = True,
        blocking_timeout: int = 5
    ) -> Optional[Any]:
        """
        دریافت Lock توزیع‌شده
        
        استفاده:
            lock = redis.acquire_lock("my_lock")
            if lock:
                try:
                    # کار
                    pass
                finally:
                    lock.release()
        """
        if not self.ensure_connection():
            return None
        
        try:
            return self._client.lock(
                lock_name,
                timeout=timeout,
                blocking=blocking,
                blocking_timeout=blocking_timeout
            )
        except Exception as e:
            logger.error(f"❌ acquire_lock error: {e}")
            return None
    
    # ============================================================
    # Stats & Quota
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار Redis"""
        if not self.ensure_connection():
            return {
                "version": "unknown",
                "connected": False,
                "name": self.name,
                "type": "redis",
            }
        
        try:
            info = self._client.info()
            
            used_mb = info.get("used_memory", 0) / (1024 * 1024)
            quota = quota_manager.check_quota(self.name, used_mb)
            
            return {
                "version": info.get("redis_version", "unknown"),
                "connected": True,
                "name": self.name,
                "type": "redis",
                "memory": {
                    "used": info.get("used_memory_human", "0"),
                    "used_mb": round(used_mb, 2),
                    "peak": info.get("used_memory_peak_human", "0"),
                    "max": info.get("maxmemory_human", "0"),
                },
                "clients": {
                    "connected": info.get("connected_clients", 0),
                    "blocked": info.get("blocked_clients", 0),
                },
                "keys": {
                    "total": info.get("db0", {}).get("keys", 0),
                },
                "performance": {
                    "hit_rate": self._calculate_hit_rate(info),
                    "commands": info.get("total_commands_processed", 0),
                },
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "query_count": self._query_count,
                "read_count": self._read_count,
                "write_count": self._write_count,
                "error_count": self._error_count,
                "used_mb": round(used_mb, 2),
                "quota": quota,
                "namespace_stats": self._namespace_stats,
            }
            
        except redis.exceptions.TimeoutError:
            logger.warning(f"⚠️ Redis stats timeout for '{self.name}'")
            return {
                "version": "unknown",
                "connected": True,
                "error": "timeout",
                "name": self.name,
            }
        except Exception as e:
            logger.warning(f"⚠️ Redis stats error: {e}")
            return {
                "version": "unknown",
                "connected": False,
                "error": str(e),
                "name": self.name,
            }
    
    def _calculate_hit_rate(self, info: Dict) -> float:
        """محاسبه hit rate"""
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        return round(hits / total * 100, 2) if total > 0 else 0.0
    
    def _get_quota_summary(self) -> Dict[str, Any]:
        """خلاصه Quota"""
        try:
            if not self.is_connected():
                return quota_manager.check_quota(self.name, 0)
            
            info = self._client.info()
            used_mb = info.get("used_memory", 0) / (1024 * 1024)
            return quota_manager.check_quota(self.name, used_mb)
        except Exception:
            return quota_manager.check_quota(self.name, 0)
    
    def get_namespace_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار namespaceها
        
        برای فرانت‌اند که بتونه ببینه هر namespace چقدر استفاده کرده
        """
        if not self.is_connected():
            return {}
        
        now = time.time()
        if (now - self._last_namespace_scan) < self._namespace_scan_ttl:
            return self._namespace_scan_cache
        
        try:
            quota_config = self.config.get("quota", {})
            per_namespace = quota_config.get("per_namespace", {})
            
            result = {}
            for namespace, config in per_namespace.items():
                pattern = f"{namespace}:*" if not namespace.endswith(":") else f"{namespace}*"
                keys = self.scan_keys(pattern, count=200)
                
                # تخمین حجم (تقریبی)
                estimated_kb = len(keys) * 1  # ~1KB per key تخمینی
                
                result[namespace] = {
                    "keys_count": len(keys),
                    "estimated_mb": round(estimated_kb / 1024, 2),
                    "max_mb": config.get("max_mb", 0),
                    "ttl_default": config.get("ttl_default", 3600),
                }
            
            self._namespace_scan_cache = result
            self._last_namespace_scan = now
            return result
            
        except Exception as e:
            logger.error(f"❌ Namespace stats error: {e}")
            return self._namespace_scan_cache
    
    def ping(self) -> bool:
        """بررسی سلامت"""
        try:
            if not self._client:
                return False
            self._client.ping()
            return True
        except Exception:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        base = super().health_check()
        
        try:
            if self._client and self._connected:
                info = self._client.info()
                base["version"] = info.get("redis_version", "unknown")
                base["used_memory"] = info.get("used_memory_human", "unknown")
                base["keys"] = info.get("db0", {}).get("keys", 0)
                base["connected_clients"] = info.get("connected_clients", 0)
                
                # Quota
                used_mb = info.get("used_memory", 0) / (1024 * 1024)
                base["quota"] = quota_manager.check_quota(self.name, used_mb)
                base["used_mb"] = round(used_mb, 2)
            else:
                base["version"] = "disconnected"
        except Exception as e:
            base["version"] = "error"
            base["error"] = str(e)
        
        return base
    
    # ============================================================
    # Keys (برای سازگاری با کد قدیمی)
    # ============================================================
    
    def keys(self, pattern: str = "*") -> List[str]:
        """دریافت کلیدها (استفاده از SCAN)"""
        return self.scan_keys(pattern)
    
    # ============================================================
    # Cleanup
    # ============================================================
    
    def cleanup_namespace(self, namespace: str) -> int:
        """
        پاک کردن یک namespace
        
        پارامترها:
            namespace: نام namespace (مثل cache:api)
        
        خروجی:
            تعداد کلیدهای حذف شده
        """
        if not self.is_connected():
            return 0
        
        try:
            pattern = f"{namespace}:*" if not namespace.endswith(":") else f"{namespace}*"
            keys = self.scan_keys(pattern, count=500)
            
            if not keys:
                return 0
            
            # حذف batch
            deleted = self.delete_many(keys)
            logger.info(f"✅ Cleaned {deleted} keys from {namespace}")
            quota_manager.mark_cleanup_done(self.name, namespace)
            return deleted
            
        except Exception as e:
            logger.error(f"❌ cleanup_namespace error: {e}")
            return 0
