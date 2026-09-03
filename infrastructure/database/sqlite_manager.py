# infrastructure/database/sqlite_manager.py
# ============================================================
# مدیریت SQLite - نسخه ۲.۲ (اصلاح شده با Self-Healing)
# ============================================================

import psycopg2
import psycopg2.extras
import logging
import time
import os
from typing import Any, Optional, Dict, List
from infrastructure.database.base import DatabaseBase

logger = logging.getLogger(__name__)


class SQLiteManager(DatabaseBase):
    """
    مدیریت SQLite (از طریق PostgreSQL برای LayerBase)
    با Self-Healing و مدیریت خودکار خطاها
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._connection = None
        self._cursor = None
        self._cached_version = None
        self._version_cache_time = 0
        self._version_cache_ttl = 300
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
    
    def connect(self) -> bool:
        """برقراری اتصال به SQLite از طریق PostgreSQL"""
        try:
            # بستن اتصال قبلی در صورت وجود
            if self._connection:
                try:
                    self._connection.close()
                except:
                    pass
                self._connection = None
                self._cursor = None
            
            # ایجاد اتصال جدید
            self._connection = psycopg2.connect(
                host=self.config.get("host"),
                port=self.config.get("port", 5432),
                user=self.config.get("user"),
                password=self.config.get("password"),
                dbname=self.config.get("database"),
                sslmode="require" if self.config.get("ssl", True) else "disable",
                connect_timeout=10,
                keepalives_idle=30,
                keepalives_interval=5,
                keepalives_count=3
            )
            self._connection.autocommit = True
            self._cursor = self._connection.cursor()
            
            # تست اتصال
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            
            self._connected = True
            self._client = self._connection
            self._reconnect_attempts = 0
            logger.info(f"✅ SQLite ({self.name}) متصل شد")
            return True
            
        except psycopg2.OperationalError as e:
            logger.error(f"❌ خطای عملیاتی SQLite ({self.name}): {e}")
            self._connected = False
            self._client = None
            self._cursor = None
            return False
            
        except Exception as e:
            logger.error(f"❌ خطا در اتصال SQLite ({self.name}): {e}")
            self._connected = False
            self._client = None
            self._cursor = None
            return False

    def disconnect(self) -> bool:
        """قطع اتصال از SQLite"""
        try:
            if self._cursor:
                self._cursor.close()
                self._cursor = None
            if self._connection:
                self._connection.close()
                self._connection = None
            self._connected = False
            self._client = None
            logger.info(f"✅ SQLite ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع SQLite ({self.name}): {e}")
            self._cursor = None
            self._connection = None
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        """
        بررسی واقعی اتصال با اجرای یک کوئری ساده
        این متد override شده تا مشکل connection already closed را حل کند
        """
        if not self._connected or self._client is None or self._cursor is None:
            return False
        
        try:
            # تست اتصال با یک کوئری ساده
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
        except Exception as e:
            # اگر خطا داد، اتصال بسته شده
            logger.warning(f"⚠️ SQLite ({self.name}) connection lost: {e}")
            self._connected = False
            self._cursor = None
            return False
    
    def ensure_connection(self) -> bool:
        """اطمینان از وجود اتصال سالم"""
        if self.is_connected():
            return True
        
        logger.warning(f"⚠️ SQLite ({self.name}) متصل نیست، تلاش برای reconnect...")
        
        # قطع اتصال قبلی
        self.disconnect()
        
        # تلاش برای reconnect
        for attempt in range(self._max_reconnect_attempts):
            if self.connect():
                logger.info(f"✅ SQLite ({self.name}) reconnect successful (attempt {attempt + 1})")
                return True
            time.sleep(2 ** attempt)  # exponential backoff
        
        logger.error(f"❌ SQLite ({self.name}) reconnect failed after {self._max_reconnect_attempts} attempts")
        return False
    
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """
        اجرای کوئری با مدیریت خودکار خطاها و Self-Healing
        """
        # اطمینان از اتصال سالم
        if not self.ensure_connection():
            logger.error(f"❌ SQLite ({self.name}) اتصال برقرار نیست")
            return []
        
        try:
            # اطمینان از وجود cursor
            if self._cursor is None:
                self._cursor = self._connection.cursor()
            
            # اجرای کوئری
            self._cursor.execute(query, params or ())
            
            # اگر SELECT است، نتایج را برگردان
            if query.strip().upper().startswith("SELECT"):
                rows = self._cursor.fetchall()
                if rows:
                    columns = [desc[0] for desc in self._cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
                return []
            
            # برای INSERT/UPDATE/DELETE
            self._connection.commit()
            return []
            
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            # خطای اتصال - reconnect و تلاش مجدد
            logger.warning(f"⚠️ SQLite ({self.name}) connection error: {e}")
            self._connected = False
            self._cursor = None
            
            if self.connect():
                logger.info(f"✅ SQLite ({self.name}) reconnected, retrying query...")
                try:
                    self._cursor = self._connection.cursor()
                    self._cursor.execute(query, params or ())
                    if query.strip().upper().startswith("SELECT"):
                        rows = self._cursor.fetchall()
                        if rows:
                            columns = [desc[0] for desc in self._cursor.description]
                            return [dict(zip(columns, row)) for row in rows]
                        return []
                    self._connection.commit()
                    return []
                except Exception as retry_error:
                    logger.error(f"❌ SQLite ({self.name}) retry failed: {retry_error}")
                    if self._connection:
                        self._connection.rollback()
                    return []
            else:
                logger.error(f"❌ SQLite ({self.name}) reconnect failed")
                return []
                
        except Exception as e:
            logger.error(f"❌ SQLite ({self.name}) query error: {e}")
            if self._connection:
                try:
                    self._connection.rollback()
                except:
                    pass
            return []
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از کش"""
        result = self.execute("SELECT value FROM cache WHERE key = %s", (key,))
        if result:
            return result[0].get("value")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار در کش"""
        try:
            self.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (%s, %s)",
                (key, value)
            )
            return True
        except:
            return False
    
    def delete(self, key: str) -> bool:
        """حذف مقدار از کش"""
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except:
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید در کش"""
        result = self.execute("SELECT 1 FROM cache WHERE key = %s", (key,))
        return len(result) > 0
    
    def flush(self) -> bool:
        """پاک کردن همه داده‌های کش"""
        try:
            self.execute("DELETE FROM cache")
            return True
        except:
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار SQLite"""
        now = time.time()
        if self._cached_version and (now - self._version_cache_time) < self._version_cache_ttl:
            return {"version": self._cached_version}
        
        if not self.ensure_connection():
            return {"version": self._cached_version or "unknown", "error": "not connected"}
        
        for attempt in range(3):
            try:
                result = self.execute("SELECT sqlite_version()")
                if result and len(result) > 0:
                    version = result[0].get('sqlite_version', 'unknown')
                    if version and version != 'unknown':
                        self._cached_version = version
                        self._version_cache_time = now
                        return {"version": version}
                break
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} to get SQLite version failed: {e}")
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        
        return {"version": self._cached_version or "unknown"}
    
    def ping(self) -> bool:
        """
        بررسی سلامت اتصال با اجرای کوئری واقعی
        این متد override شده تا مشکل connection already closed را حل کند
        """
        try:
            if not self._connected or self._cursor is None:
                return False
            
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ SQLite ({self.name}) ping failed: {e}")
            self._connected = False
            self._cursor = None
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل SQLite"""
        base = super().health_check()
        
        # تست واقعی با ping
        ping_result = self.ping()
        base["ping"] = ping_result
        base["connected"] = ping_result and self._connected
        
        try:
            stats = self.get_stats()
            base["version"] = stats.get("version", "unknown")
        except:
            base["version"] = "unknown"
        
        return base
