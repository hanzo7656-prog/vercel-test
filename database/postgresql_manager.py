# database/postgresql_manager.py
# ============================================================
# مدیریت PostgreSQL - نسخه ۲.۱ با کش ورژن
# ============================================================

import psycopg2
import psycopg2.extras
import logging
import time
from typing import Any, Optional, Dict, List
from database.base import DatabaseBase

logger = logging.getLogger(__name__)


class PostgreSQLManager(DatabaseBase):
    """مدیریت PostgreSQL با کش ورژن"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._connection = None
        self._cursor = None
        self._cached_version = None
        self._version_cache_time = 0
        self._version_cache_ttl = 300  # ۵ دقیقه
    
    def connect(self) -> bool:
        try:
            self._connection = psycopg2.connect(
                host=self.config.get("host"),
                port=self.config.get("port", 5432),
                user=self.config.get("user"),
                password=self.config.get("password"),
                dbname=self.config.get("database"),
                sslmode="require" if self.config.get("ssl", True) else "disable",
                connect_timeout=10
            )
            self._connection.autocommit = True
            self._cursor = self._connection.cursor()
            # تست اتصال
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            self._connected = True
            self._client = self._connection
            logger.info(f"✅ PostgreSQL ({self.name}) متصل شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در اتصال PostgreSQL ({self.name}): {e}")
            self._connected = False
            self._client = None
            return False

    def disconnect(self) -> bool:
        try:
            if self._cursor:
                self._cursor.close()
            if self._connection:
                self._connection.close()
            self._connected = False
            logger.info(f"✅ PostgreSQL ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع PostgreSQL ({self.name}): {e}")
            return False
    
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        if not self.is_connected():
            # تلاش مجدد برای اتصال
            if self.connect():
                logger.info(f"✅ PostgreSQL ({self.name}) reconnect successful")
            else:
                logger.warning(f"⚠️ PostgreSQL ({self.name}) متصل نیست")
                return []
        
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    if rows:
                        columns = [desc[0] for desc in cursor.description]
                        return [dict(zip(columns, row)) for row in rows]
                    return []
                self._connection.commit()
                return []
        except Exception as e:
            logger.error(f"❌ خطا در اجرای کوئری PostgreSQL ({self.name}): {e}")
            self._connection.rollback()
            return []
    
    def get(self, key: str) -> Optional[Any]:
        result = self.execute("SELECT value FROM cache WHERE key = %s", (key,))
        if result:
            return result[0].get("value")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            self.execute(
                "INSERT INTO cache (key, value, expires_at) VALUES (%s, %s, NOW() + INTERVAL %s SECOND) "
                "ON CONFLICT (key) DO UPDATE SET value = %s, expires_at = NOW() + INTERVAL %s SECOND",
                (key, value, ttl or 3600, value, ttl or 3600)
            )
            return True
        except:
            return False
    
    def delete(self, key: str) -> bool:
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except:
            return False
    
    def exists(self, key: str) -> bool:
        result = self.execute("SELECT 1 FROM cache WHERE key = %s", (key,))
        return len(result) > 0
    
    def flush(self) -> bool:
        try:
            self.execute("TRUNCATE TABLE cache")
            return True
        except:
            return False
    
    # ============================================================
    # ✅ متد get_stats با کش و Retry
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار PostgreSQL با کش و Retry"""
        # ۱. اگر کش معتبر است، برگردان
        now = time.time()
        if self._cached_version and (now - self._version_cache_time) < self._version_cache_ttl:
            return {"version": self._cached_version}
        
        # ۲. اگر اتصال نداریم، reconnect کن
        if not self.is_connected():
            if not self.connect():
                return {"version": self._cached_version or "unknown", "error": "not connected"}
        
        # ۳. تلاش برای دریافت ورژن با Retry
        for attempt in range(3):
            try:
                result = self.execute("SELECT version()")
                if result and len(result) > 0:
                    version_str = result[0].get('version', '')
                    import re
                    match = re.search(r'(\d+\.\d+)', version_str)
                    if match:
                        version = match.group(1)
                        # ذخیره در کش
                        self._cached_version = version
                        self._version_cache_time = now
                        return {"version": version}
                break
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} to get PostgreSQL version failed: {e}")
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.error(f"❌ Failed to get PostgreSQL version after 3 attempts: {e}")
        
        # ۴. اگر همه تلاش‌ها ناموفق بود، کش قبلی را برگردان
        return {"version": self._cached_version or "unknown"}
    
    def ping(self) -> bool:
        if not self._connected or not self._client:
            return False
        try:
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
        except Exception:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        base = super().health_check()
        try:
            stats = self.get_stats()
            base["version"] = stats.get("version", "unknown")
        except:
            base["version"] = "unknown"
        return base
